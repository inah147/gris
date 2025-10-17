import frappe
import pandas as pd

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/financeiro/relatorios"
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
	context.active_link = "/financeiro/relatorios"
	enrich_context(context, "/financeiro/relatorios")

	# Buscar instituições financeiras (todas)
	instituicoes = frappe.get_all(
		"Instituicao Financeira",
		fields=["name", "nome"],
		order_by="nome asc",
		limit_page_length=0,
	)
	instituicoes_nomes = [i["nome"] or i["name"] for i in instituicoes]
	context.instituicoes = instituicoes_nomes

	# Filtros de data vindos da query string
	request_args = frappe.local.form_dict or {}

	from datetime import date

	today = date.today()
	primeiro_dia = today.replace(day=1)
	data_inicio = request_args.get("data_inicio") or primeiro_dia.strftime("%Y-%m-%d")
	data_fim = request_args.get("data_fim") or today.strftime("%Y-%m-%d")

	filters = [["data_deposito", "between", [data_inicio, data_fim]], ["metodo", "!=", "Dinheiro"]]

	# Buscar transações do extrato geral filtradas
	transacoes = frappe.get_all(
		"Transacao Extrato Geral",
		fields=[
			"data_deposito",
			"instituicao",
			"carteira",
			"centro_de_custo",
			"valor",
			"valor_absoluto",
			"debito_credito",
			"descricao",
			"categoria",
			"nome_atividade",
			"observacoes",
			"metodo",
			"name",
		],
		filters=filters,
		order_by="data_deposito asc",
		limit_page_length=0,
	)

	# Garantir que cada transação é um dicionário simples
	transacoes_dict = [dict(t) for t in transacoes]
	df = pd.DataFrame(transacoes_dict)

	# Buscar saldo inicial de cada instituição somando o campo saldo_inicial de todas as carteiras
	from datetime import datetime, timedelta

	# Buscar saldos iniciais = saldo_inicial das carteiras + transações anteriores ao período
	saldos_iniciais = {inst: 0.0 for inst in instituicoes_nomes}

	# 1. Somar saldo_inicial de todas as carteiras por instituição
	try:
		rows = frappe.db.sql(
			"""
			SELECT instituicao_financeira,
			       SUM(COALESCE(saldo_inicial, 0)) AS saldo
			FROM `tabCarteira`
			GROUP BY instituicao_financeira
			""",
			as_dict=True,
		)
		for r in rows:
			inst = r.get("instituicao_financeira")
			if inst in saldos_iniciais:
				saldos_iniciais[inst] = float(r.get("saldo") or 0.0)
	except Exception:
		pass

	# 2. Somar transações anteriores ao data_inicio
	try:
		transacoes_anteriores = frappe.get_all(
			"Transacao Extrato Geral",
			fields=["instituicao", "valor"],
			filters=[["data_deposito", "<", data_inicio], ["metodo", "!=", "Dinheiro"]],
			limit_page_length=0,
		)
		for t in transacoes_anteriores:
			inst = t.get("instituicao")
			if inst in saldos_iniciais:
				valor = t.get("valor") or 0.0
				saldos_iniciais[inst] += valor
	except Exception:
		pass

	# Inicializar colunas de saldo
	for inst in instituicoes_nomes:
		df[inst] = 0.0

	# Calcular saldo incremental por instituição - usar campo 'valor' que já tem o sinal correto
	saldos = saldos_iniciais.copy()
	for idx, row in df.iterrows():
		inst = row["instituicao"]
		if inst in saldos:
			valor = row["valor"] or 0.0
			# valor já vem com sinal correto: positivo para Crédito, negativo para Débito
			saldos[inst] += valor

		# preencher saldo de TODAS as instituições em cada linha
		for inst_name in instituicoes_nomes:
			df.at[idx, inst_name] = saldos.get(inst_name)

	# Converter para dicionário para o template
	context.transacoes = df.to_dict(orient="records")
	context.data_inicio = data_inicio
	context.data_fim = data_fim
	return context
