no_cache = 1

import frappe

from gris.api.portal_access import enrich_context, user_has_access
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

	context.opcoes_instituicao = get_distinct("instituicao")
	context.opcoes_carteira = get_distinct("carteira")
	context.opcoes_categoria = get_distinct("categoria")
	context.opcoes_centro_de_custo = get_distinct("centro_de_custo")
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

	# Filtros vindos da query string
	filters = {}
	request_args = frappe.local.form_dict or {}

	# Paginação
	try:
		page = int(request_args.get("page", 1))
		if page < 1:
			page = 1
	except Exception:
		page = 1
	page_size = 50
	offset = (page - 1) * page_size

	# Filtro de data: usar chaves distintas para evitar estrutura inválida
	data_inicio = request_args.get("data_inicio")
	data_fim = request_args.get("data_fim")
	if data_inicio and data_fim:
		filters["data_deposito"] = ["between", [data_inicio, data_fim]]
	elif data_inicio:
		filters["data_deposito"] = [">=", data_inicio]
	elif data_fim:
		filters["data_deposito"] = ["<=", data_fim]

	for campo in [
		"instituicao",
		"carteira",
		"categoria",
		"centro_de_custo",
		"fixo_variavel",
		"ordinaria_extraordinaria",
		"conta_fixa",
		"repasse_entre_contas",
		"transacao_revisada",
	]:
		valor = request_args.get(campo)
		if valor not in (None, "", "null"):
			filters[campo] = valor

	# Buscar total de transações para paginação
	total_transacoes = frappe.db.count("Transacao Extrato Geral", filters=filters)

	transacoes = frappe.get_all(
		"Transacao Extrato Geral",
		fields=[
			"name",
			"transacao_revisada",
			"timestamp_transacao",
			"valor",
			"descricao",
			"descricao_reduzida",
			"instituicao",
			"carteira",
			"centro_de_custo",
			"categoria",
			"fixo_variavel",
			"ordinaria_extraordinaria",
			"conta_fixa",
			"repasse_entre_contas",
			"data_deposito",
		],
		filters=filters,
		order_by="timestamp_transacao desc",
		limit=page_size,
		start=offset,
	)
	context.transacoes = transacoes
	context.filtros_ativos = request_args
	context.paginacao = {
		"pagina_atual": page,
		"tamanho_pagina": page_size,
		"total": total_transacoes,
		"tem_proxima": offset + page_size < total_transacoes,
		"tem_anterior": page > 1,
	}

	return context
