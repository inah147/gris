import frappe

from gris.api.captacao.consultas import listar_kanban
from gris.api.captacao.permissoes import perfil_do_usuario
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/captacao/acompanhamento"
		raise frappe.Redirect

	enrich_context(context, "/captacao/acompanhamento")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/captacao/acompanhamento"

	# O quadro já vem montado no HTML: sem "Carregando..." na primeira pintura. O JS
	# só volta ao servidor para mover um card.
	context.kanban = listar_kanban(perfil_do_usuario())
	return context
