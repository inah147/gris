import frappe

from gris.api.portal_access import enrich_context, user_has_access


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/responsavel"
		raise frappe.Redirect

	if not user_has_access("/responsavel"):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	context.sidebar_title = "Painel do Responsável"
	context.active_link = "/responsavel"
	context.can_access_pesquisa_novos = user_has_access("/responsavel/pesquisa_novos")

	enrich_context(context, "/responsavel")

	return context
