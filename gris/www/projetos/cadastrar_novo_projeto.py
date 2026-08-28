import frappe
from frappe import _

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


ALLOWED_ROLES = {"Editor de projetos", "System Manager"}


def _ensure_editor_access() -> None:
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & ALLOWED_ROLES):
		frappe.throw(_("Você não tem permissão para cadastrar ou editar projetos."), frappe.PermissionError)


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/projetos/cadastrar_novo_projeto"
		raise frappe.Redirect

	_ensure_editor_access()

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/projetos/cadastrar_novo_projeto"
	context.projeto_name = (frappe.form_dict.get("projeto") or "").strip()
	enrich_context(context, "/projetos/cadastrar_novo_projeto")
	return context
