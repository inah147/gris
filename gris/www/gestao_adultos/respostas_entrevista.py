import frappe
from frappe.utils import format_datetime

from gris.api.gestao_adultos.endpoints import ALERT_CATEGORY_DEFINITIONS, build_entrevista_payload
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def _build_alert_groups(alertas):
	grouped = {
		item["key"]: {"key": item["key"], "label": item["label"], "items": []}
		for item in ALERT_CATEGORY_DEFINITIONS
	}

	for alerta in alertas or []:
		categorias = alerta.get("categorias") or []
		if "alerta_geral" in categorias:
			categorias = ["alerta_geral"]

		for categoria in categorias:
			if categoria in grouped:
				grouped[categoria]["items"].append(alerta)

	return [grouped[item["key"]] for item in ALERT_CATEGORY_DEFINITIONS if grouped[item["key"]]["items"]]


def _build_score_rows(entrevista):
	category_counts = {item["key"]: 0 for item in ALERT_CATEGORY_DEFINITIONS if item["key"] != "alerta_geral"}
	general_alerts_count = 0

	for alerta in entrevista.get("alertas") or []:
		categorias = alerta.get("categorias") or []
		if "alerta_geral" in categorias:
			general_alerts_count += 1
			categorias = ["alerta_geral"]

		for categoria in categorias:
			if categoria in category_counts:
				category_counts[categoria] += 1

	rows = []
	for item in ALERT_CATEGORY_DEFINITIONS:
		if item["key"] == "alerta_geral":
			continue

		alertas_categoria = category_counts.get(item["key"], 0)
		score = int(entrevista.get(item["key"]) or 0)
		rows.append(
			{
				"key": item["key"],
				"label": item["label"],
				"score": score,
				"alertas_categoria": alertas_categoria,
				"alertas_totais": alertas_categoria + general_alerts_count,
			}
		)

	rows.sort(key=lambda row: row["score"], reverse=True)
	return rows


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/gestao_adultos/respostas_entrevista"
		raise frappe.Redirect

	enrich_context(context, "/gestao_adultos/respostas_entrevista")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/gestao_adultos/entrevista_competencias"
	context.entrevista_name = frappe.form_dict.get("name")
	if not context.entrevista_name:
		frappe.local.flags.redirect_location = "/gestao_adultos/entrevista_competencias"
		raise frappe.Redirect

	payload = build_entrevista_payload(context.entrevista_name)
	context.form_config = payload["config"]
	context.entrevista = payload["entrevista"]
	context.alert_groups = _build_alert_groups(context.entrevista)
	context.alert_category_definitions = ALERT_CATEGORY_DEFINITIONS
	context.entrevista_updated_label = (
		format_datetime(context.entrevista.get("data_da_ultima_atualizacao"))
		if context.entrevista.get("data_da_ultima_atualizacao")
		else None
	)
	context.score_rows = _build_score_rows(context.entrevista)
	return context
