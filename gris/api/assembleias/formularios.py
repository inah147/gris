# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Formulários de candidatura e de assuntos gerais: quando cada um está aberto (RF-12).

`situacao_do_formulario` é pura: recebe a assembleia, as regras, o instante e as
contagens, e devolve o estado. Os endpoints de envio ficam neste módulo também.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, get_time, get_url, getdate

from gris.api.assembleias import constantes as c

ORDEM_DOS_FORMULARIOS = (
	c.FORMULARIO_MESA,
	c.FORMULARIO_DELEGADO,
	c.FORMULARIO_COMISSAO_FISCAL,
	c.FORMULARIO_DIRETORIA,
	c.FORMULARIO_ASSUNTOS_GERAIS,
)

ROTULO_DO_FORMULARIO = {
	c.FORMULARIO_MESA: "Mesa diretora (presidente e secretário)",
	c.FORMULARIO_DELEGADO: "Delegados para a Assembleia Regional",
	c.FORMULARIO_COMISSAO_FISCAL: "Comissão fiscal",
	c.FORMULARIO_DIRETORIA: "Chapas para a diretoria",
	c.FORMULARIO_ASSUNTOS_GERAIS: "Assuntos gerais",
}

# Como o cargo aparece na frase do edital: "Candidaturas para ... devem ser encaminhadas".
CARGO_NO_EDITAL = {
	c.FORMULARIO_MESA: "a mesa diretora (presidente e secretário)",
	c.FORMULARIO_DELEGADO: "delegados para a Assembleia Regional",
	c.FORMULARIO_COMISSAO_FISCAL: "a Comissão Fiscal",
	c.FORMULARIO_DIRETORIA: "as chapas da diretoria",
}

NUMEROS_POR_EXTENSO = {1: "uma", 2: "duas", 3: "três", 4: "quatro", 5: "cinco", 6: "seis"}


def inicio_da_assembleia(data, hora) -> datetime:
	return datetime.combine(getdate(data), get_time(hora or "00:00:00"))


def regras_de_prazo(config) -> dict:
	"""Unidade e valor de cada prazo, mais as vagas e o "manter aberto"."""
	return {
		"prazos": {
			chave: (
				config.get(f"prazo_{chave}_unidade") or c.PRAZO_SEM_LIMITE,
				cint(config.get(f"prazo_{chave}_valor")),
			)
			for chave in ORDEM_DOS_FORMULARIOS
		},
		"manter_aberto": cint(config.manter_aberto_sem_candidatos),
		"vagas_comissao_fiscal": cint(config.vagas_comissao_fiscal) + cint(config.suplentes_comissao_fiscal),
	}


def limite_de_inscricao(chave: str, inicio: datetime, regras: dict) -> datetime:
	unidade, valor = regras["prazos"].get(chave, (c.PRAZO_SEM_LIMITE, 0))
	if unidade == c.PRAZO_DIAS:
		return inicio - timedelta(days=valor)
	if unidade == c.PRAZO_HORAS:
		return inicio - timedelta(hours=valor)
	return inicio


def falta_candidato(chave: str, contagens: dict, regras: dict, vagas_delegados: int) -> bool:
	"""Art. 9, § 5º: sem inscrições suficientes, aceitam-se novas até a eleição."""
	if chave == c.FORMULARIO_MESA:
		return not contagens.get(c.CARGO_PRESIDENTE_MESA) or not contagens.get(c.CARGO_SECRETARIO_MESA)
	if chave == c.FORMULARIO_COMISSAO_FISCAL:
		return cint(contagens.get(c.CARGO_COMISSAO_FISCAL)) < regras["vagas_comissao_fiscal"]
	if chave == c.FORMULARIO_DELEGADO:
		return cint(contagens.get(c.CARGO_DELEGADO)) < max(cint(vagas_delegados), 1)
	if chave == c.FORMULARIO_DIRETORIA:
		return not contagens.get("chapas")
	return False


def situacao_do_formulario(
	chave: str,
	*,
	finalidades: set[str],
	inicio: datetime,
	regras: dict,
	agora: datetime,
	contagens: dict,
	vagas_delegados: int = 0,
) -> dict:
	"""Estado de um formulário: previsto, aberto, até quando e se foi reaberto."""
	limite = limite_de_inscricao(chave, inicio, regras)
	previsto = c.FINALIDADE_DO_FORMULARIO[chave] in finalidades
	estado = {"chave": chave, "previsto": previsto, "aberto": False, "reaberto": False, "fecha_em": limite}
	if not previsto or agora >= inicio:
		return estado
	if agora < limite:
		estado["aberto"] = True
		return estado
	if regras["manter_aberto"] and falta_candidato(chave, contagens, regras, vagas_delegados):
		estado.update({"aberto": True, "reaberto": True, "fecha_em": inicio})
	return estado


def contar_inscricoes(assembleia: str) -> dict:
	"""Candidaturas ativas por cargo, chapas ativas e assuntos, em três consultas."""
	contagens: dict = {}
	for linha in frappe.get_all(
		c.DOCTYPE_CANDIDATURA,
		filters={"assembleia": assembleia, "status": "Ativa"},
		fields=["cargo", "count(name) as total"],
		group_by="cargo",
	):
		contagens[linha.cargo] = cint(linha.total)
	contagens["chapas"] = frappe.db.count(c.DOCTYPE_CHAPA, {"assembleia": assembleia, "status": "Ativa"})
	contagens["assuntos"] = frappe.db.count(c.DOCTYPE_ASSUNTO, {"assembleia": assembleia})
	return contagens


def link_do_formulario(assembleia: str, chave: str) -> str:
	if chave == c.FORMULARIO_ASSUNTOS_GERAIS:
		return get_url(f"/assembleias/assunto_geral?assembleia={assembleia}")
	return get_url(f"/assembleias/candidatura?assembleia={assembleia}&cargo={chave}")


def prazo_por_extenso(chave: str, regras: dict, inicio: datetime) -> str:
	"""Como o edital diz o prazo: data por extenso, ou horas antes da convocação."""
	from gris.api.assembleias.padroes import data_por_extenso

	unidade, valor = regras["prazos"].get(chave, (c.PRAZO_SEM_LIMITE, 0))
	if unidade == c.PRAZO_DIAS:
		return data_por_extenso(limite_de_inscricao(chave, inicio, regras).date())
	if unidade == c.PRAZO_HORAS:
		quantidade = NUMEROS_POR_EXTENSO.get(valor, str(valor))
		return f"{quantidade} hora{'s' if valor != 1 else ''} antes da primeira convocação"
	return "o início da assembleia"


def formularios_da_assembleia(doc, config, agora=None) -> list[dict]:
	"""Os cinco formulários com estado, link e prazo, na ordem da Visão Geral."""
	agora = get_datetime(agora) if agora else get_datetime()
	regras = regras_de_prazo(config)
	inicio = inicio_da_assembleia(doc.data, doc.hora_primeira_convocacao)
	finalidades = {item.finalidade for item in doc.pauta if item.finalidade}
	contagens = contar_inscricoes(doc.name) if doc.name else {}
	formularios = []
	for chave in ORDEM_DOS_FORMULARIOS:
		estado = situacao_do_formulario(
			chave,
			finalidades=finalidades,
			inicio=inicio,
			regras=regras,
			agora=agora,
			contagens=contagens,
			vagas_delegados=cint(doc.vagas_delegados),
		)
		formularios.append(
			{
				**estado,
				"rotulo": ROTULO_DO_FORMULARIO[chave],
				"link": link_do_formulario(doc.name, chave),
				"prazo": prazo_por_extenso(chave, regras, inicio),
				"fecha_em": str(estado["fecha_em"]),
			}
		)
	return formularios


# --------------------------------------------------------------------------------------
# Quem está enviando e se pode se candidatar
# --------------------------------------------------------------------------------------

AVISO_REGISTRAR_ATE_A_POSSE = (
	"Pelo estatuto (art. 9, § 7º, II), quem for eleito sem registro ativo precisa se registrar "
	"no grupo até a posse."
)


def pessoa_do_usuario(user: str | None = None) -> frappe._dict | None:
	"""Associado ou Responsável de quem está logado; Associado tem precedência.

	O login do associado é o id@escoteiros. Responsável e Associado da mesma pessoa têm o
	mesmo `name`: quem é as duas coisas entra como Associado.
	"""
	from gris.api.acessos.permissoes import associado_do_usuario
	from gris.api.responsavel_acesso import get_responsavel_do_usuario

	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	associado = associado_do_usuario(user)
	if associado:
		return _pessoa("Associado", associado.name)
	responsavel = get_responsavel_do_usuario(user, incluir_vinculo_do_beneficiario=False)
	if responsavel:
		if frappe.db.exists("Associado", responsavel):
			return _pessoa("Associado", responsavel)
		return _pessoa("Responsavel", responsavel)
	return None


def _pessoa(tipo: str, name: str) -> frappe._dict:
	from gris.api.assembleias.pessoas import registro_ativo

	if tipo == "Associado":
		a = frappe.db.get_value(
			"Associado",
			name,
			[
				"name",
				"nome_completo",
				"registro",
				"data_de_nascimento",
				"status_no_grupo",
				"status",
				"validade_registro",
			],
			as_dict=True,
		)
		return frappe._dict(
			tipo=tipo,
			name=a.name,
			nome=a.nome_completo or "",
			registro=a.registro or "",
			nascimento=a.data_de_nascimento,
			ativo=a.status_no_grupo == "Ativo",
			registro_ativo=registro_ativo(a.status, a.validade_registro, getdate()),
		)
	r = frappe.db.get_value(
		"Responsavel",
		name,
		["name", "nome_completo", "numero_de_registro", "data_de_nascimento"],
		as_dict=True,
	)
	return frappe._dict(
		tipo=tipo,
		name=r.name,
		nome=r.nome_completo or "",
		registro=r.numero_de_registro or "",
		nascimento=r.data_de_nascimento,
		ativo=True,
		registro_ativo=False,
	)


def pessoa_por_chave(valor: str | None) -> frappe._dict | None:
	from gris.api.assembleias.pessoas import separar_pessoa

	tipo, name = separar_pessoa(valor)
	return _pessoa(tipo, name) if name else None


def elegibilidade(chave: str, pessoa, data) -> dict:
	"""Art. 9, § 7º: quem pode se candidatar a cada cargo (CA-12.3).

	Devolve `{ok, erro, aviso}`. O aviso não impede: lembra o registro até a posse.
	"""
	from gris.api.assembleias.pessoas import idade_em_anos

	if not pessoa:
		return {"ok": False, "erro": "Seu usuário não está ligado a um cadastro do grupo.", "aviso": ""}
	minima = c.IDADE_MINIMA_CANDIDATURA.get(chave, 18)
	idade = idade_em_anos(pessoa.nascimento, data)
	if pessoa.tipo == "Associado":
		if not pessoa.ativo:
			return {"ok": False, "erro": f"{pessoa.nome} não está ativo no grupo.", "aviso": ""}
		if idade is None or idade < minima:
			return {"ok": False, "erro": f"A candidatura exige {minima} anos ou mais.", "aviso": ""}
		if chave == c.FORMULARIO_DELEGADO and not pessoa.registro_ativo:
			return {
				"ok": False,
				"erro": "A candidatura a delegado exige registro ativo no grupo.",
				"aviso": "",
			}
		aviso = ""
		if chave in (c.FORMULARIO_DIRETORIA, c.FORMULARIO_COMISSAO_FISCAL) and not pessoa.registro_ativo:
			aviso = AVISO_REGISTRAR_ATE_A_POSSE
		return {"ok": True, "erro": "", "aviso": aviso}

	# Responsável legal sem cadastro de associado.
	if chave == c.FORMULARIO_DELEGADO:
		return {"ok": False, "erro": "A candidatura a delegado exige registro ativo no grupo.", "aviso": ""}
	if idade is not None and idade < minima:
		return {"ok": False, "erro": f"A candidatura exige {minima} anos ou mais.", "aviso": ""}
	aviso = AVISO_REGISTRAR_ATE_A_POSSE if chave != c.FORMULARIO_MESA else ""
	return {"ok": True, "erro": "", "aviso": aviso}


# --------------------------------------------------------------------------------------
# Envios (página /assembleias/candidatura e /assembleias/assunto_geral)
# --------------------------------------------------------------------------------------

LIMITE_DE_TEXTO_LIVRE = 2000
CARGO_PARA_FORMULARIO = {
	c.CARGO_PRESIDENTE_MESA: c.FORMULARIO_MESA,
	c.CARGO_SECRETARIO_MESA: c.FORMULARIO_MESA,
	c.CARGO_DELEGADO: c.FORMULARIO_DELEGADO,
	c.CARGO_COMISSAO_FISCAL: c.FORMULARIO_COMISSAO_FISCAL,
}


def _texto_livre(valor, rotulo: str, obrigatorio: bool = False) -> str:
	texto = str(valor or "").strip()
	if obrigatorio and not texto:
		frappe.throw(_("Preencha {0}.").format(rotulo))
	if len(texto) > LIMITE_DE_TEXTO_LIVRE:
		frappe.throw(_("{0} pode ter até {1} caracteres.").format(rotulo, LIMITE_DE_TEXTO_LIVRE))
	return texto


def assembleia_para_formulario(name: str):
	if not name or not frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, name):
		frappe.throw(_("Assembleia não encontrada."), frappe.DoesNotExistError)
	return frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, name)


def situacao_agora(doc, chave: str) -> dict:
	from gris.api.assembleias.padroes import configuracoes

	return next(f for f in formularios_da_assembleia(doc, configuracoes()) if f["chave"] == chave)


def _garantir_aberto(doc, chave: str) -> None:
	situacao = situacao_agora(doc, chave)
	if not situacao["previsto"]:
		frappe.throw(_("Esta assembleia não tem eleição para este cargo na pauta."))
	if not situacao["aberto"]:
		fecha = get_datetime(situacao["fecha_em"])
		frappe.throw(
			_("Inscrições encerradas em {0} às {1}.").format(fecha.strftime("%d/%m"), fecha.strftime("%H:%M"))
		)


def _confirmado(valor) -> None:
	if not cint(valor):
		frappe.throw(_("Confirme o envio para continuar."))


@frappe.whitelist(methods=["POST"])
def enviar_candidatura(
	assembleia: str,
	cargo: str,
	confirmacao: int | str = 0,
	biografia: str | None = None,
	motivacao: str | None = None,
) -> dict:
	"""Candidatura de quem está logado à mesa, a delegado ou à comissão fiscal (RF-12)."""
	doc = assembleia_para_formulario(assembleia)
	chave = CARGO_PARA_FORMULARIO.get(cargo)
	if not chave:
		frappe.throw(_("Cargo inválido."))
	_confirmado(confirmacao)
	_garantir_aberto(doc, chave)
	pessoa = pessoa_do_usuario()
	regra = elegibilidade(chave, pessoa, doc.data)
	if not regra["ok"]:
		frappe.throw(regra["erro"])
	if frappe.db.exists(
		c.DOCTYPE_CANDIDATURA,
		{
			"assembleia": doc.name,
			"cargo": cargo,
			"candidato_tipo": pessoa.tipo,
			"candidato": pessoa.name,
			"status": "Ativa",
		},
	):
		frappe.throw(_("Você já se candidatou a {0} nesta assembleia.").format(cargo))

	candidatura = frappe.get_doc(
		{
			"doctype": c.DOCTYPE_CANDIDATURA,
			"assembleia": doc.name,
			"cargo": cargo,
			"candidato_tipo": pessoa.tipo,
			"candidato": pessoa.name,
			"nome": pessoa.nome,
			"registro": pessoa.registro,
			"registro_ativo": 1 if pessoa.registro_ativo else 0,
			"biografia": _texto_livre(biografia, _("A biografia")),
			"motivacao": _texto_livre(motivacao, _("A motivação")),
			"usuario": frappe.session.user,
			"status": "Ativa",
		}
	)
	# ignore_permissions: quem se candidata não tem permissão no DocType; login, prazo,
	# elegibilidade e duplicidade foram conferidos acima.
	candidatura.insert(ignore_permissions=True)
	return {"ok": True, "cargo": cargo, "nome": pessoa.nome, "aviso": regra["aviso"]}


def funcoes_eleitas() -> list[str]:
	"""Funções eleitas, com a do presidente primeiro, como no art. 10 do estatuto."""
	from gris.utils.diretoria import funcao_do_presidente

	funcoes = frappe.get_all(
		"Funcao Voluntario", filters={"diretoria": "Eleita", "ativa": 1}, pluck="name", order_by="name asc"
	)
	presidente = funcao_do_presidente()
	return sorted(funcoes, key=lambda funcao: (funcao != presidente, funcao))


@frappe.whitelist(methods=["POST"])
def enviar_chapa(assembleia: str, membros: str, confirmacao: int | str = 0) -> dict:
	"""Chapa da diretoria: uma pessoa para cada função eleita (CA-12.8)."""
	import json

	doc = assembleia_para_formulario(assembleia)
	_confirmado(confirmacao)
	_garantir_aberto(doc, c.FORMULARIO_DIRETORIA)
	responsavel = pessoa_do_usuario()
	if not responsavel:
		frappe.throw(_("Seu usuário não está ligado a um cadastro do grupo."))

	try:
		linhas = json.loads(membros or "[]")
	except ValueError:
		frappe.throw(_("Dados inválidos."))
	if not isinstance(linhas, list):
		frappe.throw(_("Dados inválidos."))

	funcoes = funcoes_eleitas()
	por_funcao = {str(linha.get("funcao") or ""): linha for linha in linhas if isinstance(linha, dict)}
	faltando = [f for f in funcoes if not (por_funcao.get(f) or {}).get("pessoa")]
	if faltando:
		frappe.throw(_("Preencha todas as funções da chapa: falta {0}.").format(", ".join(faltando)))

	# Quem já está em outra chapa ativa desta assembleia (art. 9, § 2º).
	em_outra = {}
	for linha in frappe.get_all(
		"Membro da Chapa",
		filters={"parenttype": c.DOCTYPE_CHAPA, "parent": ["in", _chapas_ativas(doc.name) or [""]]},
		fields=["parent", "pessoa_tipo", "pessoa"],
	):
		em_outra[(linha.pessoa_tipo, linha.pessoa)] = linha.parent
	titulos = {
		ch.name: ch.titulo
		for ch in frappe.get_all(c.DOCTYPE_CHAPA, filters={"assembleia": doc.name}, fields=["name", "titulo"])
	}

	vistos = set()
	registros = []
	avisos = []
	for funcao in funcoes:
		linha = por_funcao[funcao]
		pessoa = pessoa_por_chave(linha.get("pessoa"))
		if not pessoa:
			frappe.throw(_("Pessoa inválida para {0}.").format(funcao))
		chave = (pessoa.tipo, pessoa.name)
		if chave in vistos:
			frappe.throw(_("{0} aparece em mais de uma função da chapa.").format(pessoa.nome))
		vistos.add(chave)
		if chave in em_outra:
			frappe.throw(
				_("{0} já está na {1}. O estatuto não permite a mesma pessoa em duas chapas.").format(
					pessoa.nome, titulos.get(em_outra[chave]) or _("outra chapa")
				)
			)
		regra = elegibilidade(c.FORMULARIO_DIRETORIA, pessoa, doc.data)
		if not regra["ok"]:
			frappe.throw(f"{pessoa.nome}: {regra['erro']}")
		if regra["aviso"]:
			avisos.append(pessoa.nome)
		registros.append(
			{
				"funcao": funcao,
				"pessoa_tipo": pessoa.tipo,
				"pessoa": pessoa.name,
				"nome": pessoa.nome,
				"registro": pessoa.registro,
				"registro_ativo": 1 if pessoa.registro_ativo else 0,
				"biografia": _texto_livre(linha.get("biografia"), _("A biografia")),
				"motivacao": _texto_livre(linha.get("motivacao"), _("A motivação")),
			}
		)

	numero = frappe.db.count(c.DOCTYPE_CHAPA, {"assembleia": doc.name}) + 1
	chapa = frappe.get_doc(
		{
			"doctype": c.DOCTYPE_CHAPA,
			"assembleia": doc.name,
			"titulo": f"Chapa {numero}",
			"status": "Ativa",
			"responsavel_usuario": frappe.session.user,
			"responsavel_pessoa_tipo": responsavel.tipo,
			"responsavel_pessoa": responsavel.name,
			"membros": registros,
		}
	)
	# ignore_permissions: idem enviar_candidatura.
	chapa.insert(ignore_permissions=True)
	aviso = f"{', '.join(avisos)}: {AVISO_REGISTRAR_ATE_A_POSSE}" if avisos else ""
	return {
		"ok": True,
		"titulo": chapa.titulo,
		"membros": [(r["funcao"], r["nome"]) for r in registros],
		"aviso": aviso,
	}


def _chapas_ativas(assembleia: str) -> list[str]:
	return frappe.get_all(
		c.DOCTYPE_CHAPA, filters={"assembleia": assembleia, "status": "Ativa"}, pluck="name"
	)


@frappe.whitelist(methods=["POST"])
def enviar_assunto_geral(assembleia: str, conteudo: str, confirmacao: int | str = 0) -> dict:
	"""Assunto geral de quem está logado (CA-12.9)."""
	doc = assembleia_para_formulario(assembleia)
	_confirmado(confirmacao)
	_garantir_aberto(doc, c.FORMULARIO_ASSUNTOS_GERAIS)
	pessoa = pessoa_do_usuario()
	if not pessoa:
		frappe.throw(_("Seu usuário não está ligado a um cadastro do grupo."))
	texto = _texto_livre(conteudo, _("O assunto"), obrigatorio=True)
	assunto = frappe.get_doc(
		{
			"doctype": c.DOCTYPE_ASSUNTO,
			"assembleia": doc.name,
			"conteudo": texto,
			"pessoa_tipo": pessoa.tipo,
			"pessoa": pessoa.name,
			"nome": pessoa.nome,
			"usuario": frappe.session.user,
		}
	)
	# ignore_permissions: idem enviar_candidatura.
	assunto.insert(ignore_permissions=True)
	return {"ok": True, "conteudo": texto}


# --------------------------------------------------------------------------------------
# Leitura: aba da gestão e página pública
# --------------------------------------------------------------------------------------

ORDEM_DOS_CARGOS = (
	c.CARGO_PRESIDENTE_MESA,
	c.CARGO_SECRETARIO_MESA,
	c.CARGO_DELEGADO,
	c.CARGO_COMISSAO_FISCAL,
)


def listar_inscricoes(assembleia: str, somente_ativas: bool = False) -> dict:
	"""Candidaturas por cargo, chapas com membros e assuntos, em quatro consultas."""
	filtros = {"assembleia": assembleia}
	if somente_ativas:
		filtros["status"] = "Ativa"
	candidaturas = frappe.get_all(
		c.DOCTYPE_CANDIDATURA,
		filters=filtros,
		fields=[
			"name",
			"cargo",
			"nome",
			"registro",
			"registro_ativo",
			"biografia",
			"motivacao",
			"status",
			"motivo_retirada",
			"creation",
		],
		order_by="creation asc",
	)
	por_cargo = {cargo: [] for cargo in ORDEM_DOS_CARGOS}
	for cand in candidaturas:
		cand.creation = str(cand.creation)
		por_cargo.setdefault(cand.cargo, []).append(cand)

	chapas = frappe.get_all(
		c.DOCTYPE_CHAPA,
		filters=filtros,
		fields=[
			"name",
			"titulo",
			"status",
			"motivo_retirada",
			"responsavel_pessoa_tipo",
			"responsavel_pessoa",
			"creation",
		],
		order_by="creation asc",
	)
	membros = {}
	if chapas:
		for m in frappe.get_all(
			"Membro da Chapa",
			filters={"parenttype": c.DOCTYPE_CHAPA, "parent": ["in", [ch.name for ch in chapas]]},
			fields=[
				"parent",
				"funcao",
				"nome",
				"registro",
				"registro_ativo",
				"biografia",
				"motivacao",
				"idx",
			],
			order_by="idx asc",
		):
			membros.setdefault(m.parent, []).append(m)
	responsaveis = {}
	for ch in chapas:
		ch.creation = str(ch.creation)
		if ch.responsavel_pessoa_tipo and ch.responsavel_pessoa:
			responsaveis[ch.name] = (
				frappe.db.get_value(ch.responsavel_pessoa_tipo, ch.responsavel_pessoa, "nome_completo") or ""
			)

	assuntos = frappe.get_all(
		c.DOCTYPE_ASSUNTO,
		filters={"assembleia": assembleia},
		fields=["name", "nome", "conteudo", "creation"],
		order_by="creation asc",
	)
	for assunto in assuntos:
		assunto.creation = str(assunto.creation)
	return {
		"cargos": [{"cargo": cargo, "candidaturas": por_cargo.get(cargo, [])} for cargo in ORDEM_DOS_CARGOS],
		"chapas": [
			{**ch, "responsavel_nome": responsaveis.get(ch.name, ""), "membros": membros.get(ch.name, [])}
			for ch in chapas
		],
		"assuntos": assuntos,
	}


def dados_publicos(assembleia: str) -> dict:
	"""Só o que pode ser público (CA-13.2 e CA-13.3): nome, registro, motivação e biografia."""
	inscricoes = listar_inscricoes(assembleia, somente_ativas=True)
	campos = ("nome", "registro", "biografia", "motivacao")
	return {
		"cargos": [
			{
				"cargo": grupo["cargo"],
				"candidaturas": [{k: cand.get(k) or "" for k in campos} for cand in grupo["candidaturas"]],
			}
			for grupo in inscricoes["cargos"]
		],
		"chapas": [
			{
				"titulo": ch["titulo"],
				"membros": [
					{"funcao": m.funcao, **{k: m.get(k) or "" for k in campos}} for m in ch["membros"]
				],
			}
			for ch in inscricoes["chapas"]
		],
	}


@frappe.whitelist(methods=["POST"])
def retirar_inscricao(tipo: str, name: str, motivo: str | None = None) -> dict:
	"""Marca candidatura ou chapa como retirada (impugnação, desistência) — CA-09.4."""
	from gris.api.assembleias.permissoes import garantir_gestor_assembleias

	garantir_gestor_assembleias()
	doctype = {"candidatura": c.DOCTYPE_CANDIDATURA, "chapa": c.DOCTYPE_CHAPA}.get(tipo)
	if not doctype or not frappe.db.exists(doctype, name):
		frappe.throw(_("Inscrição não encontrada."))
	motivo = _texto_livre(motivo, _("O motivo"), obrigatorio=True)
	frappe.db.set_value(doctype, name, {"status": "Retirada", "motivo_retirada": motivo})
	assembleia = frappe.db.get_value(doctype, name, "assembleia")
	return listar_inscricoes(assembleia)
