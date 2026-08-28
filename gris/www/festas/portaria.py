# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Página /festas/portaria — operação de entrada da festa (scan QR, vendas)."""

from __future__ import annotations

import frappe
from frappe import _

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached
from gris.festas.utils.portaria import (
	festas_que_user_pode_operar,
	user_pode_operar_portaria,
)

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/festas/portaria"
		raise frappe.Redirect

	# Combina checagem por role (PAGE_ROLES) com checagem por área da Portaria
	# (membros/coordenadores). Se o usuário não tem role mas é membro de
	# alguma Area Portaria de festa ativa, ainda assim entra.
	festas = festas_que_user_pode_operar(frappe.session.user)
	tem_acesso_global = user_pode_operar_portaria(frappe.session.user)
	if not tem_acesso_global and not festas:
		frappe.throw(
			_("Você não tem permissão para acessar a Portaria."),
			frappe.PermissionError,
		)

	context.title = "Portaria"
	context.active_link = "/festas"
	context.no_cache = 1

	uel_data = get_uel_cached() or {}
	context.portal_logo = uel_data.get("logo")
	nome_uel = uel_data.get("nome_da_uel")
	context.sidebar_title = f"{uel_data.get('tipo_uel')} {nome_uel}" if nome_uel else "Portal"

	context.portal_breadcrumbs = [
		{"label": "Festas", "url": "/festas/todas_festas"},
		{"label": "Portaria"},
	]

	# Festas que o user pode operar; se só uma, será auto-selecionada no JS.
	context.festas_ativas = festas
	context.festas_select_items = [
		{
			"label": f["nome_festa"],
			"value": f["name"],
			"type": "item",
		}
		for f in festas
	]

	enrich_context(context, "/festas/portaria")
	return context
