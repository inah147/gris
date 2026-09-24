import frappe

from gris.api.gestao_adultos.atribuicoes import pode_gerenciar_funcoes
from gris.api.gestao_adultos.atvs import listar_atvs
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/gestao_adultos/atvs"
		raise frappe.Redirect

	enrich_context(context, "/gestao_adultos/atvs")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/gestao_adultos/atvs"

	context.linhas = listar_atvs()
	context.pode_editar = pode_gerenciar_funcoes()
	return context
