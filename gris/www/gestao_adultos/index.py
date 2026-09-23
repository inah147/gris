import frappe

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/gestao_adultos"
		raise frappe.Redirect

	enrich_context(context, "/gestao_adultos")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/gestao_adultos"
	# O índice é aberto a todos por causa do breadcrumb do organograma, então cada
	# card só aparece para quem consegue abrir a página correspondente.
	context.pode_entrevistas = user_has_access("/gestao_adultos/entrevista_competencias")
	return context
