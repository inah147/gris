no_cache = 1

import frappe

from gris.api.financeiro.transactions import (
	EXTRATO_PAGE_SIZE,
	build_extrato_filters,
	get_extrato_colunas,
	get_extrato_opcoes_editaveis,
	get_extrato_transacoes,
)
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Buscar opções únicas para os filtros dropdown
	def get_distinct(field):
		return [
			r[field]
			for r in frappe.get_all("Transacao Extrato Geral", fields=[field], distinct=True, order_by=field)
			if r[field]
		]

	def get_master_options(doctype, field="name", order_by="name"):
		return [r[field] for r in frappe.get_all(doctype, fields=[field], order_by=order_by) if r.get(field)]

	context.opcoes_instituicao = get_distinct("instituicao")
	context.opcoes_carteira = get_distinct("carteira")
	context.opcoes_categoria = get_master_options("Categoria de Transacao")
	context.opcoes_centro_de_custo = get_master_options("Centro de Custo")
	context.opcoes_conta_fixa = get_distinct("conta_fixa")

	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/financeiro/extrato"
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
	context.active_link = "/financeiro/extrato"
	enrich_context(context, "/financeiro/extrato")
	roles = frappe.get_roles()
	context.can_view_full_description = "Gestor Financeiro" in roles

	# Filtros vindos da query string (mesmas chaves usadas pelo scroll infinito)
	request_args = frappe.local.form_dict or {}
	filters = build_extrato_filters(request_args)

	# Total apenas para o contador da tela; a navegação é por scroll infinito.
	total_transacoes = frappe.db.count("Transacao Extrato Geral", filters=filters)

	# Todas as colunas são renderizadas; o seletor da tela apenas mostra/esconde.
	context.colunas = get_extrato_colunas(context.can_view_full_description)

	# Opções dos campos editáveis direto na célula (edição em lote no grid).
	context.opcoes_editaveis = get_extrato_opcoes_editaveis()

	# Primeiro lote renderizado no servidor; os seguintes chegam via
	# gris.api.financeiro.transactions.get_extrato_rows.
	context.transacoes = get_extrato_transacoes(
		filters,
		start=0,
		page_length=EXTRATO_PAGE_SIZE,
		colunas=context.colunas,
	)
	context.filtros_ativos = request_args
	# Quantos filtros a URL trouxe: define se o painel abre e alimenta o badge.
	context.filtros_ativos_count = len(filters)
	context.paginacao = {
		"tamanho_pagina": EXTRATO_PAGE_SIZE,
		"total": total_transacoes,
		"carregadas": len(context.transacoes),
		"tem_mais": len(context.transacoes) < total_transacoes,
	}

	return context
