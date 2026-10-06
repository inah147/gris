import frappe

from gris.api.acessos.gestao import opcoes_de_associados, opcoes_de_papel_aprovador, resumo
from gris.api.acessos.permissoes import eh_gestor
from gris.api.auth import _has_desk_access
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/acessos/gestao"


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={ROTA}"
		raise frappe.Redirect

	enrich_context(context, ROTA)
	if context.access_denied or not eh_gestor():
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.title = "Gestão de acessos"

	context.resumo = resumo()
	context.cards = context.resumo["cards"]
	# As opções dos selects precisam estar no HTML inicial: o select do design system
	# lê os itens uma vez, na inicialização.
	context.opcoes_papel_aprovador = opcoes_de_papel_aprovador()
	context.opcoes_associados = opcoes_de_associados()
	context.opcoes_papeis_em_massa = [
		{"value": card["name"], "label": card["titulo"]}
		for card in context.cards
		if card["tipo"] == "Papel do Gris" and card["ativo"]
	]
	context.opcoes_ferramentas = [
		{"value": card["name"], "label": card["titulo"]}
		for card in context.cards
		if card["tipo"] == "Ferramenta externa"
	]
	context.tem_desk = _has_desk_access(frappe.session.user)
	return context
