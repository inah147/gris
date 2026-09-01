# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Mensagens WhatsApp do fluxo de integração de novos associados.

Dois tipos de disparo convivem aqui:

- **Orientado a evento** — chamado pelos controllers quando uma etapa vira: dados de registro
  preenchidos, recepção realizada e registro de associado criado. Cada um grava um carimbo
  em ``Novo Associado`` para nunca repetir.
- **Recorrente** — jobs diários que cobram o que ainda está pendente (dados de registro,
  pesquisa de novos associados, ficha médica, id@escoteiros e acolhida). A cadência de cada
  tipo vem de ``Configuracoes de Recepcao`` e o último envio fica carimbado no próprio jovem,
  de modo que uma execução perdida não atrasa nem duplica a série.

Todos os lembretes param sozinhos: ``finalizar_processo_recepcao`` apaga o ``Novo Associado``
ao encerrar a integração, e uma desistência apaga o registro pelo mesmo caminho.
"""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import add_days, date_diff, get_url, getdate, today

from gris.api.recepcao import formatar_idade
from gris.api.recepcao_funil import RAMOS
from gris.utils import genero
from gris.utils.chefes import buscar_contatos_chefes_por_ramo
from gris.utils.job_logger import definir_resumo, metrica, obter_logger
from gris.utils.whatsapp import (
	adicionar_participantes_no_grupo,
	enviar_para_grupo,
	enviar_texto,
)

SETTINGS_DOCTYPE = "Configuracoes de Recepcao"
STATUS_IGNORADOS = ["Fila de espera", "Concluído"]
STATUS_AGUARDAR_DADOS = "Aguardar Dados"
ASSINATURA = "_Esta é uma mensagem automática_"

DIAS_INICIAIS_PADRAO = (4, 6, 8)
INTERVALO_DADOS_PADRAO = 5
INTERVALO_PESQUISA_PADRAO = 3
INTERVALO_FICHA_MEDICA_PADRAO = 3
INTERVALO_ID_ESCOTEIROS_PADRAO = 5
INTERVALO_ACOLHIDA_PADRAO = 7

TUTORIAL_LOGIN = (
	"https://outline.gepim.com.br/s/f2ffe755-12d2-4b1b-85f0-c52ddc131a50/doc/"
	"acesso-ao-portal-do-responsavel-mLXmETL3X1"
)
TUTORIAL_DADOS_REGISTRO = (
	"https://outline.gepim.com.br/s/f2ffe755-12d2-4b1b-85f0-c52ddc131a50/doc/"
	"preenchimento-dos-dados-para-registro-Po5tDAZ3C7"
)
TUTORIAL_PESQUISA = (
	"https://outline.gepim.com.br/s/f2ffe755-12d2-4b1b-85f0-c52ddc131a50/doc/"
	"respondendo-pesquisa-de-novos-associados-8vH3Z5QchB"
)
TUTORIAL_FICHA_MEDICA = (
	"https://outline.gepim.com.br/s/f2ffe755-12d2-4b1b-85f0-c52ddc131a50/doc/"
	"alteracao-de-ficha-medica-oGSZcBwr2N"
)
PAXTU_PRIMEIRO_ACESSO = "https://paxtu100.escoteiros.org.br/primeiro_acesso"
AJUDA_ID_ESCOTEIROS = "https://id.escoteiros.org.br/pages/ajuda.php"


# ─── Contatos ─────────────────────────────────────────────────────────────────


def _extrair_primeiro_nome(nome_completo: str | None) -> str:
	nome = (nome_completo or "").strip()
	if not nome:
		return "amigo"
	return nome.split()[0]


def _buscar_contatos_responsaveis(novo_associado_names: list[str]) -> dict[str, frappe._dict]:
	"""Retorna o responsável prioritário de cada Novo Associado.

	Prioridade: guardião legal > primeiro responsável. Usa ``celular`` com fallback em
	``telefone_secundario``. Consultas agregadas para evitar N+1.
	"""
	if not novo_associado_names:
		return {}

	links = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": ["in", novo_associado_names]},
		fields=["beneficiario_novo_associado", "responsavel", "é_guardiao_legal", "primeiro_responsavel"],
	)

	links_por_associado: dict[str, list[frappe._dict]] = defaultdict(list)
	responsavel_names: set[str] = set()
	for link in links:
		associado_name = link.get("beneficiario_novo_associado")
		responsavel_name = link.get("responsavel")
		if not associado_name or not responsavel_name:
			continue
		links_por_associado[str(associado_name)].append(link)
		responsavel_names.add(str(responsavel_name))

	if not responsavel_names:
		return {}

	responsaveis = frappe.get_all(
		"Responsavel",
		filters={"name": ["in", list(responsavel_names)]},
		fields=["name", "nome_completo", "sexo", "celular", "telefone_secundario"],
	)
	responsavel_por_name = {str(row.get("name")): row for row in responsaveis if row.get("name")}

	contatos: dict[str, frappe._dict] = {}
	for associado_name, associado_links in links_por_associado.items():
		links_ordenados = sorted(
			associado_links,
			key=lambda lnk: (
				1 if lnk.get("é_guardiao_legal") else 0,
				1 if lnk.get("primeiro_responsavel") else 0,
			),
			reverse=True,
		)

		for link in links_ordenados:
			responsavel = responsavel_por_name.get(str(link.get("responsavel")))
			if not responsavel:
				continue

			telefone = (responsavel.get("celular") or responsavel.get("telefone_secundario") or "").strip()
			contato = frappe._dict(
				{
					"nome": (responsavel.get("nome_completo") or "").strip(),
					"sexo": (responsavel.get("sexo") or "").strip(),
					"telefone": telefone,
				}
			)

			# Prefere o primeiro responsável com telefone; senão mantém o de maior prioridade.
			if telefone or associado_name not in contatos:
				contatos[associado_name] = contato
			if telefone:
				break

	return contatos


def _buscar_contato_do_recepcionista(user_id: str | None) -> frappe._dict | None:
	"""Nome, sexo e telefone do usuário que acompanha a recepção do jovem.

	``Novo Associado.responsavel_recepcao`` é um Link para ``User``: o telefone sai de
	``User.mobile_no``, com fallback no ``Associado`` casado pelo ``id@escoteiros`` — mesma
	resolução usada em ``gris.utils.gestores``.

	O sexo vem sempre do ``Associado``: ``User.gender`` não é preenchido neste site, e é o
	sexo que decide entre "avisar a Ana" e "avisar ao João".
	"""
	if not user_id:
		return None

	user = frappe.db.get_value("User", user_id, ["name", "full_name", "mobile_no"], as_dict=True)
	if not user:
		return None

	associado = (
		frappe.db.get_value("Associado", {"id_escoteiros": user.name}, ["sexo", "telefone"], as_dict=True)
		or {}
	)

	telefone = (user.get("mobile_no") or "").strip() or (associado.get("telefone") or "").strip()
	nome = (user.get("full_name") or "").strip()
	if not nome and not telefone:
		return None

	return frappe._dict({"nome": nome, "sexo": (associado.get("sexo") or "").strip(), "telefone": telefone})


# ─── Configuração ─────────────────────────────────────────────────────────────


def _grupo(fieldname: str) -> str:
	return (frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname) or "").strip()


def _intervalo(fieldname: str, padrao: int) -> int:
	"""Intervalo configurado em dias; cai no padrão quando ausente ou não positivo."""
	try:
		dias = int(frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname))
	except (TypeError, ValueError):
		return padrao
	return dias if dias > 0 else padrao


def _dias_iniciais_lembrete_dados() -> tuple[int, ...]:
	"""Lê a lista "4,6,8" das configurações, ignorando entradas inválidas."""
	bruto = frappe.db.get_single_value(SETTINGS_DOCTYPE, "lembrete_dados_dias_iniciais")
	dias: list[int] = []
	for parte in str(bruto or "").split(","):
		parte = parte.strip()
		if not parte:
			continue
		try:
			valor = int(parte)
		except ValueError:
			continue
		if valor > 0:
			dias.append(valor)

	return tuple(sorted(set(dias))) if dias else DIAS_INICIAIS_PADRAO


def _degraus_do_lembrete_de_dados(dias_decorridos: int) -> list[int]:
	"""Dias de envio já vencidos: os iniciais e, depois deles, um a cada N dias."""
	if dias_decorridos < 0:
		return []

	iniciais = _dias_iniciais_lembrete_dados()
	intervalo = _intervalo("lembrete_dados_intervalo_dias", INTERVALO_DADOS_PADRAO)

	degraus = [dia for dia in iniciais if dia <= dias_decorridos]
	proximo = iniciais[-1] + intervalo
	while proximo <= dias_decorridos:
		degraus.append(proximo)
		proximo += intervalo

	return degraus


def _passou_o_intervalo(ultimo_envio, hoje, intervalo: int) -> bool:
	"""True no primeiro envio ou quando já se passaram ``intervalo`` dias desde o último."""
	if not ultimo_envio:
		return True
	return date_diff(hoje, getdate(ultimo_envio)) >= intervalo


def _carimbar(novo_associado_name: str, fieldname: str, valor) -> None:
	frappe.db.set_value("Novo Associado", novo_associado_name, fieldname, valor, update_modified=False)


# ─── Montagem das mensagens ───────────────────────────────────────────────────


def _mencao(telefone: str | None) -> str:
	"""Trecho ``@<dígitos>`` que o WhatsApp transforma em menção."""
	digitos = "".join(ch for ch in str(telefone or "") if ch.isdigit())
	if not digitos:
		return ""
	if not digitos.startswith("55"):
		digitos = f"55{digitos}"
	return f"@{digitos}"


def _filiacao(sexo: str | None) -> str:
	return genero.flexionar(sexo, "filha de", "filho de", "filho(a) de")


def _ficha_do_jovem(jovem: frappe._dict, contato: frappe._dict | None) -> str:
	"""Bloco de dados repetido nas mensagens dirigidas aos chefes de seção."""
	idade = formatar_idade(jovem.get("data_de_nascimento")) or "não informada"
	nome_responsavel = (contato or {}).get("nome") or "não cadastrado"
	telefone_responsavel = (contato or {}).get("telefone") or "não cadastrado"
	# Sem responsável vinculado não há pessoa com quem concordar: a forma dupla só faz
	# sentido quando existe alguém e o sexo é que está faltando.
	de_responsavel = genero.de(contato.get("sexo")) if contato else "do"

	return (
		f"*Jovem*: {jovem.get('nome_completo') or jovem.get('name')}\n"
		f"*Idade*: {idade}\n"
		f"*Ramo*: {jovem.get('ramo') or 'não definido'}\n"
		f"*Responsável*: {nome_responsavel}\n"
		f"*Telefone {de_responsavel} responsável*: {telefone_responsavel}"
	)


def _montar_dados_preenchidos(nome_jovem: str, nome_responsavel: str, sexo_jovem: str | None) -> str:
	novo_associado = genero.flexionar(
		sexo_jovem, "da nova associada", "do novo associado", "do(a) novo(a) associado(a)"
	)
	return (
		"@todos\n\n"
		"📋 Dados de registro preenchidos!\n\n"
		f"*Jovem*: {nome_jovem}\n"
		f"*Responsável*: {nome_responsavel}\n\n"
		f"Já é possível criar o registro {novo_associado} no PAXTU.\n\n"
		f"Acompanhe na Visão Geral: {get_url('/recepcao/visao_geral')}\n\n"
		f"{ASSINATURA}"
	)


def _montar_visitas_do_dia(data_visita, visitas_por_ramo: dict[str, list[str]]) -> str:
	linhas = [f"*Visitas do dia {getdate(data_visita).strftime('%d/%m/%Y')}*"]

	for ramo in RAMOS:
		linhas.append("")
		linhas.append(f"_Ramo {ramo}_")
		itens = visitas_por_ramo.get(ramo) or []
		if itens:
			linhas.extend(f"- {item}" for item in itens)
		else:
			linhas.append("- Nenhuma visita")

	linhas.append("")
	linhas.append(ASSINATURA)
	return "\n".join(linhas)


def _montar_lembrete_dados(
	*,
	primeiro_nome_responsavel: str,
	primeiro_nome_jovem: str,
	sexo_jovem: str | None,
	recepcionista: frappe._dict | None,
) -> str:
	partes = [
		f"Olá, {primeiro_nome_responsavel}!\n",
		(
			f"Vi que ainda não preencheu os dados para fazer o registro "
			f"{genero.de(sexo_jovem)} {primeiro_nome_jovem}. "
			"Esta etapa é essencial para seguirmos com a integração!"
		),
		(
			"Os dados devem ser preenchidos no Gris. Se estiver com dificuldades, aqui estão alguns "
			"tutoriais que podem ajudar:\n"
		),
		f"*Como fazer login no Gris*\n{TUTORIAL_LOGIN}\n",
		f"*Como preencher os dados para registro*\n{TUTORIAL_DADOS_REGISTRO}\n",
	]

	if recepcionista and recepcionista.get("nome"):
		para_recepcionista = genero.para(recepcionista.get("sexo"))
		contato = f"{para_recepcionista} {recepcionista.get('nome')}, que está acompanhando sua recepção!"
		if recepcionista.get("telefone"):
			contato += f" O telefone é: {recepcionista.get('telefone')}"
		partes.append(
			f"Se ainda tiver dificuldades ou se mudaram de ideia e não forem continuar, só avisar {contato}\n"
		)

	partes.append("Grande abraço!\n")
	partes.append(ASSINATURA)
	return "\n".join(partes)


def _montar_recepcao_realizada(
	*,
	primeiro_nome_jovem: str,
	sexo_jovem: str | None,
	mencao: str,
	ficha: str,
) -> str:
	chamada = f"{mencao} não" if mencao else "Chefe de seção, não"
	return (
		"Olá!\n\n"
		f"Passando para informar que {genero.artigo(sexo_jovem)} {primeiro_nome_jovem} "
		"fez a visita hoje!\n"
		f"{chamada} esqueça de incluir seus responsáveis no grupo de recados gerais e no grupo "
		"de responsáveis da seção. Aqui estão os dados:\n\n"
		f"{ficha}\n\n"
		f"{ASSINATURA}"
	)


def _montar_registro_criado(
	*,
	primeiro_nome_responsavel: str,
	primeiro_nome_jovem: str,
	sexo_jovem: str | None,
	sexo_responsavel: str | None,
	tipo_registro: str,
	numero_registro: str,
) -> str:
	tipo = "definitivo" if (tipo_registro or "").strip() == "Definitivo" else "provisório"
	de_jovem = genero.de(sexo_jovem)
	# "a jovem pela qual você é responsável" concorda com o jovem, não com quem lê.
	por_jovem = genero.por(sexo_jovem)
	de_responsavel = genero.de(sexo_responsavel)
	return (
		f"Olá, {primeiro_nome_responsavel}!\n\n"
		f"Venho trazer ótimas notícias, o registro {tipo} de {primeiro_nome_jovem} já foi criado!\n\n"
		"O número de registro é:\n"
		f"{numero_registro}\n\n"
		f"O próximo passo é fazer o primeiro acesso {de_jovem} jovem no Paxtu, que é o sistema "
		f"oficial dos Escoteiros do Brasil, através do link {PAXTU_PRIMEIRO_ACESSO}. Ao acessar, "
		f"informe o número do registro acima e o CPF {de_jovem} jovem.\n\n"
		"Você também deve fazer o seu primeiro acesso como responsável no Paxtu! O link é o mesmo "
		f"({PAXTU_PRIMEIRO_ACESSO}), mas o registro é diferente, é o seu registro como responsável. "
		f"Para saber qual é este registro, entre com o acesso do Paxtu 100 {de_jovem} jovem "
		f"{por_jovem} qual você é responsável, navegue até a aba de responsáveis e lá você vai "
		f"encontrar o número de registro {de_responsavel} responsável. Outra opção é perguntar para "
		"algum escotista da seção ou para a diretoria qual é o seu registro!\n\n"
		f"{ASSINATURA}"
	)


def _montar_lembrete_pesquisa(primeiro_nome_responsavel: str) -> str:
	return (
		f"Olá, {primeiro_nome_responsavel}!\n\n"
		"Estamos sempre tentando melhorar, e por isso gostaríamos da sua opinião! Dentro do Gris, "
		"aquele sistema onde você preencheu os dados para registro, temos uma pesquisa de novos "
		"associados. Poderia responder, por favor? É super rapidinho e nos ajuda muito a melhorar "
		"constantemente!\n\n"
		"Para te ajudar, aqui está um tutorial de como responder a pesquisa, caso precise:\n"
		f"{TUTORIAL_PESQUISA}\n\n"
		"Grande abraço!\n"
		f"{ASSINATURA}"
	)


def _montar_lembrete_ficha_medica(
	*, primeiro_nome_responsavel: str, primeiro_nome_jovem: str, sexo_jovem: str | None
) -> str:
	return (
		f"Olá, {primeiro_nome_responsavel}!\n\n"
		f"Agora que o registro {genero.de(sexo_jovem)} {primeiro_nome_jovem} já foi processado, "
		f"precisamos preencher os dados da ficha médica {genero.dele(sexo_jovem)}! Estes dados são "
		"essenciais para zelarmos pela segurança dos jovens. O preenchimento é pelo Paxtu, aqui está "
		"um tutorial de como fazer isso para te ajudar:\n"
		f"{TUTORIAL_FICHA_MEDICA}\n\n"
		"Grande abraço!\n"
		f"{ASSINATURA}"
	)


def _montar_lembrete_id_escoteiros(primeiro_nome_responsavel: str) -> str:
	return (
		f"Olá, {primeiro_nome_responsavel}!\n\n"
		"Todos os associados dos Escoteiros do Brasil têm direito a um e-mail institucional, e ele é "
		"super importante! Para criar, acesse o site id.escoteiros.org.br.\n"
		"Para te ajudar, aqui está um passo a passo de como fazer a criação:\n"
		f"{AJUDA_ID_ESCOTEIROS}\n\n"
		"Grande abraço!\n"
		f"{ASSINATURA}"
	)


def _montar_acolhida(*, primeiro_nome_jovem: str, sexo_jovem: str | None, ficha: str, mencao: str) -> str:
	cabecalho = f"{mencao}\n\n" if mencao else ""
	de_jovem = genero.de(sexo_jovem)
	return (
		"Olá!\n\n"
		f"{cabecalho}"
		f"O registro definitivo {de_jovem} jovem {primeiro_nome_jovem} foi efetivado!\n"
		"Isso significa que chegou a hora de fazer sua acolhida e entrega do lenço.\n\n"
		f"Aqui estão os dados {de_jovem} jovem:\n"
		f"{ficha}\n\n"
		f"{ASSINATURA}"
	)


# ─── Disparos orientados a evento ─────────────────────────────────────────────


def _logger_de_evento():
	return frappe.logger("recepcao_mensagens", allow_site=True)


def notificar_dados_preenchidos_no_grupo_recepcao(novo_associado_name: str) -> None:
	"""Avisa o grupo da recepção, com menção geral, que os dados de registro chegaram.

	Chamado ao final de ``gris.www.responsavel.registro.update_novo_associado``.
	Falha silenciosa com log: o cadastro do responsável não pode cair por causa do aviso.
	"""
	logger = _logger_de_evento()

	grupo_jid = _grupo("grupo_recepcao_whatsapp")
	if not grupo_jid:
		logger.warning(
			"Aviso de dados preenchidos não enviado: grupo de recepção não configurado "
			f"({novo_associado_name})."
		)
		return

	try:
		jovem = (
			frappe.db.get_value(
				"Novo Associado", novo_associado_name, ["nome_completo", "sexo"], as_dict=True
			)
			or {}
		)
		contato = _buscar_contatos_responsaveis([novo_associado_name]).get(novo_associado_name)
		mensagem = _montar_dados_preenchidos(
			nome_jovem=jovem.get("nome_completo") or novo_associado_name,
			nome_responsavel=(contato or {}).get("nome") or "não cadastrado",
			sexo_jovem=jovem.get("sexo"),
		)
		enviar_para_grupo(grupo_jid, mensagem, mencionar_todos=True)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Aviso de dados preenchidos (grupo recepção): {novo_associado_name}",
		)


def notificar_recepcao_realizada(novo_associado_name: str) -> None:
	"""Avisa o grupo de chefes que a visita aconteceu e inclui o responsável no grupo geral.

	Disparado na virada de ``primeira_visita_realizada`` para 1. O chefe do ramo do jovem é
	mencionado quando existe cadastro com telefone; sem chefe, a mensagem vai mesmo assim.
	"""
	logger = _logger_de_evento()

	jovem = frappe.db.get_value(
		"Novo Associado",
		novo_associado_name,
		[
			"name",
			"nome_completo",
			"sexo",
			"data_de_nascimento",
			"ramo",
			"data_mensagem_visita_realizada",
		],
		as_dict=True,
	)
	if not jovem or jovem.get("data_mensagem_visita_realizada"):
		return

	contato = _buscar_contatos_responsaveis([novo_associado_name]).get(novo_associado_name)

	grupo_jid = _grupo("grupo_chefes_secao_whatsapp")
	if grupo_jid:
		try:
			chefes = buscar_contatos_chefes_por_ramo([jovem.get("ramo")]) if jovem.get("ramo") else {}
			telefones_chefes = [
				chefe.get("telefone") for chefe in chefes.get(jovem.get("ramo"), []) if chefe.get("telefone")
			]
			mencoes = " ".join(_mencao(telefone) for telefone in telefones_chefes).strip()

			enviar_para_grupo(
				grupo_jid,
				_montar_recepcao_realizada(
					primeiro_nome_jovem=_extrair_primeiro_nome(jovem.get("nome_completo")),
					sexo_jovem=jovem.get("sexo"),
					mencao=mencoes,
					ficha=_ficha_do_jovem(jovem, contato),
				),
				mencionar=telefones_chefes or None,
			)
			_carimbar(novo_associado_name, "data_mensagem_visita_realizada", getdate(today()))
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Aviso de recepção realizada (grupo chefes): {novo_associado_name}",
			)
	else:
		logger.warning(
			"Aviso de recepção realizada não enviado: grupo de chefes de seção não configurado "
			f"({novo_associado_name})."
		)

	_incluir_responsavel_no_grupo_geral(novo_associado_name, contato)


def _incluir_responsavel_no_grupo_geral(novo_associado_name: str, contato: frappe._dict | None) -> None:
	"""Adiciona o responsável ao grupo de recados gerais, se o grupo estiver configurado.

	A adição pode ser recusada pela privacidade de quem seria adicionado — nesse caso o
	chefe de seção ainda tem o pedido manual na mensagem anterior.
	"""
	grupo_geral = _grupo("grupo_recados_gerais_whatsapp")
	telefone = (contato or {}).get("telefone")
	if not grupo_geral or not telefone:
		return

	try:
		adicionar_participantes_no_grupo(grupo_geral, [telefone])
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Inclusão no grupo de recados gerais: {novo_associado_name}",
		)


def notificar_registro_criado(associado_name: str) -> None:
	"""Avisa o responsável que o registro do jovem saiu, com o número para o Paxtu.

	Chamado pelo controller de ``Associado``. ``Associado`` e ``Novo Associado`` compartilham
	o nome (md5 do CPF), então ``associado_name`` também identifica o jovem no funil.
	"""
	logger = _logger_de_evento()

	jovem = frappe.db.get_value(
		"Novo Associado",
		associado_name,
		["name", "nome_completo", "sexo", "data_mensagem_registro_criado"],
		as_dict=True,
	)
	if not jovem or jovem.get("data_mensagem_registro_criado"):
		return

	associado = frappe.db.get_value("Associado", associado_name, ["registro", "tipo_registro"], as_dict=True)
	numero_registro = (associado or {}).get("registro") or ""
	if not numero_registro:
		return

	contato = _buscar_contatos_responsaveis([associado_name]).get(associado_name)
	telefone = (contato or {}).get("telefone")
	if not telefone:
		logger.warning(f"Aviso de registro criado não enviado: nenhum telefone para {associado_name}.")
		return

	try:
		enviar_texto(
			telefone,
			_montar_registro_criado(
				primeiro_nome_responsavel=_extrair_primeiro_nome(contato.get("nome")),
				primeiro_nome_jovem=_extrair_primeiro_nome(jovem.get("nome_completo")),
				sexo_jovem=jovem.get("sexo"),
				sexo_responsavel=contato.get("sexo"),
				tipo_registro=(associado or {}).get("tipo_registro") or "",
				numero_registro=numero_registro,
			),
		)
		_carimbar(associado_name, "data_mensagem_registro_criado", getdate(today()))
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Aviso de registro criado: {associado_name}")


def on_novo_associado_atualizado(doc, method=None) -> None:
	"""``doc_events`` de ``Novo Associado``: dispara o aviso de recepção realizada.

	Cobre todos os caminhos de escrita da etapa (portal da recepção, MCP e Desk) porque
	todos passam por ``doc.save()``.
	"""
	if frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate:
		return
	if doc.flags.get("ignore_notificacoes"):
		return

	anterior = doc.get_doc_before_save()
	if not anterior:
		return

	if doc.primeira_visita_realizada and not anterior.primeira_visita_realizada:
		notificar_recepcao_realizada(doc.name)


# ─── Jobs agendados ───────────────────────────────────────────────────────────


def notificar_visitas_do_dia() -> None:
	"""Sábado de manhã: publica no grupo de chefes as visitas marcadas para hoje.

	A mensagem sai mesmo sem nenhuma visita — os chefes contam com ela para saber que o dia
	está livre, e um silêncio seria indistinguível de uma falha do robô.
	"""
	logger = obter_logger("recepcao_mensagens")
	data_hoje = getdate(today())

	grupo_jid = _grupo("grupo_chefes_secao_whatsapp")
	if not grupo_jid:
		logger.warning("Visitas do dia não enviadas: grupo de chefes de seção não configurado.")
		definir_resumo("Grupo de chefes de seção não configurado — nada enviado.")
		return

	visitas = frappe.get_all(
		"Agenda de Visitas",
		filters={"data_da_visita": data_hoje},
		fields=["name", "jovem", "visita_confirmada", "ramo"],
	)
	metrica("visitas_encontradas", len(visitas), incrementar=False)

	jovens_names = [str(visita.jovem) for visita in visitas if visita.jovem]
	jovens = (
		frappe.get_all(
			"Novo Associado",
			filters={"name": ["in", jovens_names]},
			fields=["name", "nome_completo", "data_de_nascimento", "sexo", "ramo"],
		)
		if jovens_names
		else []
	)
	jovem_por_name = {str(row.get("name")): row for row in jovens}
	contatos = _buscar_contatos_responsaveis(jovens_names)

	visitas_por_ramo: dict[str, list[str]] = defaultdict(list)
	for visita in visitas:
		jovem = jovem_por_name.get(str(visita.jovem)) or {}
		# O ramo do jovem é recalculado diariamente pela idade; o da visita pode estar velho.
		ramo = (jovem.get("ramo") or visita.get("ramo") or "").strip()
		if ramo not in RAMOS:
			logger.warning(f"Visita {visita.name} sem ramo reconhecido ({ramo or '—'}) — fora da lista.")
			metrica("visitas_sem_ramo")
			continue

		nome = jovem.get("nome_completo") or str(visita.jovem)
		idade = formatar_idade(jovem.get("data_de_nascimento")) or "idade não informada"
		contato = contatos.get(str(visita.jovem))
		responsavel = (contato or {}).get("nome") or "responsável não cadastrado"
		confirmacao = "confirmado" if visita.get("visita_confirmada") else "não confirmado"
		visitas_por_ramo[ramo].append(
			f"{nome} - {idade} - {_filiacao(jovem.get('sexo'))} {responsavel} ({confirmacao})"
		)

	listadas = sum(len(itens) for itens in visitas_por_ramo.values())
	try:
		enviar_para_grupo(grupo_jid, _montar_visitas_do_dia(data_hoje, visitas_por_ramo))
	except Exception:
		logger.exception("Falha ao enviar as visitas do dia para o grupo de chefes de seção.")
		metrica("falhas_no_envio")
		frappe.log_error(frappe.get_traceback(), f"Visitas do dia: {data_hoje}")
		definir_resumo("Falha ao enviar as visitas do dia — veja o Error Log.")
		return

	metrica("visitas_listadas", listadas, incrementar=False)
	logger.info(f"{listadas} visita(s) listada(s) para {data_hoje} no grupo de chefes de seção.")
	definir_resumo(f"{listadas} visita(s) de {data_hoje} publicada(s) no grupo de chefes de seção.")


def enviar_lembretes_dados_registro() -> None:
	"""Cobra do responsável o preenchimento dos dados enquanto o jovem espera por eles.

	Os primeiros lembretes seguem os dias configurados (padrão 4, 6 e 8 dias após o status
	virar "Aguardar Dados") e depois se repetem a cada N dias. O degrau vencido é recalculado
	a cada execução a partir da data do status, então uma execução perdida não desloca a série.
	"""
	logger = obter_logger("recepcao_mensagens")
	data_hoje = getdate(today())

	pendentes = frappe.get_all(
		"Novo Associado",
		filters={
			"status": STATUS_AGUARDAR_DADOS,
			"dados_para_registro_enviados": 0,
			"data_status_aguardar_dados": ["is", "set"],
		},
		fields=[
			"name",
			"nome_completo",
			"sexo",
			"responsavel_recepcao",
			"data_status_aguardar_dados",
			"data_lembrete_dados",
		],
	)

	if not pendentes:
		logger.info("Nenhum novo associado aguardando o preenchimento dos dados.")
		definir_resumo("Nenhum novo associado aguardando dados — nada a cobrar.")
		return

	metrica("aguardando_dados", len(pendentes), incrementar=False)
	contatos = _buscar_contatos_responsaveis([str(jovem.name) for jovem in pendentes])

	enviados = 0
	for jovem in pendentes:
		try:
			inicio = getdate(jovem.data_status_aguardar_dados)
			degraus = _degraus_do_lembrete_de_dados(date_diff(data_hoje, inicio))
			if not degraus:
				continue

			alvo = getdate(add_days(inicio, degraus[-1]))
			if jovem.data_lembrete_dados and getdate(jovem.data_lembrete_dados) >= alvo:
				continue

			contato = contatos.get(str(jovem.name))
			telefone = (contato or {}).get("telefone")
			if not telefone:
				logger.warning(f"Lembrete de dados não enviado: nenhum telefone para {jovem.name}.")
				metrica("sem_telefone")
				continue

			enviar_texto(
				telefone,
				_montar_lembrete_dados(
					primeiro_nome_responsavel=_extrair_primeiro_nome(contato.get("nome")),
					primeiro_nome_jovem=_extrair_primeiro_nome(jovem.nome_completo),
					sexo_jovem=jovem.get("sexo"),
					recepcionista=_buscar_contato_do_recepcionista(jovem.responsavel_recepcao),
				),
			)
			_carimbar(str(jovem.name), "data_lembrete_dados", data_hoje)
			enviados += 1
			logger.info(
				f"Lembrete de dados enviado para o responsável de "
				f"{jovem.nome_completo or jovem.name} (degrau de {degraus[-1]} dia(s))."
			)
		except Exception:
			logger.exception(f"Falha ao cobrar os dados de registro de {jovem.name}.")
			metrica("falhas_no_envio")
			frappe.log_error(frappe.get_traceback(), f"Lembrete de dados de registro: {jovem.name}")

	metrica("enviados", enviados, incrementar=False)
	definir_resumo(f"{enviados} de {len(pendentes)} lembrete(s) de preenchimento de dados enviado(s).")


def _enviar_lembretes_para_responsavel(
	*,
	rotulo: str,
	filtros: dict,
	campo_carimbo: str,
	intervalo: int,
	montar_mensagem,
	campos_extras: list[str] | None = None,
	resumir: bool = True,
) -> tuple[int, int]:
	"""Motor comum dos lembretes recorrentes dirigidos ao responsável.

	``montar_mensagem(jovem, contato)`` devolve o texto; ``filtros`` define quem ainda está
	pendente. O carimbo em ``campo_carimbo`` segura o próximo envio por ``intervalo`` dias.

	Devolve ``(enviados, elegíveis)``. Quem roda o motor mais de uma vez no mesmo job passa
	``resumir=False`` e consolida os números, senão a última passada apaga a anterior.
	"""
	logger = obter_logger("recepcao_mensagens")
	data_hoje = getdate(today())

	campos = ["name", "nome_completo", "sexo", campo_carimbo, *(campos_extras or [])]
	pendentes = frappe.get_all(
		"Novo Associado",
		filters={**filtros, "status": ["not in", STATUS_IGNORADOS]},
		fields=list(dict.fromkeys(campos)),
	)

	elegiveis = [
		jovem for jovem in pendentes if _passou_o_intervalo(jovem.get(campo_carimbo), data_hoje, intervalo)
	]

	if not elegiveis:
		logger.info(f"Nenhum lembrete de {rotulo} a enviar hoje.")
		if resumir:
			definir_resumo(f"Nenhum lembrete de {rotulo} a enviar hoje.")
		return 0, 0

	if resumir:
		metrica("elegiveis", len(elegiveis), incrementar=False)
	contatos = _buscar_contatos_responsaveis([str(jovem.name) for jovem in elegiveis])

	enviados = 0
	for jovem in elegiveis:
		try:
			contato = contatos.get(str(jovem.name))
			telefone = (contato or {}).get("telefone")
			if not telefone:
				logger.warning(f"Lembrete de {rotulo} não enviado: nenhum telefone para {jovem.name}.")
				metrica("sem_telefone")
				continue

			enviar_texto(telefone, montar_mensagem(jovem, contato))
			_carimbar(str(jovem.name), campo_carimbo, data_hoje)
			enviados += 1
			logger.info(f"Lembrete de {rotulo} enviado sobre {jovem.nome_completo or jovem.name}.")
		except Exception:
			logger.exception(f"Falha ao enviar o lembrete de {rotulo} de {jovem.name}.")
			metrica("falhas_no_envio")
			frappe.log_error(frappe.get_traceback(), f"Lembrete de {rotulo}: {jovem.name}")

	if resumir:
		metrica("enviados", enviados, incrementar=False)
		definir_resumo(f"{enviados} de {len(elegiveis)} lembrete(s) de {rotulo} enviado(s).")

	return enviados, len(elegiveis)


def enviar_lembretes_pesquisa_novos_associados() -> None:
	"""Pede a resposta da pesquisa de novos associados a quem já enviou os dados de registro."""
	_enviar_lembretes_para_responsavel(
		rotulo="pesquisa de novos associados",
		filtros={
			"dados_para_registro_enviados": 1,
			"pesquisa_de_novos_associados_respondida": 0,
		},
		campo_carimbo="data_lembrete_pesquisa",
		intervalo=_intervalo("lembrete_pesquisa_intervalo_dias", INTERVALO_PESQUISA_PADRAO),
		montar_mensagem=lambda jovem, contato: _montar_lembrete_pesquisa(
			_extrair_primeiro_nome(contato.get("nome"))
		),
	)


def enviar_lembretes_ficha_medica() -> None:
	"""Cobra a ficha médica no Paxtu de quem já teve o registro escolhido efetivado.

	Registro provisório e definitivo têm etapas de efetivação distintas: cada tipo é filtrado
	pela sua, mantendo a seleção no SQL.
	"""
	intervalo = _intervalo("lembrete_ficha_medica_intervalo_dias", INTERVALO_FICHA_MEDICA_PADRAO)
	base = {"ficha_medica_preenchida": 0}

	enviados = 0
	elegiveis = 0
	for tipo, campo_efetivado in (
		("Provisório", "registro_provisorio_efetivado"),
		("Definitivo", "registro_definitivo_efetivado"),
	):
		parciais = _enviar_lembretes_para_responsavel(
			rotulo=f"ficha médica ({tipo.lower()})",
			filtros={**base, "tipo_de_registro": tipo, campo_efetivado: 1},
			campo_carimbo="data_lembrete_ficha_medica",
			intervalo=intervalo,
			montar_mensagem=lambda jovem, contato: _montar_lembrete_ficha_medica(
				primeiro_nome_responsavel=_extrair_primeiro_nome(contato.get("nome")),
				primeiro_nome_jovem=_extrair_primeiro_nome(jovem.nome_completo),
				sexo_jovem=jovem.get("sexo"),
			),
			resumir=False,
		)
		enviados += parciais[0]
		elegiveis += parciais[1]

	# Consolidado das duas passadas: o resumo de uma apagaria o da outra.
	metrica("elegiveis", elegiveis, incrementar=False)
	metrica("enviados", enviados, incrementar=False)
	definir_resumo(f"{enviados} de {elegiveis} lembrete(s) de ficha médica enviado(s).")


def enviar_lembretes_id_escoteiros() -> None:
	"""Cobra a criação do id@escoteiros de quem já preencheu a ficha médica."""
	_enviar_lembretes_para_responsavel(
		rotulo="id@escoteiros",
		filtros={"ficha_medica_preenchida": 1, "id_escoteiros_criado": 0},
		campo_carimbo="data_lembrete_id_escoteiros",
		intervalo=_intervalo("lembrete_id_escoteiros_intervalo_dias", INTERVALO_ID_ESCOTEIROS_PADRAO),
		montar_mensagem=lambda jovem, contato: _montar_lembrete_id_escoteiros(
			_extrair_primeiro_nome(contato.get("nome"))
		),
	)


def enviar_lembretes_acolhida_lenco() -> None:
	"""Lembra o grupo de chefes da acolhida e da entrega do lenço após o registro definitivo.

	Diferente dos outros lembretes, o destinatário é o grupo — o carimbo continua no jovem
	porque a cadência é por jovem, não por grupo.
	"""
	logger = obter_logger("recepcao_mensagens")
	data_hoje = getdate(today())
	intervalo = _intervalo("lembrete_acolhida_intervalo_dias", INTERVALO_ACOLHIDA_PADRAO)

	grupo_jid = _grupo("grupo_chefes_secao_whatsapp")
	if not grupo_jid:
		logger.warning("Avisos de acolhida não enviados: grupo de chefes de seção não configurado.")
		definir_resumo("Grupo de chefes de seção não configurado — nada enviado.")
		return

	pendentes = frappe.get_all(
		"Novo Associado",
		filters={
			"registro_definitivo_efetivado": 1,
			"reuniao_de_acolhida_realizada": 0,
			"status": ["not in", STATUS_IGNORADOS],
		},
		fields=["name", "nome_completo", "sexo", "data_de_nascimento", "ramo", "data_lembrete_acolhida"],
	)
	elegiveis = [
		jovem
		for jovem in pendentes
		if _passou_o_intervalo(jovem.get("data_lembrete_acolhida"), data_hoje, intervalo)
	]

	if not elegiveis:
		logger.info("Nenhum aviso de acolhida a enviar hoje.")
		definir_resumo("Nenhum aviso de acolhida a enviar hoje.")
		return

	metrica("elegiveis", len(elegiveis), incrementar=False)
	contatos = _buscar_contatos_responsaveis([str(jovem.name) for jovem in elegiveis])
	chefes_por_ramo = buscar_contatos_chefes_por_ramo(
		[jovem.get("ramo") for jovem in elegiveis if jovem.get("ramo")]
	)

	enviados = 0
	for jovem in elegiveis:
		try:
			telefones_chefes = [
				chefe.get("telefone")
				for chefe in chefes_por_ramo.get(jovem.get("ramo"), [])
				if chefe.get("telefone")
			]
			mencoes = " ".join(_mencao(telefone) for telefone in telefones_chefes).strip()

			enviar_para_grupo(
				grupo_jid,
				_montar_acolhida(
					primeiro_nome_jovem=_extrair_primeiro_nome(jovem.nome_completo),
					sexo_jovem=jovem.get("sexo"),
					ficha=_ficha_do_jovem(jovem, contatos.get(str(jovem.name))),
					mencao=mencoes,
				),
				mencionar=telefones_chefes or None,
			)
			_carimbar(str(jovem.name), "data_lembrete_acolhida", data_hoje)
			enviados += 1
			logger.info(f"Aviso de acolhida enviado sobre {jovem.nome_completo or jovem.name}.")
		except Exception:
			logger.exception(f"Falha ao enviar o aviso de acolhida de {jovem.name}.")
			metrica("falhas_no_envio")
			frappe.log_error(frappe.get_traceback(), f"Aviso de acolhida: {jovem.name}")

	metrica("enviados", enviados, incrementar=False)
	definir_resumo(f"{enviados} de {len(elegiveis)} aviso(s) de acolhida enviado(s).")
