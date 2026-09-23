import frappe

from gris.api.administracao.consultas import listar_funcoes
from gris.api.administracao.permissoes import pode_gerenciar_estrutura
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

#: Mesmo conjunto do Select `Funcao Voluntario.categoria`, cujo rótulo é "Linha".
LINHAS = ("Dirigente", "Escotista", "Colaborador")


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/administracao/funcoes"
		raise frappe.Redirect

	enrich_context(context, "/administracao/funcoes")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/administracao/funcoes"

	context.funcoes = listar_funcoes()
	context.pode_editar = pode_gerenciar_estrutura()
	# Primeira opção vazia: o select do design system escolhe sozinho a primeira
	# opção ao inicializar, em silêncio. Sem ela, uma função sem linha definida
	# apareceria como "Dirigente" e o save gravaria isso.
	context.linha_items = [
		{"label": "Sem linha definida", "value": ""},
		*({"label": linha, "value": linha} for linha in LINHAS),
	]
	return context
