import frappe

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/calendario"
		raise frappe.Redirect

	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Visualizador Calendario", "Gestor Calendario", "System Manager"]):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/calendario"
	enrich_context(context, "/calendario")

	if not user_has_access("/calendario"):
		frappe.local.flags.redirect_location = "/inicio"
		raise frappe.Redirect

	return context
