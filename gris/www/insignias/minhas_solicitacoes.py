import frappe

from gris.api.insignias import consultas, permissoes
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/insignias/minhas_solicitacoes"
		raise frappe.Redirect

	permissoes.garantir_solicitante()

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/insignias/minhas_solicitacoes"

	solicitacoes = consultas.minhas_solicitacoes()
	context.solicitacoes = solicitacoes
	context.resumo = consultas.resumo_por_status(solicitacoes)
	context.total_solicitacoes = len(solicitacoes)

	enrich_context(context, "/insignias/minhas_solicitacoes")
	return context
