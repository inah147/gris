from __future__ import annotations

import frappe

from gris.api.festas.relatorio import build_relatorio_payload, relatorio_disponivel
from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/festas/relatorio"
		raise frappe.Redirect

	if not user_has_access("/festas/relatorio"):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		nome_uel = uel_data.get("nome_da_uel")
		context.sidebar_title = f"{uel_data.get('tipo_uel')} {nome_uel}" if nome_uel else "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/festas"
	festa_name = frappe.form_dict.get("name")

	if not festa_name:
		context.not_found = True
		context.missing_reason = "Parâmetro 'name' não informado."
		enrich_context(context, "/festas/relatorio")
		return context

	if not frappe.db.exists("Festa", festa_name):
		context.not_found = True
		context.missing_reason = "Festa não encontrada."
		enrich_context(context, "/festas/relatorio")
		return context

	if not frappe.has_permission("Festa", "read", festa_name):
		frappe.throw("Sem permissão para acessar esta festa.", frappe.PermissionError)

	nome_festa = frappe.db.get_value("Festa", festa_name, "nome_festa") or festa_name
	context.festa_name = festa_name
	context.nome_festa = nome_festa
	context.portal_breadcrumbs = [
		{"label": "Festas", "url": "/festas/todas_festas"},
		{"label": nome_festa, "url": f"/festas/festa?name={festa_name}"},
		{"label": "Relatório"},
	]

	# Gate: o relatório só fica disponível após o início da avaliação da equipe.
	if not relatorio_disponivel(festa_name):
		context.indisponivel = True
		enrich_context(context, "/festas/relatorio")
		return context

	payload = build_relatorio_payload(festa_name)
	for key, value in payload.items():
		setattr(context, key, value)

	enrich_context(context, "/festas/relatorio")
	return context
