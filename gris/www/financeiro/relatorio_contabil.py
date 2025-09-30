import frappe
import pandas as pd

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect_to=/financeiro/relatorios"
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

	# Buscar instituições financeiras
	instituicoes = frappe.get_all("Instituicao Financeira", fields=["name", "nome"], order_by="nome asc")
	instituicoes_nomes = [i["nome"] or i["name"] for i in instituicoes]
	context.instituicoes = instituicoes_nomes

	# Filtros de data vindos da query string
	request_args = frappe.local.form_dict or {}

	from datetime import date

	today = date.today()
	primeiro_dia = today.replace(day=1)
	data_inicio = request_args.get("data_inicio") or primeiro_dia.strftime("%Y-%m-%d")
	data_fim = request_args.get("data_fim") or today.strftime("%Y-%m-%d")

	filters = []
	if data_inicio:
		filters.append(["Transacao Extrato Geral", "data_deposito", ">=", data_inicio])
	if data_fim:
		filters.append(["Transacao Extrato Geral", "data_deposito", "<=", data_fim])

	# Buscar transações do extrato geral filtradas
	transacoes = frappe.get_all(
		"Transacao Extrato Geral",
		fields=[
			"data_deposito",
			"instituicao",
			"carteira",
			"centro_de_custo",
			"valor_absoluto",
			"debito_credito",
			"descricao",
			"categoria",
			"nome_atividade",
			"observacoes",
			"name",
		],
		filters=filters,
		order_by="data_deposito asc",
	)

	# Garantir que cada transação é um dicionário simples
	transacoes_dict = [dict(t) for t in transacoes]
	df = pd.DataFrame(transacoes_dict)

	# Buscar saldo inicial de cada instituição no dia anterior à data_inicio
	from datetime import datetime, timedelta

	saldos_iniciais = {inst: 0.0 for inst in instituicoes_nomes}
	if data_inicio:
		try:
			data_inicio_dt = datetime.strptime(data_inicio, "%Y-%m-%d")
			data_anterior = (data_inicio_dt - timedelta(days=1)).strftime("%Y-%m-%d")
			for inst in instituicoes_nomes:
				saldo = 0.0
				transacoes_anteriores = frappe.get_all(
					"Transacao Extrato Geral",
					fields=["valor_absoluto", "debito_credito", "instituicao", "data_deposito"],
					filters={
						"instituicao": inst,
						"data_deposito": ["<=", data_anterior],
					},
					order_by="data_deposito asc",
				)
				for t in transacoes_anteriores:
					valor = t.get("valor_absoluto") or 0.0
					if t.get("debito_credito") == "Crédito":
						saldo += valor
					elif t.get("debito_credito") == "Débito":
						saldo -= valor
				saldos_iniciais[inst] = saldo
		except Exception:
			pass

	# Inicializar colunas de saldo
	for inst in instituicoes_nomes:
		df[inst] = 0.0

	# Calcular saldo incremental por instituição
	saldos = saldos_iniciais.copy()
	for idx, row in df.iterrows():
		for inst in instituicoes_nomes:
			if row["instituicao"] == inst:
				valor = row["valor_absoluto"] or 0.0
				if row["debito_credito"] == "Crédito":
					saldos[inst] += valor
				elif row["debito_credito"] == "Débito":
					saldos[inst] -= valor
			df.at[idx, inst] = saldos[inst]

	# Converter para dicionário para o template
	context.transacoes = df.to_dict(orient="records")
	context.data_inicio = data_inicio
	context.data_fim = data_fim
	return context
	# Garantir colunas obrigatórias
	for col in [
		"data_deposito",
		"instituicao",
		"carteira",
		"centro_de_custo",
		"valor_absoluto",
		"debito_credito",
		"descricao",
		"categoria",
		"nome_atividade",
		"observacoes",
	]:
		if col not in df:
			df[col] = None

	# Inicializar colunas de saldo
	for inst in instituicoes_nomes:
		df[inst] = 0.0

	# Calcular saldo incremental por instituição
	saldos = {inst: 0.0 for inst in instituicoes_nomes}
	for idx, row in df.iterrows():
		for inst in instituicoes_nomes:
			if row["instituicao"] == inst:
				valor = row["valor_absoluto"] or 0.0
				if row["debito_credito"] == "Crédito":
					saldos[inst] += valor
				elif row["debito_credito"] == "Débito":
					saldos[inst] -= valor
			df.at[idx, inst] = saldos[inst]

	# Converter para dicionário para o template
	context.transacoes = df.to_dict(orient="records")
	return context
