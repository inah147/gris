import frappe

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/projetos/projeto_aprovado"
		raise frappe.Redirect

	if not (user_has_access("/projetos/projeto_aprovado") or user_has_access("/projetos/aprovacao_projeto")):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	projeto_name = (frappe.form_dict.get("projeto") or "").strip()
	if not projeto_name:
		frappe.throw("Projeto não informado.")

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/projetos/visao_geral"
	context.projeto_name = projeto_name
	enrich_context(context, "/projetos/projeto_aprovado")
	return context
