import frappe

from gris.api.captacao.consultas import DOCTYPE, serializar_projeto, tipos_de_projeto
from gris.api.captacao.permissoes import eh_proponente, perfil_do_usuario
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached
from gris.captacao_de_recursos.doctype.projeto_de_captacao.projeto_de_captacao import (
	STATUS_PRELIMINAR,
	identificar_proponente,
)

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/captacao/nova_ideia"
		raise frappe.Redirect

	enrich_context(context, "/captacao/nova_ideia")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/captacao/nova_ideia"

	# Primeira opção vazia: o select do design system escolhe sozinho a primeira
	# opção ao inicializar, e a ideia sairia com um tipo que ninguém escolheu.
	context.tipo_items = [{"label": "Escolha o tipo", "value": ""}] + [
		{"label": tipo["label"], "value": tipo["value"]} for tipo in tipos_de_projeto()
	]
	context.tipos = tipos_de_projeto()
	context.projeto = None
	# Só para mostrar: quem grava o proponente é o `before_insert`, com a sessão.
	proponente = identificar_proponente(frappe.session.user)
	context.proponente_nome = proponente["nome"]
	context.proponente_tipo = {"Associado": "Associado", "Responsavel": "Responsável"}.get(
		proponente["tipo"], ""
	)

	# `?name=`: a Diretoria pediu alteração e o proponente reabre a ideia.
	name = frappe.form_dict.get("name")
	if name:
		if not frappe.db.exists(DOCTYPE, name):
			raise frappe.DoesNotExistError
		perfil = perfil_do_usuario()
		doc = frappe.get_doc(DOCTYPE, name)
		if not (perfil.admin or eh_proponente(perfil, doc)) or doc.status != STATUS_PRELIMINAR:
			frappe.local.flags.redirect_location = f"/captacao/projeto?name={doc.name}"
			raise frappe.Redirect
		context.projeto = serializar_projeto(doc, perfil)
		context.proponente_nome = doc.proponente_nome
		context.proponente_tipo = {"Associado": "Associado", "Responsavel": "Responsável"}.get(
			doc.proponente_tipo, ""
		)
	return context
