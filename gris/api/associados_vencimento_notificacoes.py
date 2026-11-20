"""Régua de comunicação do vencimento do registro escoteiro.

Três frentes, todas lidas de ``Configuracoes de Associados``:

1. **Associado ou responsável** (menor de 18): 30, 7 e 1 dia antes, no dia, e depois uma vez
   a cada N dias até renovar ou ficar inativo.
2. **Chefe de seção**: 30 e 7 dias antes e logo depois do vencimento, sobre os beneficiários
   da seção — uma mensagem por chefe por dia, com um bloco por aviso.
3. **Grupo de chefes**: no início do mês, os beneficiários que vencem no mês, por seção.

Cada marco tem uma **janela** de dias, e não um dia exato: um job que não rodou é recuperado
no dia seguinte sem que o texto minta ("vence hoje" nunca sai depois do dia). Os carimbos
ficam no próprio ``Associado`` e valem para uma validade só (``regua_validade_referencia``):
quando a importação do Paxtu traz a validade renovada, a régua recomeça sozinha.

Spec: ``docs/specs/regua-vencimento-registro/spec.md``.
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, get_first_day, get_last_day, getdate, today

from gris.api.associados_vencimento_modelos import (
	MODELO_0,
	MODELO_1,
	MODELO_7,
	MODELO_30,
	MODELO_CHEFE_7,
	MODELO_CHEFE_30,
	MODELO_CHEFE_POS,
	MODELO_GRUPO_MENSAL,
	MODELO_RECORRENTE,
	SETTINGS_DOCTYPE,
	com_rodape,
	instrucoes_renovacao,
	interruptor_ligado,
	mes_por_extenso,
	regua_ativa,
	renderizar,
)
from gris.utils import genero
from gris.utils.chefes import contatos_chefes_dos_beneficiarios, normalizar_texto
from gris.utils.gestores import buscar_destinatarios_gestores
from gris.utils.job_logger import definir_resumo, metrica, obter_logger
from gris.utils.whatsapp import enviar_para_grupo, enviar_texto

NOME_LOGGER = "associados_vencimento_notificacoes"
REGUA_DESLIGADA = "Régua de vencimento desligada nas configurações de associados."
CATEGORIA_BENEFICIARIO = "Beneficiário"
STATUS_ATIVO = "Ativo"
IDADE_ADULTA = 18
MAIOR_ANTECEDENCIA = 30
SEM_SECAO = "Sem seção"

# ─── Marcos ───────────────────────────────────────────────────────────────────

MARCO_30 = "30"
MARCO_7 = "7"
MARCO_1 = "1"
MARCO_0 = "0"
MARCO_RECORRENTE = "recorrente"
ORDEM_DO_ASSOCIADO = (MARCO_30, MARCO_7, MARCO_1, MARCO_0, MARCO_RECORRENTE)

CHEFE_30 = "30"
CHEFE_7 = "7"
CHEFE_POS = "pos"
ORDEM_DO_CHEFE = (CHEFE_30, CHEFE_7, CHEFE_POS)

MODELO_DO_MARCO = {
	MARCO_30: MODELO_30,
	MARCO_7: MODELO_7,
	MARCO_1: MODELO_1,
	MARCO_0: MODELO_0,
	MARCO_RECORRENTE: MODELO_RECORRENTE,
}
INTERRUPTOR_DO_MARCO = {
	MARCO_30: "msg_venc_30",
	MARCO_7: "msg_venc_7",
	MARCO_1: "msg_venc_1",
	MARCO_0: "msg_venc_0",
	MARCO_RECORRENTE: "msg_venc_recorrente",
}
ASSUNTO_DO_MARCO = {
	MARCO_30: "Vencimento do registro: 30 dias antes",
	MARCO_7: "Vencimento do registro: 7 dias antes",
	MARCO_1: "Vencimento do registro: 1 dia antes",
	MARCO_0: "Vencimento do registro: no dia",
	MARCO_RECORRENTE: "Vencimento do registro: cobrança recorrente",
}
MODELO_DO_MARCO_DO_CHEFE = {CHEFE_30: MODELO_CHEFE_30, CHEFE_7: MODELO_CHEFE_7, CHEFE_POS: MODELO_CHEFE_POS}
INTERRUPTOR_DO_MARCO_DO_CHEFE = {
	CHEFE_30: "msg_venc_chefe_30",
	CHEFE_7: "msg_venc_chefe_7",
	CHEFE_POS: "msg_venc_chefe_pos",
}

# Rótulos do campo ``destinatario_tipo`` do ``Log de Mensagem``.
DESTINATARIO_ASSOCIADO = "Associado"
DESTINATARIO_RESPONSAVEL = "Responsável do associado"
DESTINATARIO_CHEFE = "Chefe de seção"
DESTINATARIO_GRUPO_CHEFES = "Grupo de chefes de seção"

CAMPOS_DO_ASSOCIADO = [
	"name",
	"nome_completo",
	"sexo",
	"telefone",
	"categoria",
	"data_de_nascimento",
	"validade_registro",
	"registro",
	"secao",
	"ramo",
	"nome_responsavel_1",
	"telefone_responsavel_1",
	"regua_validade_referencia",
	"regua_ultimo_marco",
	"regua_ultimo_envio",
	"regua_chefe_ultimo_marco",
]


def _janela_do_associado(dias: int, intervalo: int) -> str | None:
	"""Marco cuja janela contém ``dias`` (validade - hoje); entre 0 e -N não há nenhum."""
	if 8 <= dias <= MAIOR_ANTECEDENCIA:
		return MARCO_30
	if 2 <= dias <= 7:
		return MARCO_7
	if dias == 1:
		return MARCO_1
	if dias == 0:
		return MARCO_0
	if dias <= -intervalo:
		return MARCO_RECORRENTE
	return None


def _vem_depois(marco: str, ultimo: str | None, ordem: tuple[str, ...]) -> bool:
	if not ultimo or ultimo not in ordem:
		return True
	return ordem.index(marco) > ordem.index(ultimo)


def marco_devido(
	*,
	dias: int,
	ultimo_marco: str | None,
	ultimo_envio,
	hoje: datetime.date,
	validade: datetime.date,
	corte: datetime.date | None,
	intervalo: int,
) -> str | None:
	"""Qual mensagem o associado deve receber hoje, ou ``None``.

	``ultimo_marco``/``ultimo_envio`` já precisam vir zerados se a validade mudou
	(ver ``estado_vigente``). O corte só vale do dia do vencimento em diante: quem venceu
	antes dele não entra no "no dia" nem na cobrança recorrente.
	"""
	intervalo = max(cint(intervalo), 1)
	marco = _janela_do_associado(dias, intervalo)
	if marco is None:
		return None
	if marco in (MARCO_0, MARCO_RECORRENTE) and corte and validade < corte:
		return None
	if marco == MARCO_RECORRENTE and ultimo_marco == MARCO_RECORRENTE:
		if ultimo_envio and date_diff(hoje, getdate(ultimo_envio)) < intervalo:
			return None
		return marco
	return marco if _vem_depois(marco, ultimo_marco, ORDEM_DO_ASSOCIADO) else None


def marco_do_chefe(
	*,
	dias: int,
	ultimo_marco: str | None,
	validade: datetime.date,
	corte: datetime.date | None,
) -> str | None:
	"""Qual bloco o chefe deve receber hoje sobre este beneficiário, ou ``None``."""
	if 8 <= dias <= MAIOR_ANTECEDENCIA:
		marco = CHEFE_30
	elif 1 <= dias <= 7:
		marco = CHEFE_7
	elif dias <= -1:
		if corte and validade < corte:
			return None
		marco = CHEFE_POS
	else:
		return None
	return marco if _vem_depois(marco, ultimo_marco, ORDEM_DO_CHEFE) else None


@dataclass
class Estado:
	"""Carimbos da régua de um associado, já descartados se a validade mudou."""

	validade: datetime.date
	ultimo_marco: str | None = None
	ultimo_envio: datetime.date | None = None
	chefe_ultimo_marco: str | None = None
	recomecou: bool = False

	def carimbar(self, **campos) -> dict:
		"""Campos a gravar; na primeira gravação depois da troca de validade zera os outros."""
		valores = {"regua_validade_referencia": self.validade, **campos}
		if self.recomecou:
			valores.setdefault("regua_ultimo_marco", None)
			valores.setdefault("regua_ultimo_envio", None)
			valores.setdefault("regua_chefe_ultimo_marco", None)
			self.recomecou = False
		return valores


def estado_vigente(associado) -> Estado:
	validade = getdate(associado.get("validade_registro"))
	referencia = associado.get("regua_validade_referencia")
	if not referencia or getdate(referencia) != validade:
		return Estado(validade=validade, recomecou=bool(referencia))
	return Estado(
		validade=validade,
		ultimo_marco=(associado.get("regua_ultimo_marco") or None),
		ultimo_envio=getdate(associado.get("regua_ultimo_envio"))
		if associado.get("regua_ultimo_envio")
		else None,
		chefe_ultimo_marco=(associado.get("regua_chefe_ultimo_marco") or None),
	)


# ─── Destinatário ─────────────────────────────────────────────────────────────


# Tratamentos que às vezes vêm grudados no nome do cadastro ("Dr. Fulano"): a saudação
# usa o primeiro nome de verdade, não o título.
TRATAMENTOS = frozenset({"dr", "dra", "sr", "sra", "srta", "prof", "profa"})


def _primeiro_nome(nome: str | None) -> str:
	partes = (nome or "").strip().split()
	for parte in partes:
		if parte.rstrip(".").casefold() not in TRATAMENTOS:
			return parte
	return ""


def _idade(nascimento, hoje: datetime.date) -> int:
	nascimento = getdate(nascimento)
	return hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))


def eh_menor(associado, hoje: datetime.date) -> bool:
	"""Menor de 18 pela data de nascimento; beneficiário sem a data conta como menor."""
	nascimento = associado.get("data_de_nascimento")
	if not nascimento:
		return (associado.get("categoria") or "").strip() == CATEGORIA_BENEFICIARIO
	return _idade(nascimento, hoje) < IDADE_ADULTA


def _buscar_links_responsavel(associado_names: list[str]) -> dict[str, list[frappe._dict]]:
	if not associado_names:
		return {}

	links = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_associado": ["in", associado_names]},
		fields=["beneficiario_associado", "responsavel", "é_guardiao_legal", "primeiro_responsavel"],
	)

	links_por_associado: dict[str, list[frappe._dict]] = defaultdict(list)
	for link in links:
		associado_name = link.get("beneficiario_associado")
		if associado_name:
			links_por_associado[str(associado_name)].append(link)

	return links_por_associado


def _buscar_contatos_responsavel(
	links_por_associado: dict[str, list[frappe._dict]],
) -> dict[str, frappe._dict]:
	responsavel_names: set[str] = set()
	for links in links_por_associado.values():
		for link in links:
			responsavel_name = link.get("responsavel")
			if responsavel_name:
				responsavel_names.add(str(responsavel_name))

	if not responsavel_names:
		return {}

	responsaveis = frappe.get_all(
		"Responsavel",
		filters={"name": ["in", list(responsavel_names)]},
		fields=["name", "nome_completo", "celular", "telefone_secundario"],
	)
	return {str(row.get("name")): row for row in responsaveis if row.get("name")}


def _proprio_associado(associado) -> frappe._dict | None:
	telefone = (associado.get("telefone") or "").strip()
	if not telefone:
		return None
	return frappe._dict(
		telefone=telefone,
		nome=associado.get("nome_completo") or "",
		tipo=DESTINATARIO_ASSOCIADO,
	)


def resolver_destinatario(
	associado,
	links_por_associado: dict[str, list[frappe._dict]],
	contatos_responsavel: dict[str, frappe._dict],
	hoje: datetime.date,
) -> frappe._dict | None:
	"""Quem recebe a mensagem do associado.

	Adulto: o próprio telefone. Menor: guardião legal → primeiro responsável →
	``telefone_responsavel_1`` → o telefone do próprio jovem, que costuma ser o da família.
	"""
	if not eh_menor(associado, hoje):
		return _proprio_associado(associado)

	links = sorted(
		links_por_associado.get(str(associado.get("name")), []),
		key=lambda link: (
			1 if link.get("é_guardiao_legal") else 0,
			1 if link.get("primeiro_responsavel") else 0,
		),
		reverse=True,
	)
	for link in links:
		contato = contatos_responsavel.get(str(link.get("responsavel") or "").strip())
		if not contato:
			continue
		telefone = (contato.get("celular") or contato.get("telefone_secundario") or "").strip()
		if telefone:
			return frappe._dict(
				telefone=telefone,
				nome=contato.get("nome_completo") or "",
				tipo=DESTINATARIO_RESPONSAVEL,
			)

	telefone_responsavel = (associado.get("telefone_responsavel_1") or "").strip()
	if telefone_responsavel:
		return frappe._dict(
			telefone=telefone_responsavel,
			nome=associado.get("nome_responsavel_1") or "",
			tipo=DESTINATARIO_RESPONSAVEL,
		)

	return _proprio_associado(associado)


# ─── Montagem das mensagens ───────────────────────────────────────────────────


def _data_br(data) -> str:
	return getdate(data).strftime("%d/%m/%Y")


def contato_duvidas() -> str:
	"""Convite a falar com o administrativo; vazio quando não há quem contatar."""
	from gris.api.recepcao_mensagens import _buscar_responsavel_administrativo

	administrativo = _buscar_responsavel_administrativo()
	if not administrativo:
		return ""
	nome = _primeiro_nome(administrativo.get("nome_completo"))
	telefone = (administrativo.get("telefone") or "").strip()
	if not nome or not telefone:
		return ""
	return (
		f"Dúvidas sobre a renovação? Fale com {genero.artigo(administrativo.get('sexo'))} {nome}, "
		f"do administrativo, pelo telefone {telefone}."
	)


def _textos_comuns() -> dict[str, str]:
	"""Lidos uma vez por rodada: valem para todas as mensagens ao associado."""
	return {
		"como_renovar": instrucoes_renovacao(),
		"como_renovar_vencido": instrucoes_renovacao(vencido=True),
		"contato_duvidas": contato_duvidas(),
	}


def valores_do_associado(associado, destinatario, *, dias: int, comum: dict) -> dict[str, object]:
	nome_associado = (associado.get("nome_completo") or "").strip()
	primeiro_nome_associado = _primeiro_nome(nome_associado)
	if destinatario.tipo == DESTINATARIO_ASSOCIADO:
		registro_de = "seu registro escoteiro"
		primeiro_nome_destinatario = primeiro_nome_associado
	else:
		registro_de = f"o registro escoteiro de {primeiro_nome_associado}"
		primeiro_nome_destinatario = _primeiro_nome(destinatario.nome)
	return {
		"primeiro_nome_destinatario": primeiro_nome_destinatario or "tudo bem",
		"nome_associado": nome_associado,
		"primeiro_nome_associado": primeiro_nome_associado,
		"registro_de": registro_de,
		"data_vencimento": _data_br(associado.get("validade_registro")),
		"dias_restantes": max(dias, 0),
		"dias_vencido": max(-dias, 0),
		"numero_registro": (associado.get("registro") or "").strip(),
		# Mesma regra do status do registro (``Associado._set_status``): no dia já conta como vencido.
		"como_renovar": comum.get("como_renovar_vencido" if dias <= 0 else "como_renovar", ""),
		"contato_duvidas": comum.get("contato_duvidas", ""),
	}


def mensagem_do_associado(marco: str, associado, destinatario, *, dias: int, comum: dict) -> str:
	valores = valores_do_associado(associado, destinatario, dias=dias, comum=comum)
	return com_rodape(renderizar(MODELO_DO_MARCO[marco], valores))


def _secao_exibida(beneficiario) -> str:
	return (beneficiario.get("secao") or "").strip() or SEM_SECAO


def _linha_do_beneficiario(beneficiario, hoje: datetime.date) -> str:
	validade = getdate(beneficiario.get("validade_registro"))
	verbo = "venceu" if validade < hoje else "vence"
	ramo = (beneficiario.get("ramo") or "").strip()
	sufixo = f" ({ramo})" if ramo and ramo != "Não se aplica" else ""
	nome = (beneficiario.get("nome_completo") or beneficiario.get("name") or "").strip()
	return f"• {nome}{sufixo} — {verbo} em {_data_br(validade)}"


def _ordem_dos_beneficiarios(beneficiario) -> tuple:
	return (
		getdate(beneficiario.get("validade_registro")),
		(beneficiario.get("nome_completo") or "").casefold(),
	)


def mensagem_do_chefe(chefe, blocos: dict[tuple[str, str], list], hoje: datetime.date) -> str:
	"""Uma mensagem com um bloco por (marco, seção), na ordem 30 → 7 → vencidos."""
	partes = []
	for (marco, secao), beneficiarios in sorted(
		blocos.items(), key=lambda item: (ORDEM_DO_CHEFE.index(item[0][0]), item[0][1].casefold())
	):
		ordenados = sorted(beneficiarios, key=_ordem_dos_beneficiarios)
		partes.append(
			renderizar(
				MODELO_DO_MARCO_DO_CHEFE[marco],
				{
					"primeiro_nome_chefe": _primeiro_nome(chefe.get("nome_completo")),
					"secao": secao,
					"quantidade": len(ordenados),
					"lista_beneficiarios": "\n".join(_linha_do_beneficiario(b, hoje) for b in ordenados),
				},
			)
		)
	saudacao = f"Olá, {_primeiro_nome(chefe.get('nome_completo')) or 'chefe'}!"
	return com_rodape("\n\n".join([saudacao, *partes]))


def _mencao(telefone: str | None) -> str:
	from gris.api.recepcao_mensagens import _mencao as mencao

	return mencao(telefone)


def _linha_do_resumo(beneficiario) -> str:
	dia = getdate(beneficiario.get("validade_registro")).strftime("%d/%m")
	nome = (beneficiario.get("nome_completo") or beneficiario.get("name") or "").strip()
	return f"• {dia} — {nome}"


def mensagem_do_resumo_mensal(
	beneficiarios: list, chefes_por_beneficiario: dict[str, list], mes: datetime.date
) -> tuple[str, list[str]]:
	"""Texto do resumo do mês e os telefones a mencionar."""
	por_secao: dict[str, list] = defaultdict(list)
	grafia: dict[str, str] = {}
	for beneficiario in beneficiarios:
		chave = normalizar_texto(beneficiario.get("secao"))
		por_secao[chave].append(beneficiario)
		grafia.setdefault(chave, (beneficiario.get("secao") or "").strip())

	mencionar: list[str] = []
	blocos = []
	for chave in sorted(por_secao, key=lambda c: (c == "", grafia[c].casefold())):
		lista = sorted(por_secao[chave], key=_ordem_dos_beneficiarios)
		telefones: list[str] = []
		if chave:
			for beneficiario in lista:
				for chefe in chefes_por_beneficiario.get(beneficiario.get("name"), []):
					if chefe.telefone and chefe.telefone not in telefones:
						telefones.append(chefe.telefone)
		mencoes = " ".join(m for m in (_mencao(t) for t in telefones) if m)
		titulo = f"*{grafia[chave] or SEM_SECAO}*" + (f" {mencoes}" if mencoes else "")
		linhas = [_linha_do_resumo(b) for b in lista]
		blocos.append("\n".join([titulo, *linhas]))
		mencionar.extend(t for t in telefones if t not in mencionar)

	corpo = renderizar(
		MODELO_GRUPO_MENSAL,
		{
			"mes": mes_por_extenso(mes),
			"quantidade": len(beneficiarios),
			"lista_por_secao": "\n\n".join(blocos),
		},
	)
	return com_rodape(corpo), mencionar


# ─── Job ──────────────────────────────────────────────────────────────────────


def _contexto(*, assunto: str, tipo: str, nome: str | None, associado: str | None = None) -> dict:
	return {
		"assunto": assunto,
		"destinatario_tipo": tipo,
		"destinatario_nome": nome or "",
		"associado": associado,
	}


def _commit() -> None:
	# Commit por envio: a mensagem já saiu, e a falha do associado seguinte não pode desfazer
	# o carimbo com um rollback — senão ele receberia a mesma mensagem amanhã.
	frappe.db.commit()  # nosemgrep


def _whatsapp_habilitado() -> bool:
	return bool(cint(frappe.db.get_single_value("Configuracoes WhatsApp", "habilitar_integracao")))


def enviar_lembretes_vencimento_registro_associados() -> None:
	"""Scheduler diário (9h): se a régua estiver ligada, enfileira a rodada na fila longa.

	Com a fila única do WhatsApp (4 a 6 s entre mensagens), uma rodada de dia de muitos
	vencimentos passa dos 5 minutos da fila padrão.
	"""
	if not regua_ativa():
		obter_logger(NOME_LOGGER).info(REGUA_DESLIGADA)
		definir_resumo(REGUA_DESLIGADA)
		return

	definir_resumo("Régua de vencimento do registro enviada para a fila longa.")
	frappe.enqueue(
		"gris.api.associados_vencimento_notificacoes.executar_regua",
		queue="long",
		timeout=3600,
		job_name=f"{frappe.local.site}:regua-vencimento-registro",
	)


def executar_regua(hoje: datetime.date | str | None = None) -> dict:
	"""Rodada da régua: associados, chefes e resumo mensal, nessa ordem."""
	logger = obter_logger(NOME_LOGGER)
	if not regua_ativa():
		definir_resumo(REGUA_DESLIGADA)
		return {"executado": False, "motivo": REGUA_DESLIGADA}
	if not _whatsapp_habilitado():
		motivo = "Integração WhatsApp desabilitada: nenhuma mensagem da régua foi enviada."
		logger.warning(motivo)
		definir_resumo(motivo)
		return {"executado": False, "motivo": motivo}

	hoje = getdate(hoje or today())
	corte_bruto = frappe.db.get_single_value(SETTINGS_DOCTYPE, "cobrar_vencidos_desde")
	corte = getdate(corte_bruto) if corte_bruto else None
	intervalo = max(cint(frappe.db.get_single_value(SETTINGS_DOCTYPE, "intervalo_recorrente_dias") or 3), 1)

	associados = _associados_na_janela(hoje, corte)
	metrica("associados_avaliados", len(associados), incrementar=False)
	estados = {a.name: estado_vigente(a) for a in associados}

	resultado_associados = _avisar_associados(associados, estados, hoje, corte, intervalo, logger)
	resultado_chefes = _avisar_chefes(associados, estados, hoje, corte, logger)
	resultado_resumo = _enviar_resumo_mensal(hoje, logger)

	definir_resumo(
		f"{resultado_associados['enviados']} aviso(s) a associados/responsáveis, "
		f"{resultado_chefes['enviados']} a chefes de seção; resumo mensal: {resultado_resumo['situacao']}. "
		f"{len(associados)} associado(s) avaliados."
	)
	return {
		"executado": True,
		"associados": resultado_associados,
		"chefes": resultado_chefes,
		"resumo_mensal": resultado_resumo,
	}


def _associados_na_janela(hoje: datetime.date, corte: datetime.date | None) -> list[frappe._dict]:
	"""Ativos cuja validade cai em alguma janela: até 30 dias à frente e, para trás, até o corte."""
	limite_superior = add_days(hoje, MAIOR_ANTECEDENCIA)
	filtros: dict = {"status_no_grupo": STATUS_ATIVO}
	if corte:
		filtros["validade_registro"] = ["between", [min(corte, hoje), limite_superior]]
	else:
		filtros["validade_registro"] = ["<=", limite_superior]
	associados = frappe.get_all(
		"Associado", filters=filtros, fields=CAMPOS_DO_ASSOCIADO, order_by="validade_registro asc"
	)
	return [frappe._dict(a) for a in associados if a.get("validade_registro")]


def _avisar_associados(associados, estados, hoje, corte, intervalo, logger) -> dict:
	enviados = 0
	devidos: list[tuple[frappe._dict, str, int]] = []
	for associado in associados:
		estado = estados[associado.name]
		dias = date_diff(estado.validade, hoje)
		marco = marco_devido(
			dias=dias,
			ultimo_marco=estado.ultimo_marco,
			ultimo_envio=estado.ultimo_envio,
			hoje=hoje,
			validade=estado.validade,
			corte=corte,
			intervalo=intervalo,
		)
		if not marco:
			continue
		if not interruptor_ligado(INTERRUPTOR_DO_MARCO[marco]):
			metrica("desativado")
			continue
		devidos.append((associado, marco, dias))

	if not devidos:
		return {"enviados": 0, "devidos": 0}

	nomes = [a.name for a, _marco, _dias in devidos]
	links = _buscar_links_responsavel(nomes)
	contatos = _buscar_contatos_responsavel(links)
	comum = _textos_comuns()

	for associado, marco, dias in devidos:
		destinatario = resolver_destinatario(associado, links, contatos, hoje)
		if not destinatario:
			logger.warning(f"Associado {associado.name} sem telefone para o aviso de vencimento.")
			metrica("sem_telefone")
			continue
		try:
			mensagem = mensagem_do_associado(marco, associado, destinatario, dias=dias, comum=comum)
			enviar_texto(
				destinatario.telefone,
				mensagem,
				enqueue=False,
				contexto=_contexto(
					assunto=ASSUNTO_DO_MARCO[marco],
					tipo=destinatario.tipo,
					nome=destinatario.nome,
					associado=associado.name,
				),
			)
		except Exception:
			logger.exception(f"Falha no aviso de vencimento do associado {associado.name}.")
			metrica("falhas_no_envio")
			frappe.log_error(frappe.get_traceback(), f"Régua de vencimento: associado {associado.name}")
			continue

		estado = estados[associado.name]
		frappe.db.set_value(
			"Associado",
			associado.name,
			estado.carimbar(regua_ultimo_marco=marco, regua_ultimo_envio=hoje),
			update_modified=False,
		)
		estado.ultimo_marco, estado.ultimo_envio = marco, hoje
		_commit()
		enviados += 1
		metrica(f"enviados_{marco}")

	metrica("enviados_associados", enviados, incrementar=False)
	return {"enviados": enviados, "devidos": len(devidos)}


def _avisar_chefes(associados, estados, hoje, corte, logger) -> dict:
	devidos: list[tuple[frappe._dict, str]] = []
	for associado in associados:
		if (associado.get("categoria") or "").strip() != CATEGORIA_BENEFICIARIO:
			continue
		estado = estados[associado.name]
		marco = marco_do_chefe(
			dias=date_diff(estado.validade, hoje),
			ultimo_marco=estado.chefe_ultimo_marco,
			validade=estado.validade,
			corte=corte,
		)
		if not marco:
			continue
		if not interruptor_ligado(INTERRUPTOR_DO_MARCO_DO_CHEFE[marco]):
			metrica("desativado")
			continue
		devidos.append((associado, marco))

	if not devidos:
		return {"enviados": 0, "devidos": 0}

	chefes_por_beneficiario = contatos_chefes_dos_beneficiarios([b for b, _marco in devidos])

	por_chefe: dict[str, dict] = {}
	marco_do_beneficiario: dict[str, str] = {}
	for beneficiario, marco in devidos:
		chefes = chefes_por_beneficiario.get(beneficiario.name) or []
		if not chefes:
			logger.warning(f"Beneficiário {beneficiario.name} sem chefe de seção com telefone.")
			metrica("sem_chefe")
			continue
		marco_do_beneficiario[beneficiario.name] = marco
		for chefe in chefes:
			entrada = por_chefe.setdefault(chefe.name, {"chefe": chefe, "blocos": defaultdict(list)})
			entrada["blocos"][(marco, _secao_exibida(beneficiario))].append(beneficiario)

	avisados: set[str] = set()
	enviados = 0
	for entrada in por_chefe.values():
		chefe = entrada["chefe"]
		try:
			enviar_texto(
				chefe.telefone,
				mensagem_do_chefe(chefe, entrada["blocos"], hoje),
				enqueue=False,
				contexto=_contexto(
					assunto="Vencimento do registro: aviso ao chefe de seção",
					tipo=DESTINATARIO_CHEFE,
					nome=chefe.nome_completo,
				),
			)
		except Exception:
			logger.exception(f"Falha no aviso de vencimento ao chefe {chefe.name}.")
			metrica("falhas_no_envio")
			frappe.log_error(frappe.get_traceback(), f"Régua de vencimento: chefe {chefe.name}")
			continue
		enviados += 1
		for beneficiarios in entrada["blocos"].values():
			avisados.update(b.name for b in beneficiarios)

	for name in avisados:
		estado = estados[name]
		frappe.db.set_value(
			"Associado",
			name,
			estado.carimbar(regua_chefe_ultimo_marco=marco_do_beneficiario[name]),
			update_modified=False,
		)
		estado.chefe_ultimo_marco = marco_do_beneficiario[name]
	if avisados:
		_commit()

	metrica("enviados_chefes", enviados, incrementar=False)
	return {"enviados": enviados, "devidos": len(devidos), "beneficiarios_avisados": len(avisados)}


def _enviar_resumo_mensal(hoje: datetime.date, logger) -> dict:
	mes_ref = hoje.strftime("%Y-%m")
	if not interruptor_ligado("msg_venc_grupo_mensal"):
		return {"situacao": "desligado"}
	if (frappe.db.get_single_value(SETTINGS_DOCTYPE, "resumo_mensal_enviado_em") or "") == mes_ref:
		return {"situacao": "já enviado no mês"}
	grupo = (frappe.db.get_single_value(SETTINGS_DOCTYPE, "grupo_chefes_whatsapp") or "").strip()
	if not grupo:
		logger.warning("Resumo mensal de vencimentos sem grupo de chefes configurado.")
		return {"situacao": "sem grupo configurado"}

	beneficiarios = [
		frappe._dict(b)
		for b in frappe.get_all(
			"Associado",
			filters={
				"status_no_grupo": STATUS_ATIVO,
				"categoria": CATEGORIA_BENEFICIARIO,
				"validade_registro": ["between", [get_first_day(hoje), get_last_day(hoje)]],
			},
			fields=["name", "nome_completo", "secao", "ramo", "validade_registro"],
		)
	]

	if beneficiarios:
		chefes = contatos_chefes_dos_beneficiarios(beneficiarios)
		mensagem, mencionar = mensagem_do_resumo_mensal(beneficiarios, chefes, hoje)
		try:
			enviar_para_grupo(
				grupo,
				mensagem,
				mencionar=mencionar or None,
				enqueue=False,
				contexto=_contexto(
					assunto="Vencimento do registro: resumo do mês",
					tipo=DESTINATARIO_GRUPO_CHEFES,
					nome=None,
				),
			)
		except Exception:
			logger.exception("Falha no resumo mensal de vencimentos.")
			metrica("falhas_no_envio")
			frappe.log_error(frappe.get_traceback(), "Régua de vencimento: resumo mensal")
			return {"situacao": "falhou"}

	frappe.db.set_single_value(SETTINGS_DOCTYPE, "resumo_mensal_enviado_em", mes_ref)
	_commit()
	if not beneficiarios:
		return {"situacao": "nenhum vencimento no mês"}
	metrica("resumo_mensal_beneficiarios", len(beneficiarios), incrementar=False)
	return {"situacao": f"enviado ({len(beneficiarios)} beneficiário(s))"}


# ─── Aviso manual (botão "Avisar Vencimento" na ficha do Associado) ───────────


def marco_natural(dias: int) -> str:
	"""Modelo que o botão manual usa: a janela do dia, sem carimbo nem corte."""
	if dias >= 8:
		return MARCO_30
	if dias >= 2:
		return MARCO_7
	if dias == 1:
		return MARCO_1
	if dias == 0:
		return MARCO_0
	return MARCO_RECORRENTE


def _mensagem_ao_gestor(*, dias_para_vencer: int, associado_nome: str, gestor) -> str:
	situacao = "venceu hoje" if dias_para_vencer == 0 else f"venceu há {abs(dias_para_vencer)} dia(s)"
	corpo = (
		f"Olá, {_primeiro_nome(gestor.get('nome')) or 'tudo bem'}!\n\n"
		f"Atenção: o registro escoteiro de {_primeiro_nome(associado_nome)} {situacao}.\n"
		"Verifique o status e tome as providências necessárias."
	)
	return com_rodape(corpo)


@frappe.whitelist()
def notificar_vencimento_manual(associado_name: str) -> dict:
	"""Envia na hora o aviso do marco atual, mesmo com a régua desligada, sem carimbar."""
	if not frappe.has_permission("Associado", "read", associado_name):
		frappe.throw(_("Sem permissão para acessar este Associado."), frappe.PermissionError)

	associado = frappe._dict(
		frappe.db.get_value("Associado", associado_name, CAMPOS_DO_ASSOCIADO, as_dict=True) or {}
	)
	if not associado.get("name"):
		frappe.throw(_("Associado não encontrado."))
	if not associado.get("validade_registro"):
		frappe.throw(_("Este associado não possui validade de registro informada."))

	hoje = getdate(today())
	dias = date_diff(getdate(associado.validade_registro), hoje)
	links = _buscar_links_responsavel([associado.name])
	destinatario = resolver_destinatario(associado, links, _buscar_contatos_responsavel(links), hoje)
	if not destinatario:
		frappe.throw(_("Não foi possível encontrar um número de telefone elegível para o aviso."))

	marco = marco_natural(dias)
	comum = _textos_comuns()
	enviar_texto(
		destinatario.telefone,
		mensagem_do_associado(marco, associado, destinatario, dias=dias, comum=comum),
		contexto=_contexto(
			assunto=f"{ASSUNTO_DO_MARCO[marco]} (envio manual)",
			tipo=destinatario.tipo,
			nome=destinatario.nome,
			associado=associado.name,
		),
	)

	if dias <= 0:
		for gestor in buscar_destinatarios_gestores():
			try:
				enviar_texto(
					gestor.telefone,
					_mensagem_ao_gestor(
						dias_para_vencer=dias,
						associado_nome=associado.nome_completo or associado.name,
						gestor=gestor,
					),
					contexto=_contexto(
						assunto="Vencimento do registro: aviso ao gestor (envio manual)",
						tipo="Não identificado",
						nome=gestor.get("nome"),
						associado=associado.name,
					),
				)
			except Exception:
				frappe.log_error(
					frappe.get_traceback(),
					f"Aviso gestor vencimento manual: gestor={gestor.get('nome')}, associado={associado_name}",
				)

	frappe.logger(NOME_LOGGER, allow_site=True).info(
		f"Aviso manual de vencimento ({marco}) enviado para {destinatario.tipo} — "
		f"associado={associado_name}, dias={dias}."
	)
	return {
		"destinatario_nome": destinatario.nome,
		"destinatario_tipo": "associado" if destinatario.tipo == DESTINATARIO_ASSOCIADO else "responsavel",
		"dias_para_vencer": dias,
		"marco": marco,
	}
