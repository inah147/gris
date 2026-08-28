import frappe
from frappe import _
from frappe.utils import format_date

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def _format_time(value) -> str:
	if not value:
		return ""
	text = str(value)
	if len(text) >= 5:
		return text[:5]
	return text


def _hydrate_festa_row(row: dict) -> dict:
	row["data_formatada"] = format_date(row.get("data"), "dd/MM/yyyy") if row.get("data") else ""
	row["horario_inicio_fmt"] = _format_time(row.get("horario_inicio"))
	row["horario_termino_fmt"] = _format_time(row.get("horario_termino"))
	return row


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/festas/todas_festas"
		raise frappe.Redirect

	if not user_has_access("/festas/todas_festas"):
		frappe.throw(_("Você não tem permissão para acessar Festas."), frappe.PermissionError)

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/festas/todas_festas"
	context.can_criar = user_has_access("/festas/nova_festa")
	em_andamento = frappe.get_all(
		"Festa",
		filters={"status": "Em andamento"},
		fields=["name", "nome_festa", "data", "horario_inicio", "horario_termino"],
		order_by="data asc",
	)
	realizadas = frappe.get_all(
		"Festa",
		filters={"status": "Realizada"},
		fields=["name", "nome_festa", "data"],
		order_by="data desc",
	)
	context.festas_em_andamento = [_hydrate_festa_row(dict(r)) for r in em_andamento]
	context.festas_realizadas = [_hydrate_festa_row(dict(r)) for r in realizadas]
	enrich_context(context, "/festas/todas_festas")
	return context
