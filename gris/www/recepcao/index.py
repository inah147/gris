import frappe

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/recepcao"
		raise frappe.Redirect

	if not user_has_access("/recepcao"):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	roles = frappe.get_roles(frappe.session.user)
	if "Recepcao" not in roles and "System Manager" not in roles:
		frappe.throw("Acesso permitido apenas para Recepção.", frappe.PermissionError)

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
	context.active_link = "/recepcao"
	enrich_context(context, "/recepcao")
	return context
