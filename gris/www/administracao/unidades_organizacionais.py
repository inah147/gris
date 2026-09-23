import frappe

from gris.api.administracao.consultas import (
	listar_unidades,
	opcoes_de_funcao,
	opcoes_de_responsavel,
)
from gris.api.administracao.permissoes import pode_gerenciar_estrutura
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		redirect = "/login?redirect-to=/administracao/unidades_organizacionais"
		frappe.local.flags.redirect_location = redirect
		raise frappe.Redirect

	enrich_context(context, "/administracao/unidades_organizacionais")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/administracao/unidades_organizacionais"

	# A página inteira é renderizada a partir deste payload, nos dois modos de
	# visualização: a estrutura é pequena e cabe numa carga só.
	context.unidades = listar_unidades()
	context.pode_editar = pode_gerenciar_estrutura()
	context.opcoes_responsavel = opcoes_de_responsavel() if context.pode_editar else []
	context.opcoes_funcao = opcoes_de_funcao() if context.pode_editar else []
	return context
