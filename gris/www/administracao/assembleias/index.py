import frappe

from gris.api.assembleias.constantes import TIPO_EXTRAORDINARIA, TIPO_ORDINARIA
from gris.api.assembleias.endpoints import listar_assembleias
from gris.api.assembleias.padroes import configuracoes
from gris.api.assembleias.permissoes import pode_gerenciar_assembleias
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/administracao/assembleias"


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={ROTA}"
		raise frappe.Redirect

	enrich_context(context, ROTA)
	if context.access_denied or not pode_gerenciar_assembleias():
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = ROTA

	assembleias = listar_assembleias()
	context.proximas = assembleias["proximas"]
	context.realizadas = assembleias["realizadas"]
	context.local_padrao = configuracoes().local_padrao or ""
	context.hoje = str(frappe.utils.getdate())
	context.tipo_items = [{"label": tipo, "value": tipo} for tipo in (TIPO_ORDINARIA, TIPO_EXTRAORDINARIA)]
	return context
