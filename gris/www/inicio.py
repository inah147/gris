import frappe

from gris.api.portal_access import PORTAL_MODULE_ICON_MAP, enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/inicio"
		raise frappe.Redirect
	# Recupera logo e define para sidebar
	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"
	context.active_link = "/inicio"
	context.module_icons = PORTAL_MODULE_ICON_MAP
	enrich_context(context, "/inicio")
	# Flags para controlar exibição de cards na página inicial
	context.can_associados = user_has_access("/associados")
	context.can_financeiro = user_has_access("/financeiro")
	context.can_transparencia = user_has_access("/portal_transparencia")
	context.can_calendario = user_has_access("/calendario")
	context.can_responsavel = user_has_access("/responsavel")
	context.can_recepcao = user_has_access("/recepcao")
	context.can_gestao_adultos = user_has_access("/gestao_adultos")
	context.can_projetos = user_has_access("/projetos")
	context.can_festas = user_has_access("/festas")
	context.can_gestao_tarefas = user_has_access("/gestao_tarefas")
	return context
