import frappe

from gris.api.financeiro.previsao_orcamentaria import pode_gerir
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

PAGE_PATH = "/financeiro/previsao_orcamentaria"


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

	# Previsão exibida: a informada na query string ou a mais recente cadastrada.
	request_args = frappe.local.form_dict or {}
	selecionada = request_args.get("previsao")
	nomes = {p["name"] for p in previsoes}
	if selecionada not in nomes:
		selecionada = previsoes[0]["name"] if previsoes else None
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
