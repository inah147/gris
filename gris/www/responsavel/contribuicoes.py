"""Contribuições mensais dos beneficiários, na visão do responsável.

O responsável vê aqui exatamente os beneficiários vinculados a ele, com o mês a
mês do que está pago e do que está em atraso. A apuração é a mesma da tela do
financeiro e da página pública (`gris.api.financeiro.pagamentos_contribuicao`, lida
do Pagamento Contribuicao Mensal) — o que muda é o recorte: nada que não seja de um
beneficiário vinculado entra nesta página. O botão de pagar leva à página pública da
contribuição, que entrega o link da InfinitePay com o valor do dia.
"""

import frappe
from frappe import _

from gris.api.financeiro.contribuicao_token import url_publica
from gris.api.financeiro.contribuicoes import MESES_PADRAO_TELA, normalizar_meses
from gris.api.financeiro.pagamentos_contribuicao import (
	STATUS_ATRASADO,
	STATUS_NAO_GERADO,
	apurar_associados,
	competencias_pendentes,
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

	meses = normalizar_meses(frappe.form_dict.get("meses"), MESES_PADRAO_TELA)
	context.meses_selecionado = str(meses)
	context.opcoes_periodo = OPCOES_PERIODO

	responsavel = get_responsavel_do_usuario(frappe.session.user)
	beneficiarios = get_beneficiarios_associados(responsavel)

	apuracoes = apurar_associados(beneficiarios, meses) if beneficiarios else []

	for apuracao in apuracoes:
		pendentes = competencias_pendentes(apuracao)
		apuracao["pendentes"] = pendentes
		apuracao["total_pendente"] = round(sum(p["valor"] for p in pendentes), 2)
		apuracao["meses_em_atraso"] = len([p for p in pendentes if p["status"] == STATUS_ATRASADO])
		# O pagamento passa pela página pública do GRIS, não pelo link da InfinitePay.
		apuracao["link_pagamento"] = url_publica(apuracao["id"]) if pendentes else None
		# O mês a mês fica do mais recente para o mais antigo, sem os meses que ainda
		# não foram gerados: o que interessa a quem paga é o mês corrente.
		apuracao["linhas_recentes"] = [
			linha for linha in reversed(apuracao["linhas"]) if linha["status"] != STATUS_NAO_GERADO
		]

	context.beneficiarios = apuracoes
	context.tem_vinculo = bool(beneficiarios)
	context.total_pendente = round(sum(a["total_pendente"] for a in apuracoes), 2)
	context.em_dia = all(a["situacao"] != STATUS_ATRASADO for a in apuracoes)

	return context
