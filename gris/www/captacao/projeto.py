import frappe

from gris.api.captacao.consultas import DOCTYPE, historico_de_versoes, serializar_projeto
from gris.api.captacao.permissoes import perfil_do_usuario, pode_ver
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached
from gris.utils import comentarios

no_cache = 1


def get_context(context):
	name = frappe.form_dict.get("name") or ""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to=/captacao/projeto?name={name}"
		raise frappe.Redirect

	enrich_context(context, "/captacao/projeto")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	if not name or not frappe.db.exists(DOCTYPE, name):
		frappe.local.flags.redirect_location = "/captacao/acompanhamento"
		raise frappe.Redirect

	perfil = perfil_do_usuario()
	doc = frappe.get_doc(DOCTYPE, name)
	if not pode_ver(perfil, doc):
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/captacao/acompanhamento"

	context.projeto = serializar_projeto(doc, perfil)
	context.versoes = historico_de_versoes(doc.name)
	context.comentarios = comentarios.listar(DOCTYPE, doc.name, perfil.user)
	context.titulo_da_pagina = doc.titulo
	return context
