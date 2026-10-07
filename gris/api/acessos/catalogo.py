"""O catálogo de acessos visto por uma pessoa: o que ela tem, o que pediu, o que falta.

As consultas são agregadas por tipo (papéis, drives, licenças, solicitações) e não por
item, para a página não fazer uma consulta por card.
"""

from __future__ import annotations

import frappe
from frappe.query_builder.functions import Count

from gris.api.acessos import drives, secoes
from gris.api.acessos.constantes import (
	ABA_POR_TIPO,
	ACESSO_DOCTYPE,
	LICENCA_DOCTYPE,
	LICENCA_REVOGACAO_PENDENTE,
	LICENCAS_QUE_OCUPAM_VAGA,
	SOLICITACAO_DOCTYPE,
	STATUS_ABERTOS,
	STATUS_AGUARDANDO_CONCESSAO,
	TIPO_DRIVE,
	TIPO_FERRAMENTA,
	TIPO_PAPEL,
)
from gris.api.acessos.permissoes import associado_do_usuario, eh_gestor, garantir_portal
from gris.api.google_workspace import access_manager as workspace
from gris.api.users.roles import get_role_profile_roles, get_user_roles
from gris.utils.chefes import normalizar_texto

CAMPOS_DO_CATALOGO = [
	"name",
	"titulo",
	"tipo",
	"papel",
	"drive_id",
	"nome_drive",
	"permissao_drive",
	"descricao",
	"o_que_muda",
	"icone",
	"link_externo",
	"solicitavel",
	"exige_associado",
	"por_secao",
	"limite_licencas",
	"ordem",
]

ICONE_PADRAO = {
	TIPO_PAPEL: "key-round",
	TIPO_DRIVE: "hard-drive",
	TIPO_FERRAMENTA: "app-window",
}

# Situação de cada card, do ponto de vista de quem olha.
SITUACAO_TEM = "tem"
SITUACAO_VIA_PERFIL = "via_perfil"
SITUACAO_REVOGACAO_PENDENTE = "revogacao_pendente"
SITUACAO_EM_PROVISIONAMENTO = "em_provisionamento"
SITUACAO_EM_APROVACAO = "em_aprovacao"
SITUACAO_AGUARDANDO = "aguardando_concessao"
SITUACAO_NAO_TEM = "nao_tem"
SITUACAO_INDISPONIVEL = "indisponivel"


def itens_do_catalogo(incluir_inativos: bool = False) -> list[frappe._dict]:
	"""Itens do catálogo; a gestão também vê os inativos, para poder reativá-los."""
	return frappe.get_all(
		ACESSO_DOCTYPE,
		filters={} if incluir_inativos else {"ativo": 1},
		fields=[*CAMPOS_DO_CATALOGO, "ativo", "instrucoes_concessao"],
		order_by="ordem asc, titulo asc",
	)


def vagas_por_ferramenta(nomes: list[str] | None = None) -> dict[str, dict]:
	"""Licenças ocupadas e pedidos aguardando concessão, por ferramenta."""
	filtro_acesso = {"acesso": ["in", nomes]} if nomes else {}

	licenca = frappe.qb.DocType(LICENCA_DOCTYPE)
	consulta = (
		frappe.qb.from_(licenca)
		.select(licenca.acesso, Count("*"))
		.where(licenca.status.isin(list(LICENCAS_QUE_OCUPAM_VAGA)))
		.groupby(licenca.acesso)
	)
	if nomes:
		consulta = consulta.where(licenca.acesso.isin(nomes))
	ocupadas = dict(consulta.run())

	aguardando: dict[str, int] = {}
	for linha in frappe.get_all(
		SOLICITACAO_DOCTYPE,
		filters={"status": STATUS_AGUARDANDO_CONCESSAO, "tipo": TIPO_FERRAMENTA, **filtro_acesso},
		fields=["acesso", "count(name) as total"],
		group_by="acesso",
	):
		aguardando[linha.acesso] = linha.total

	return {"ocupadas": ocupadas, "aguardando": aguardando}


def _resumo_de_vagas(item, vagas: dict) -> dict | None:
	if item.tipo != TIPO_FERRAMENTA:
		return None
	usadas = int(vagas["ocupadas"].get(item.name) or 0)
	aguardando = int(vagas["aguardando"].get(item.name) or 0)
	limite = int(item.limite_licencas or 0)
	return {
		"limite": limite,
		"usadas": usadas,
		"aguardando": aguardando,
		"disponiveis": max(limite - usadas - aguardando, 0) if limite else None,
	}


def _solicitacoes_abertas(user: str) -> dict[str, list[dict]]:
	"""Pedidos em andamento de ``user`` por acesso.

	É uma lista porque um acesso concedido por seção aceita um pedido aberto por seção.
	"""
	abertas = frappe.get_all(
		SOLICITACAO_DOCTYPE,
		filters={"solicitante": user, "status": ["in", STATUS_ABERTOS]},
		fields=["name", "acesso", "secao", "status", "etapa_atual", "creation"],
		order_by="creation asc",
	)
	if not abertas:
		return {}

	etapas: dict[str, list] = {}
	for etapa in frappe.get_all(
		"Etapa de Solicitacao de Acesso",
		filters={"parenttype": SOLICITACAO_DOCTYPE, "parent": ["in", [s.name for s in abertas]]},
		fields=["parent", "ordem", "descricao"],
		order_by="ordem asc",
	):
		etapas.setdefault(etapa.parent, []).append(etapa)

	resultado = {}
	for solicitacao in abertas:
		lista = etapas.get(solicitacao.name, [])
		atual = next((e for e in lista if e.ordem == solicitacao.etapa_atual), None)
		resultado.setdefault(solicitacao.acesso, []).append(
			{
				"name": solicitacao.name,
				"secao": solicitacao.secao,
				"status": solicitacao.status,
				"etapa_atual": solicitacao.etapa_atual,
				"total_etapas": len(lista),
				"etapa_descricao": atual.descricao if atual else None,
			}
		)
	return resultado


def _email_institucional(associado) -> str:
	if not associado:
		return ""
	email = workspace._normalize_email(associado.id_escoteiros)
	return email if workspace._is_institutional_email(email) else ""


def estados_do_catalogo(user: str, associado=None) -> list[dict]:
	"""Cada item ativo do catálogo com a situação de ``user``."""
	itens = itens_do_catalogo()
	if not itens:
		return []

	tipos = {item.tipo for item in itens}
	papeis_do_usuario: set[str] = set()
	papeis_do_perfil: set[str] = set()
	perfil = None
	if TIPO_PAPEL in tipos:
		papeis_do_usuario = get_user_roles(user)
		perfil = frappe.db.get_value("User", user, "role_profile_name")
		papeis_do_perfil = get_role_profile_roles(perfil)

	estado_drives = drives.estado_dos_drives(associado) if TIPO_DRIVE in tipos else {}

	licencas: dict[str, frappe._dict] = {}
	if TIPO_FERRAMENTA in tipos and associado:
		for licenca in frappe.get_all(
			LICENCA_DOCTYPE,
			filters={"associado": associado.name, "status": ["in", LICENCAS_QUE_OCUPAM_VAGA]},
			fields=["name", "acesso", "status", "email", "concedida_em"],
		):
			licencas[licenca.acesso] = licenca

	vagas = vagas_por_ferramenta() if TIPO_FERRAMENTA in tipos else {"ocupadas": {}, "aguardando": {}}
	abertas = _solicitacoes_abertas(user)
	email = _email_institucional(associado)

	por_secao = any(item.por_secao for item in itens)
	secoes_do_usuario = secoes.concessoes_do_usuario(user) if por_secao else {}
	todas_as_secoes = secoes.secoes_existentes() if por_secao else []

	resultado = []
	for item in itens:
		estado = {"situacao": SITUACAO_NAO_TEM, "detalhe": None}

		if item.tipo == TIPO_PAPEL:
			if item.papel in papeis_do_usuario:
				if item.papel in papeis_do_perfil:
					estado = {"situacao": SITUACAO_VIA_PERFIL, "detalhe": perfil}
				else:
					estado = {"situacao": SITUACAO_TEM, "detalhe": None}

		elif item.tipo == TIPO_DRIVE:
			drive = estado_drives.get(item.drive_id)
			if not drive:
				estado = {"situacao": SITUACAO_INDISPONIVEL, "detalhe": "Drive não configurado"}
			elif drive["tem_acesso"]:
				situacao = SITUACAO_EM_PROVISIONAMENTO if drive["em_provisionamento"] else SITUACAO_TEM
				estado = {
					"situacao": situacao,
					"detalhe": drive["permissao_rotulo"],
					"expira_em": str(drive["expira_em"]) if drive["expira_em"] else None,
				}

		elif item.tipo == TIPO_FERRAMENTA:
			licenca = licencas.get(item.name)
			if licenca:
				situacao = (
					SITUACAO_REVOGACAO_PENDENTE
					if licenca.status == LICENCA_REVOGACAO_PENDENTE
					else SITUACAO_TEM
				)
				estado = {"situacao": situacao, "detalhe": licenca.email}

		pedidos = abertas.get(item.name) or []
		solicitacao = pedidos[0] if pedidos else None
		if solicitacao and estado["situacao"] == SITUACAO_NAO_TEM:
			estado = {
				"situacao": SITUACAO_AGUARDANDO
				if solicitacao["status"] == STATUS_AGUARDANDO_CONCESSAO
				else SITUACAO_EM_APROVACAO,
				"detalhe": None,
			}

		recorte = None
		if item.por_secao:
			recorte = _recorte_por_secao(item, papeis_do_usuario, secoes_do_usuario, pedidos, todas_as_secoes)

		motivo_bloqueio = _motivo_para_nao_solicitar(
			item, estado, solicitacao, email, estado_drives, associado, recorte
		)
		resultado.append(
			{
				"name": item.name,
				"titulo": item.titulo,
				"tipo": item.tipo,
				"aba": ABA_POR_TIPO.get(item.tipo),
				"descricao": item.descricao,
				"o_que_muda": item.o_que_muda,
				"icone": item.icone or ICONE_PADRAO.get(item.tipo),
				"link_externo": item.link_externo,
				"papel": item.papel,
				"nome_drive": item.nome_drive,
				"solicitavel": bool(item.solicitavel),
				"por_secao": bool(item.por_secao),
				"recorte": recorte,
				"estado": estado,
				"solicitacao": solicitacao,
				"vagas": _resumo_de_vagas(item, vagas),
				"pode_solicitar": motivo_bloqueio is None,
				"motivo_bloqueio": motivo_bloqueio,
				"email_concessao": email if item.tipo != TIPO_PAPEL else None,
			}
		)
	return resultado


def _recorte_por_secao(item, papeis_do_usuario, secoes_do_usuario, pedidos, todas_as_secoes) -> dict:
	"""Seções que a pessoa já vê, as que pediu e as que ainda pode pedir.

	Só valem as seções de quem tem o papel: é ele que abre a página.
	"""
	concedidas = secoes_do_usuario.get(item.papel, []) if item.papel in papeis_do_usuario else []
	ocupadas = {normalizar_texto(linha.secao) for linha in concedidas}
	ocupadas |= {normalizar_texto(pedido["secao"]) for pedido in pedidos if pedido.get("secao")}
	return {
		"concedidas": [linha.secao for linha in concedidas],
		"pedidas": [
			{"secao": pedido["secao"], "solicitacao": pedido["name"], "status": pedido["status"]}
			for pedido in pedidos
		],
		"disponiveis": [s for s in todas_as_secoes if normalizar_texto(s) not in ocupadas],
	}


def _motivo_para_nao_solicitar(
	item, estado, solicitacao, email, estado_drives, associado=None, recorte=None
) -> str | None:
	if not item.solicitavel:
		return "Este acesso não é concedido por solicitação."
	if item.exige_associado and not associado:
		return "Só associados com cadastro no Gris podem pedir este acesso."
	if recorte is not None:
		# Por seção, ter o papel ou um pedido aberto não impede pedir outra seção.
		if not recorte["disponiveis"]:
			if recorte["concedidas"] or recorte["pedidas"]:
				return "Você já tem ou já pediu todas as seções."
			return "Nenhuma seção cadastrada nos associados."
		return None
	if estado["situacao"] != SITUACAO_NAO_TEM:
		return "Você já tem este acesso ou já pediu."
	if solicitacao:
		return "Já existe uma solicitação em andamento."
	if item.tipo in (TIPO_DRIVE, TIPO_FERRAMENTA) and not email:
		return "É preciso ter um id@escoteiros para receber este acesso."
	if item.tipo == TIPO_DRIVE and item.drive_id not in estado_drives:
		return "Drive não configurado."
	return None


def estado_do_item(user: str, associado, nome_do_acesso: str) -> dict | None:
	return next(
		(item for item in estados_do_catalogo(user, associado) if item["name"] == nome_do_acesso), None
	)


def dados_do_portal(user: str) -> dict:
	"""Tudo o que a página /acessos mostra. A página e a API usam o mesmo payload."""
	from gris.api.acessos.solicitacoes import pendentes_para, solicitacoes_de

	associado = associado_do_usuario(user)
	return {
		"itens": estados_do_catalogo(user, associado),
		"solicitacoes": solicitacoes_de(user),
		"pendentes": pendentes_para(user),
		"email_institucional": _email_institucional(associado),
		"eh_gestor": eh_gestor(user),
	}


@frappe.whitelist(methods=["GET"])
def listar_meus_acessos() -> dict:
	garantir_portal()
	return dados_do_portal(frappe.session.user)
