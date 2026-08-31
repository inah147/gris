"""Contribuições mensais apuradas a partir das transações do extrato geral."""

import json

import frappe

from gris.api.financeiro.contribuicoes import (
	MESES_PADRAO,
	STATUS_AGUARDANDO,
	STATUS_ATRASADO,
	STATUS_EM_ABERTO,
	STATUS_NAO_APLICAVEL,
	STATUS_PAGO,
	STATUS_PARCIAL,
	apurar,
	normalizar_meses,
)
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

# Janelas de apuração oferecidas no filtro da página.
OPCOES_PERIODO = [
	{"label": "Últimos 6 meses", "value": "6"},
	{"label": "Últimos 12 meses", "value": "12"},
	{"label": "Últimos 24 meses", "value": "24"},
]

# Ordem de exibição na tela, do mais urgente ao resolvido.
ORDEM_EXIBICAO = [
	STATUS_ATRASADO,
	STATUS_PARCIAL,
	STATUS_EM_ABERTO,
	STATUS_AGUARDANDO,
	STATUS_PAGO,
	STATUS_NAO_APLICAVEL,
]


def get_context(context):
	enrich_context(context, "/financeiro/contribuicoes")

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/financeiro"
		raise frappe.Redirect

	# Usuário autenticado sem uma das roles de PAGE_ROLES: 403 em vez de voltar
	# ao login, que só produziria um laço de redirecionamento.
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/financeiro/contribuicoes"
	context.titulo = "Contribuições Mensais"

	meses = normalizar_meses(frappe.form_dict.get("meses") or MESES_PADRAO)
	# Sem dados de cobrança: e-mail e telefone são do detalhe do contribuinte
	# (/financeiro/contribuicao), que só os entrega a quem pode geri-los.
	apuracao = apurar(meses)

	context.meses_selecionado = str(meses)
	context.opcoes_periodo = OPCOES_PERIODO
	context.apuracao = apuracao
	context.totais = apuracao["totais"]
	context.nao_vinculadas = apuracao["nao_vinculadas"]
	context.associados_por_situacao = _agrupar_por_situacao(apuracao["associados"])
	context.ordem_situacao = ORDEM_EXIBICAO
	# Payload consumido pelos gráficos ECharts em contribuicoes.js. O escape de "<"
	# impede que um "</script>" em qualquer valor feche o bloco antes da hora.
	context.dados_graficos = json.dumps(
		{
			"series": apuracao["series"],
			"totais": apuracao["totais"],
		}
	).replace("<", "\\u003c")

	return context


def _agrupar_por_situacao(associados: list[dict]) -> dict[str, list[dict]]:
	"""Agrupa os contribuintes pela situação apurada, preservando a ordem alfabética."""
	agrupado: dict[str, list[dict]] = {situacao: [] for situacao in ORDEM_EXIBICAO}
	for associado in associados:
		agrupado.setdefault(associado["situacao"], []).append(associado)
	return agrupado
