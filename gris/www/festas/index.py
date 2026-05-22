import frappe

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/festas"
		raise frappe.Redirect

	if not user_has_access("/festas"):
		frappe.throw("Você não tem permissão para acessar Festas.", frappe.PermissionError)

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/festas"
	context.can_criar = user_has_access("/festas/nova_festa")
	context.can_ver_todas = user_has_access("/festas/todas_festas")
	context.can_portaria = user_has_access("/festas/portaria")
	enrich_context(context, "/festas")
	return context
