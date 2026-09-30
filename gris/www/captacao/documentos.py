import frappe

from gris.api.captacao.consultas import documentos_para_captacao
from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/captacao/documentos"
		raise frappe.Redirect

	enrich_context(context, "/captacao/documentos")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/captacao/documentos"

	context.documentos = documentos_para_captacao()
	context.pendentes = sum(1 for doc in context.documentos if doc["situacao"] != "em_dia")
	# A página de envio é só do Gestor da UEL; para os demais o nome vai sem link.
	context.pode_gerir_documentos = user_has_access("/administracao/transparencia")
	return context
