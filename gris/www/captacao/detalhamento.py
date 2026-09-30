import frappe

from gris.api.captacao.consultas import DOCTYPE, serializar_projeto
from gris.api.captacao.permissoes import perfil_do_usuario
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	name = frappe.form_dict.get("name") or ""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to=/captacao/detalhamento?name={name}"
		raise frappe.Redirect

	enrich_context(context, "/captacao/detalhamento")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	if not name or not frappe.db.exists(DOCTYPE, name):
		frappe.local.flags.redirect_location = "/captacao/acompanhamento"
		raise frappe.Redirect

	perfil = perfil_do_usuario()
	doc = frappe.get_doc(DOCTYPE, name)
	projeto = serializar_projeto(doc, perfil)

	# O mesmo formulário serve ao proponente (rascunho e envio) e à Relações
	# Institucionais (alteração manual com motivo). Fora disso, volta para o projeto.
	if projeto["acoes"]["detalhar"]:
		context.modo = "proponente"
	elif projeto["acoes"]["revisar"]:
		context.modo = "revisao"
	else:
		frappe.local.flags.redirect_location = f"/captacao/projeto?name={doc.name}"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/captacao/acompanhamento"
	context.projeto = projeto
	context.titulo_da_pagina = doc.titulo
	return context
