import frappe
from frappe.utils import format_datetime

from gris.api.gestao_adultos.endpoints import build_entrevista_payload
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

	payload = build_entrevista_payload(entrevista_name)
	context.form_config = payload["config"]
	context.entrevista = payload["entrevista"]
	context.entrevista_updated_label = (
		format_datetime(context.entrevista.get("data_da_ultima_atualizacao"))
		if context.entrevista.get("data_da_ultima_atualizacao")
		else None
	)

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/gestao_adultos/minha_entrevista"
	return context
