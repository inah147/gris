from __future__ import annotations

import frappe

from gris.api.gestao_de_tarefas.quadros import listar_quadros_publicos
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	request_path = (getattr(frappe.local, "request", None) and frappe.local.request.path) or ""
	if request_path.endswith((".css", ".js")):
		return context

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/gestao_tarefas"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/gestao_tarefas"
	context.page_title = "Gestao de Tarefas"
	context.quadros = listar_quadros_publicos()
	context.current_user = frappe.session.user
	enrich_context(context, "/gestao_tarefas")
	return context
