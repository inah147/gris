import frappe

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	frappe.throw("Página indisponível", frappe.PageDoesNotExistError)

	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/calendario/importar"
		raise frappe.Redirect

	roles = frappe.get_roles(frappe.session.user)
	if "Gestor Calendario" not in roles and "System Manager" not in roles:
		frappe.throw("Acesso permitido apenas para Gestor de Calendário.", frappe.PermissionError)

	# Enrich + permissão
	enrich_context(context, "/calendario/importar")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect
	# Logo
	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	# Link ativo
	context.active_link = "/calendario/importar"
	return context
