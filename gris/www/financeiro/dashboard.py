"""Financeiro Dashboard Web Page (context only).
All whitelisted data functions moved to `gris.api.financeiro.dashboard`.
"""

import frappe

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def _format_brl(v: float) -> str:
	try:
		return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
	except Exception:
		return f"R$ {v}"


def _get_total_amount() -> float:
	try:
		pre_tx = frappe.get_all(
			"Transacao Extrato Geral",
			fields=["SUM(valor) as total"],
			filters={"metodo": ["!=", "Dinheiro"]},
			limit_page_length=0,
		)
		total_extrato = pre_tx[0].get("total") or 0.0 if pre_tx else 0.0

		pre_carteiras = frappe.get_all(
			"Carteira",
			fields=["SUM(saldo_inicial) as total"],
			limit_page_length=0,
		)
		total_saldo_inicial = pre_carteiras[0].get("total") or 0.0 if pre_carteiras else 0.0

		return float(total_extrato) + float(total_saldo_inicial)
	except Exception:
		return 0.0


def _distinct_list(field: str) -> list:
	try:
		rows = frappe.get_all(
			"Transacao Extrato Geral",
			fields=[f"distinct {field} as val"],
			filters={field: ["is", "set"], "metodo": ["!=", "Dinheiro"]},
			order_by=f"{field} asc",
			limit_page_length=0,
		)
		return [r.get("val") for r in rows if r.get("val")]
	except Exception:
		return []


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/financeiro/dashboard"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		context.sidebar_title = (
			f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
			if uel_data.get("nome_da_uel")
			else "Portal"
		)
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/financeiro/dashboard"
	enrich_context(context, "/financeiro/dashboard")

	context.total_amount = _get_total_amount()
	context.total_amount_fmt = _format_brl(context.total_amount)

	context.filter_categorias = _distinct_list("categoria")
	context.filter_instituicoes = _distinct_list("instituicao")
	context.filter_carteiras = _distinct_list("carteira")
	context.filter_centros_custo = _distinct_list("centro_de_custo")

	return context
