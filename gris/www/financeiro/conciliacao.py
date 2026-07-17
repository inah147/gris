no_cache = 1

import frappe
from frappe import _

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/financeiro/conciliacao"
		raise frappe.Redirect

	# Logo / título da sidebar
	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/financeiro/conciliacao"
	enrich_context(context, "/financeiro/conciliacao")
	context.title = _("Conciliação")

	def get_master_options(doctype):
		return [
			r["name"]
			for r in frappe.get_all(doctype, fields=["name"], order_by="name")
			if r.get("name")
		]

	context.opcoes_categoria = get_master_options("Categoria de Transacao")
	context.opcoes_centro_de_custo = get_master_options("Centro de Custo")

	# Opções de filtro (carteira/instituição das transações de sistema pendentes)
	context.opcoes_carteira = [
		r["carteira"]
		for r in frappe.get_all(
			"Transacao Extrato Geral",
			fields=["carteira"],
			filters={"fonte": "Sistema"},
			distinct=True,
			order_by="carteira",
		)
		if r.get("carteira")
	]

	return context
