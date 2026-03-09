import frappe

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/gestao_adultos/minha_entrevista"
		raise frappe.Redirect

	enrich_context(context, "/gestao_adultos/minha_entrevista")

	associado = frappe.db.get_value("Associado", {"id_escoteiros": frappe.session.user}, "name")
	if not associado:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	entrevista_name = frappe.db.get_value("Entrevista por Competencias", {"associado": associado}, "name")
	if not entrevista_name:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/gestao_adultos/minha_entrevista"
	context.entrevista_name = entrevista_name
	return context
