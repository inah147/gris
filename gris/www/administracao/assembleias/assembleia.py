from urllib.parse import quote

import frappe
from frappe.utils import get_url

from gris.api.assembleias import constantes as c
from gris.api.assembleias.ata import dados_da_ata
from gris.api.assembleias.endpoints import contagem_de_inscricoes
from gris.api.assembleias.formularios import listar_inscricoes
from gris.api.assembleias.padroes import configuracoes
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
	context.link_sessao = get_url(f"/assembleias/sessao?assembleia={quote(name)}")
	context.dados = dados_da_pagina(doc)
	context.inscricoes = contagem_de_inscricoes(name)
	context.tipo_items = [{"label": t, "value": t} for t in (c.TIPO_ORDINARIA, c.TIPO_EXTRAORDINARIA)]
	context.pessoas_18 = opcoes_de_pessoas(18, doc.data)
	context.pessoas_todas = opcoes_de_pessoas(0, doc.data)
	context.lista = dados_da_lista(doc)
	context.pessoas_16 = opcoes_de_pessoas(16, doc.data)
	context.ata = dados_da_ata(doc)
	config = configuracoes()
	context.inscricoes_dados = {
		**listar_inscricoes(name),
		"vagas_delegados": doc.vagas_delegados or 0,
		"titulares_cf": config.vagas_comissao_fiscal or 0,
		"suplentes_cf": config.suplentes_comissao_fiscal or 0,
	}
	abrem_formulario = set(c.FINALIDADE_DO_FORMULARIO.values())
	context.finalidades = [
		{"label": "Sem finalidade", "value": "", "descricao": c.DESCRICAO_DA_FINALIDADE[""]},
		*(
			{
				"label": f,
				"value": f,
				"descricao": c.DESCRICAO_DA_FINALIDADE.get(f, ""),
				"abre_formulario": f in abrem_formulario,
			}
			for f in c.FINALIDADES
		),
	]
	return context
