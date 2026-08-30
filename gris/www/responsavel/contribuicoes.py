"""Contribuições mensais dos beneficiários, na visão do responsável.

O responsável vê aqui exatamente os beneficiários vinculados a ele, com o mês a
mês do que está pago e do que está em atraso. A apuração é a mesma da tela do
financeiro (`gris.api.financeiro.contribuicoes`) — o que muda é o recorte: nada
que não seja de um beneficiário vinculado entra nesta página.
"""

import frappe
from frappe import _

from gris.api.financeiro.cobranca_contribuicao import FINALIDADE_CONTRIBUICAO
from gris.api.financeiro.contribuicoes import (
	MESES_PADRAO,
	STATUS_ATRASADO,
	STATUS_PARCIAL,
	apurar_associados,
	competencias_pendentes,
	normalizar_meses,
)
from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached
from gris.api.responsavel_acesso import get_beneficiarios_associados, get_responsavel_do_usuario

no_cache = 1

ROTA = "/responsavel/contribuicoes"

# Janelas de apuração oferecidas no filtro da página.
OPCOES_PERIODO = [
	{"label": "Últimos 6 meses", "value": "6"},
	{"label": "Últimos 12 meses", "value": "12"},
	{"label": "Últimos 24 meses", "value": "24"},
]


def get_context(context):
	enrich_context(context, ROTA)

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={ROTA}"
		raise frappe.Redirect

	if not user_has_access(ROTA):
		frappe.throw(_("Você não tem permissão para acessar esta página."), frappe.PermissionError)

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
	context.sidebar_title = "Painel do Responsável"
	context.active_link = ROTA
	context.titulo = "Contribuições dos meus beneficiários"

	meses = normalizar_meses(frappe.form_dict.get("meses") or MESES_PADRAO)
	context.meses_selecionado = str(meses)
	context.opcoes_periodo = OPCOES_PERIODO

	responsavel = get_responsavel_do_usuario(frappe.session.user)
	beneficiarios = get_beneficiarios_associados(responsavel)

	apuracoes = apurar_associados(beneficiarios, meses) if beneficiarios else []
	links = _links_de_pagamento([a["id"] for a in apuracoes])

	for apuracao in apuracoes:
		pendentes = competencias_pendentes(apuracao)
		apuracao["pendentes"] = pendentes
		apuracao["total_pendente"] = round(sum(p["valor"] for p in pendentes), 2)
		apuracao["meses_em_atraso"] = len([p for p in pendentes if p["status"] == STATUS_ATRASADO])
		apuracao["link_pagamento"] = links.get(apuracao["id"])
		# O mês a mês fica do mais recente para o mais antigo: o que interessa a
		# quem paga é o mês corrente, não o começo da janela apurada.
		apuracao["linhas_recentes"] = list(reversed(apuracao["linhas"]))

	context.beneficiarios = apuracoes
	context.tem_vinculo = bool(beneficiarios)
	context.total_pendente = round(sum(a["total_pendente"] for a in apuracoes), 2)
	context.em_dia = all(
		a["situacao"] not in (STATUS_ATRASADO, STATUS_PARCIAL) for a in apuracoes
	)

	return context


def _links_de_pagamento(associados: list[str]) -> dict[str, str]:
	"""Link da cobrança em aberto mais recente de cada beneficiário.

	Só entra cobrança ainda pendente e com link: a paga não tem o que cobrar e a
	que deu erro na InfinitePay levaria o responsável a uma página quebrada.
	"""
	if not associados:
		return {}

	cobrancas = frappe.get_all(
		"Cobranca Infinitepay",
		filters={
			"associado": ["in", associados],
			"finalidade": FINALIDADE_CONTRIBUICAO,
			"status": "Pendente",
			"link_pagamento": ["!=", ""],
		},
		fields=["associado", "link_pagamento", "creation"],
		order_by="creation asc",
	)
	# Ordem crescente com sobrescrita deixa a cobrança mais recente por último.
	return {c.associado: c.link_pagamento for c in cobrancas}
