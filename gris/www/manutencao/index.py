import frappe

no_cache = 1


def get_context(context):
	"""A raiz do módulo não tem tela própria: leva direto para as próximas manutenções."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/manutencao/acompanhamento"
		raise frappe.Redirect

	frappe.local.flags.redirect_location = "/manutencao/acompanhamento"
	raise frappe.Redirect
