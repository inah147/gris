import frappe

from gris.api.assembleias import constantes as c
from gris.api.assembleias.endpoints import contagem_de_inscricoes
from gris.api.assembleias.pagina import dados_da_pagina
from gris.api.assembleias.permissoes import pode_gerenciar_assembleias
from gris.api.assembleias.pessoas import opcoes_de_pessoas
from gris.api.assembleias.votantes import dados_da_lista
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/administracao/assembleias/assembleia"


def get_context(context):
	name = frappe.form_dict.get("name") or ""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={ROTA}?name={name}"
		raise frappe.Redirect

	enrich_context(context, ROTA)
	if context.access_denied or not pode_gerenciar_assembleias():
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	if not name or not frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, name):
		frappe.local.flags.redirect_location = "/administracao/assembleias"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/administracao/assembleias"

	doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, name)
	context.assembleia = doc
	context.dados = dados_da_pagina(doc)
	context.inscricoes = contagem_de_inscricoes(name)
	context.tipo_items = [{"label": t, "value": t} for t in (c.TIPO_ORDINARIA, c.TIPO_EXTRAORDINARIA)]
	context.pessoas_18 = opcoes_de_pessoas(18, doc.data)
	context.pessoas_todas = opcoes_de_pessoas(0, doc.data)
	context.lista = dados_da_lista(doc)
	context.finalidades = [
		{"label": "Sem finalidade", "value": ""},
		*({"label": f, "value": f} for f in c.FINALIDADES),
	]
	context.orientacoes = {
		"por_finalidade": c.ORIENTACAO_POR_FINALIDADE,
		"simples": c.ORIENTACAO_APROVACAO_SIMPLES,
	}
	return context
