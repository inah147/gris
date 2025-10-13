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

	# Buscar saldo inicial de cada instituição no dia anterior à data_inicio
	from datetime import datetime, timedelta

	saldos_iniciais = {inst: 0.0 for inst in instituicoes_nomes}
	if data_inicio:
		try:
			data_inicio_dt = datetime.strptime(data_inicio, "%Y-%m-%d")
			rows = frappe.db.sql(
				"""
				SELECT instituicao,
				       SUM(valor) AS saldo
				FROM `tabTransacao Extrato Geral`
				WHERE data_deposito < %(data_inicio_dt)s
				  AND (metodo IS NULL OR LOWER(TRIM(metodo)) <> 'dinheiro')
				GROUP BY instituicao
				""",
				{"data_inicio_dt": data_inicio_dt},
				as_dict=True,
			)
			for r in rows:
				inst = r.get("instituicao")
				if inst in saldos_iniciais:
					saldos_iniciais[inst] = float(r.get("saldo") or 0.0)
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
