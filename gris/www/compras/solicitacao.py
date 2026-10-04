import frappe

from gris.api.compras import consultas
from gris.api.portal_access import enrich_context

no_cache = 1


def get_context(context):
	nome = frappe.form_dict.get("name") or frappe.form_dict.get("id")
	if frappe.session.user == "Guest":
		destino = f"/compras/solicitacao?name={nome}" if nome else "/compras/minhas_solicitacoes"
		frappe.local.flags.redirect_location = f"/login?redirect-to={destino}"
		raise frappe.Redirect

	# `carregar_solicitacao` valida o acesso do usuário ao documento.
	solicitacao = consultas.carregar_solicitacao(nome) if nome else None

	context.solicitacao = solicitacao
	context.nao_encontrada = solicitacao is None
	context.active_link = "/compras/minhas_solicitacoes"

	enrich_context(context, "/compras/solicitacao")
	return context
