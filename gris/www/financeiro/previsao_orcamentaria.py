import frappe
from frappe.utils import getdate

from gris.api.financeiro.previsao_orcamentaria import pode_gerir
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

PAGE_PATH = "/financeiro/previsao_orcamentaria"


def previsao_padrao(previsoes: list[dict]) -> str | None:
	"""Previsão aberta quando a URL não pede uma específica.

	Prioriza a que cobre a data de hoje — ordenar só por exercício abriria o rascunho
	do ano seguinte, uma tela de zeros, e esconderia o orçamento vigente no seletor.
	Sem previsão vigente, cai na mais recente já aprovada e, por fim, na primeira da
	lista (que vem ordenada do maior exercício para o menor).
	"""
	if not previsoes:
		return None

	hoje = getdate()
	vigentes = [p for p in previsoes if getdate(p["data_inicio"]) <= hoje <= getdate(p["data_fim"])]
	candidatas = [p for p in vigentes if p["status"] == "Aprovada"] or vigentes
	if not candidatas:
		candidatas = [p for p in previsoes if p["status"] == "Aprovada"] or previsoes
	return candidatas[0]["name"]


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={PAGE_PATH}"
		raise frappe.Redirect

	# Recupera logo e define para sidebar
	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"
	context.active_link = PAGE_PATH
	enrich_context(context, PAGE_PATH)

	# Usuário autenticado sem as roles de PAGE_ROLES: manda para /403 em vez de
	# carregar (e renderizar) dados financeiros.
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	context.can_edit_financeiro = pode_gerir()

	previsoes = frappe.get_all(
		"Previsao Orcamentaria",
		fields=["name", "titulo", "exercicio", "status", "data_inicio", "data_fim"],
		order_by="exercicio desc, data_inicio desc",
		limit_page_length=0,
	)
	context.previsoes = previsoes

	# Previsão exibida: a informada na query string ou a escolhida por `previsao_padrao`.
	request_args = frappe.local.form_dict or {}
	selecionada = request_args.get("previsao")
	nomes = {p["name"] for p in previsoes}
	if selecionada not in nomes:
		selecionada = previsao_padrao(previsoes)
	context.previsao_selecionada = selecionada

	context.previsao = frappe.get_doc("Previsao Orcamentaria", selecionada) if selecionada else None

	# Opções dos formulários de item
	context.categorias = [
		c["name"]
		for c in frappe.get_all(
			"Categoria de Transacao", fields=["name"], order_by="name asc", limit_page_length=0
		)
	]
	context.centros_de_custo = [
		c["name"]
		for c in frappe.get_all("Centro de Custo", fields=["name"], order_by="name asc", limit_page_length=0)
	]

	return context
