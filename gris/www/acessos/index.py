import frappe

from gris.api.acessos.catalogo import dados_do_portal
from gris.api.acessos.permissoes import pode_usar_portal
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/acessos"


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={ROTA}"
		raise frappe.Redirect

	enrich_context(context, ROTA)
	if context.access_denied or not pode_usar_portal():
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.title = "Meus acessos"
	context.payload = dados_do_portal(frappe.session.user)
	return context
