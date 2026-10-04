"""Página pública /contribuicao/<código>.

É o link que o WhatsApp leva, um por beneficiário. Sem login e sem sidebar: mostra
o mês a mês e entrega o link da InfinitePay com o valor do dia (`iniciar_pagamento`).
Código inexistente devolve a mesma página de "não encontrado" de qualquer rota
inexistente, sem revelar se o código já existiu. Nenhum dado de contato aparece aqui.
"""

import frappe
from frappe import _

from gris.api.financeiro.contribuicao_publica import montar_pagina
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	context.title = "Contribuição mensal"
	context.show_sidebar = False
	context.no_header = True
	context.no_footer = True

	token = (frappe.form_dict.get("token") or "").strip()
	pagina = montar_pagina(token)
	if not pagina:
		frappe.throw(_("Página indisponível"), frappe.PageDoesNotExistError)

	uel_data = get_uel_cached() or {}
	context.token = token
	context.pagina = pagina
	context.portal_logo = uel_data.get("logo")
	context.uel = {
		"tipo_uel": uel_data.get("tipo_uel") or "",
		"nome_da_uel": uel_data.get("nome_da_uel") or "",
		"numeral": uel_data.get("numeral") or "",
		"regiao": uel_data.get("regiao") or "",
	}
	# `noindex` e `no-referrer` também no HTML; os cabeçalhos saem do after_request.
	context.head_html = (
		'<meta name="robots" content="noindex, nofollow"><meta name="referrer" content="no-referrer">'
	)
	return context
