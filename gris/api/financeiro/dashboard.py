import frappe
from frappe.utils import add_months, getdate

from gris.api.financeiro.contribuicoes import (
	MESES_PADRAO,
	SITUACOES_DO_MES_DEVIDO,
	apurar,
)

# API Financeiro - funções whitelisted migradas de `gris/www/financeiro/dashboard.py`.
# Mantemos assinatura e lógica originais para minimizar impacto no frontend.


def _build_month_sequence():
	"""Retorna lista de objetos date (12 meses incluindo atual), labels, first_days, min_day, next_month."""
	today = getdate()
	start = add_months(getdate(f"{today.year}-{today.month}-01"), -11)
	months = []
	month_cursor = start
	for _ in range(12):
		months.append(month_cursor)
		month_cursor = add_months(month_cursor, 1)
	labels = [m.strftime("%m/%y") for m in months]
	first_days = [m.strftime("%Y-%m-01") for m in months]
	min_day = first_days[0]
	max_day = first_days[-1]
	next_month = add_months(getdate(max_day), 1)
	return months, labels, min_day, next_month


def _maybe_exclude_transfers(conditions, categoria=None, carteira=None, instituicao=None):
	# Regra: excluir transferências quando nenhum filtro que reduz granularidade aplicado
	if categoria is None and carteira is None and instituicao is None:
		conditions.append("COALESCE(repasse_entre_contas,0) = 0")


def _apply_fonte_filter(conditions, params):
	"""Aplica o filtro de fonte (Planilha/Sistema) lido da requisição, se informado.

	Lido de frappe.form_dict para funcionar em todas as funções whitelisted sem alterar
	suas assinaturas — o frontend passa `fonte` junto dos demais filtros.
	"""
	fonte = frappe.form_dict.get("fonte")
	if fonte in ("Planilha", "Sistema"):
		conditions.append("fonte = %(fonte)s")
		params["fonte"] = fonte


@frappe.whitelist()
def get_entradas_saidas_mensal(
	categoria: str | None = None,
	instituicao: str | None = None,
	carteira: str | None = None,
	centro_de_custo: str | None = None,
	ordinaria_extraordinaria: str | None = None,
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"COALESCE(excluir_do_total,0) = 0",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if not categoria and not carteira:
		conditions.append("COALESCE(repasse_entre_contas,0) = 0")
	if categoria:
		conditions.append("categoria = %(categoria)s")
		params["categoria"] = categoria
	if instituicao:
		conditions.append("instituicao = %(instituicao)s")
		params["instituicao"] = instituicao
	if carteira:
		conditions.append("carteira = %(carteira)s")
		params["carteira"] = carteira
	if centro_de_custo:
		conditions.append("centro_de_custo = %(centro_de_custo)s")
		params["centro_de_custo"] = centro_de_custo
	if ordinaria_extraordinaria:
		conditions.append("ordinaria_extraordinaria = %(ordinaria_extraordinaria)s")
		params["ordinaria_extraordinaria"] = ordinaria_extraordinaria
	_apply_fonte_filter(conditions, params)
	where_sql = " AND ".join(conditions)
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	query = f"""
		SELECT DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
			   SUM(CASE WHEN valor > 0 THEN valor ELSE 0 END) AS entradas,
			   SUM(CASE WHEN valor < 0 THEN ABS(valor) ELSE 0 END) AS saidas
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	map_rows = {r.ym: r for r in rows}
	entradas_values, saidas_values, resultado_values = [], [], []
	for m in months:
		key = m.strftime("%Y-%m")
		row = map_rows.get(key)
		e = float(row.entradas) if row and row.entradas else 0.0
		s = float(row.saidas) if row and row.saidas else 0.0
		entradas_values.append(e)
		saidas_values.append(s)
		resultado_values.append(e - s)
	return {
		"labels": labels,
		"datasets": [
			{"name": "Entradas", "chartType": "bar", "values": entradas_values},
			{"name": "Saídas", "chartType": "bar", "values": saidas_values},
			{"name": "Resultado", "chartType": "line", "values": resultado_values},
		],
	}


@frappe.whitelist()
def get_entradas_credito_mensal(
	categoria: str | None = None,
	instituicao: str | None = None,
	carteira: str | None = None,
	centro_de_custo: str | None = None,
	ordinaria_extraordinaria: str | None = None,
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"COALESCE(excluir_do_total,0) = 0",
		"valor > 0",
		"debito_credito = 'Crédito'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if not categoria and not carteira:
		conditions.append("COALESCE(repasse_entre_contas,0) = 0")
	if categoria:
		conditions.append("categoria = %(categoria)s")
		params["categoria"] = categoria
	if instituicao:
		conditions.append("instituicao = %(instituicao)s")
		params["instituicao"] = instituicao
	if carteira:
		conditions.append("carteira = %(carteira)s")
		params["carteira"] = carteira
	if centro_de_custo:
		conditions.append("centro_de_custo = %(centro_de_custo)s")
		params["centro_de_custo"] = centro_de_custo
	if ordinaria_extraordinaria:
		conditions.append("ordinaria_extraordinaria = %(ordinaria_extraordinaria)s")
		params["ordinaria_extraordinaria"] = ordinaria_extraordinaria
	_apply_fonte_filter(conditions, params)
	where_sql = " AND ".join(conditions)
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	query = f"""
		SELECT DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
			   SUM(valor) AS total_credito
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	row_map = {r.ym: r for r in rows}
	values = []
	for m in months:
		row = row_map.get(m.strftime("%Y-%m"))
		values.append(float(row.total_credito) if row and row.total_credito else 0.0)
	return {
		"labels": labels,
		"datasets": [{"name": "Entradas (Crédito)", "chartType": "line", "values": values}],
	}


@frappe.whitelist()
def get_entradas_credito_mensal_por_categoria(
	instituicao: str | None = None,
	carteira: str | None = None,
	centro_de_custo: str | None = None,
	ordinaria_extraordinaria: str | None = None,
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"COALESCE(excluir_do_total,0) = 0",
		"valor > 0",
		"debito_credito = 'Crédito'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if not instituicao and not carteira:
		conditions.append("COALESCE(repasse_entre_contas,0) = 0")
	if instituicao:
		conditions.append("instituicao = %(instituicao)s")
		params["instituicao"] = instituicao
	if carteira:
		conditions.append("carteira = %(carteira)s")
		params["carteira"] = carteira
	if centro_de_custo:
		conditions.append("centro_de_custo = %(centro_de_custo)s")
		params["centro_de_custo"] = centro_de_custo
	if ordinaria_extraordinaria:
		conditions.append("ordinaria_extraordinaria = %(ordinaria_extraordinaria)s")
		params["ordinaria_extraordinaria"] = ordinaria_extraordinaria
	_apply_fonte_filter(conditions, params)
	where_sql = " AND ".join(conditions)
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	query = f"""
		SELECT DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
			   COALESCE(categoria, 'Sem Categoria') AS categoria,
			   SUM(valor) AS total
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym, categoria
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	cat_month_map = {}
	categorias = set()
	for r in rows:
		categorias.add(r.categoria)
		cat_month_map.setdefault(r.categoria, {})[r.ym] = float(r.total) if r.total else 0.0
	categorias = sorted(categorias)
	datasets = []
	for cat in categorias:
		vals = []
		for m in months:
			vals.append(cat_month_map.get(cat, {}).get(m.strftime("%Y-%m"), 0.0))
		datasets.append({"name": cat, "chartType": "bar", "values": vals})
	return {"labels": labels, "datasets": datasets}


@frappe.whitelist()
def get_entradas_credito_mensal_por_centro_custo(
	instituicao: str | None = None,
	carteira: str | None = None,
	categoria: str | None = None,
	ordinaria_extraordinaria: str | None = None,
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"COALESCE(excluir_do_total,0) = 0",
		"valor > 0",
		"debito_credito = 'Crédito'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if not categoria and not carteira:
		conditions.append("COALESCE(repasse_entre_contas,0) = 0")
	if instituicao:
		conditions.append("instituicao = %(instituicao)s")
		params["instituicao"] = instituicao
	if carteira:
		conditions.append("carteira = %(carteira)s")
		params["carteira"] = carteira
	if categoria:
		conditions.append("categoria = %(categoria)s")
		params["categoria"] = categoria
	if ordinaria_extraordinaria:
		conditions.append("ordinaria_extraordinaria = %(ordinaria_extraordinaria)s")
		params["ordinaria_extraordinaria"] = ordinaria_extraordinaria
	_apply_fonte_filter(conditions, params)
	where_sql = " AND ".join(conditions)
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	query = f"""
		SELECT DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
			   COALESCE(centro_de_custo, 'Sem Centro') AS centro,
			   SUM(valor) AS total
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym, centro
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	centro_month_map = {}
	centros = set()
	for r in rows:
		centros.add(r.centro)
		centro_month_map.setdefault(r.centro, {})[r.ym] = float(r.total) if r.total else 0.0
	centros = sorted(centros)
	datasets = []
	for centro in centros:
		vals = []
		for m in months:
			vals.append(centro_month_map.get(centro, {}).get(m.strftime("%Y-%m"), 0.0))
		datasets.append({"name": centro, "chartType": "bar", "values": vals})
	return {"labels": labels, "datasets": datasets}


@frappe.whitelist()
def get_entradas_credito_mensal_por_tipo(
	instituicao: str | None = None,
	carteira: str | None = None,
	categoria: str | None = None,
	centro_de_custo: str | None = None,
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"COALESCE(excluir_do_total,0) = 0",
		"valor > 0",
		"debito_credito = 'Crédito'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if not categoria and not carteira:
		conditions.append("COALESCE(repasse_entre_contas,0) = 0")
	if instituicao:
		conditions.append("instituicao = %(instituicao)s")
		params["instituicao"] = instituicao
	if carteira:
		conditions.append("carteira = %(carteira)s")
		params["carteira"] = carteira
	if categoria:
		conditions.append("categoria = %(categoria)s")
		params["categoria"] = categoria
	if centro_de_custo:
		conditions.append("centro_de_custo = %(centro_de_custo)s")
		params["centro_de_custo"] = centro_de_custo
	_apply_fonte_filter(conditions, params)
	where_sql = " AND ".join(conditions)
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	query = f"""
		SELECT DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
			SUM(CASE WHEN COALESCE(ordinaria_extraordinaria,'Ordinária') = 'Ordinária' THEN valor ELSE 0 END) AS ordinaria_total,
			SUM(CASE WHEN ordinaria_extraordinaria = 'Extraordinária' THEN valor ELSE 0 END) AS extraordinaria_total,
			SUM(CASE WHEN COALESCE(ordinaria_extraordinaria,'') NOT IN ('Ordinária','Extraordinária') THEN valor ELSE 0 END) AS outros_total
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	row_map = {r.ym: r for r in rows}
	ordinaria_vals, extra_vals, outros_vals = [], [], []
	for m in months:
		row = row_map.get(m.strftime("%Y-%m"))
		ordinaria_vals.append(float(row.ordinaria_total) if row and row.ordinaria_total else 0.0)
		extra_vals.append(float(row.extraordinaria_total) if row and row.extraordinaria_total else 0.0)
		outros_vals.append(float(row.outros_total) if row and row.outros_total else 0.0)
	datasets = [
		{"name": "Ordinária", "chartType": "bar", "values": ordinaria_vals},
		{"name": "Extraordinária", "chartType": "bar", "values": extra_vals},
	]
	if any(v > 0 for v in outros_vals):
		datasets.append({"name": "Outros", "chartType": "bar", "values": outros_vals})
	return {"labels": labels, "datasets": datasets}


@frappe.whitelist()
def get_saidas_debito_mensal(
	categoria: str | None = None,
	instituicao: str | None = None,
	carteira: str | None = None,
	centro_de_custo: str | None = None,
	ordinaria_extraordinaria: str | None = None,
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"COALESCE(excluir_do_total,0) = 0",
		"valor < 0",
		"debito_credito = 'Débito'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if not categoria and not carteira:
		conditions.append("COALESCE(repasse_entre_contas,0) = 0")
	if categoria:
		conditions.append("categoria = %(categoria)s")
		params["categoria"] = categoria
	if instituicao:
		conditions.append("instituicao = %(instituicao)s")
		params["instituicao"] = instituicao
	if carteira:
		conditions.append("carteira = %(carteira)s")
		params["carteira"] = carteira
	if centro_de_custo:
		conditions.append("centro_de_custo = %(centro_de_custo)s")
		params["centro_de_custo"] = centro_de_custo
	if ordinaria_extraordinaria:
		conditions.append("ordinaria_extraordinaria = %(ordinaria_extraordinaria)s")
		params["ordinaria_extraordinaria"] = ordinaria_extraordinaria
	_apply_fonte_filter(conditions, params)
	where_sql = " AND ".join(conditions)
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	query = f"""
		SELECT DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
			   SUM(ABS(valor)) AS total_debito
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	row_map = {r.ym: r for r in rows}
	values = []
	for m in months:
		row = row_map.get(m.strftime("%Y-%m"))
		values.append(float(row.total_debito) if row and row.total_debito else 0.0)
	return {
		"labels": labels,
		"datasets": [{"name": "Saídas (Débito)", "chartType": "line", "values": values}],
	}


@frappe.whitelist()
def get_saidas_debito_mensal_por_categoria(
	instituicao: str | None = None,
	carteira: str | None = None,
	centro_de_custo: str | None = None,
	ordinaria_extraordinaria: str | None = None,
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"COALESCE(excluir_do_total,0) = 0",
		"valor < 0",
		"debito_credito = 'Débito'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if not instituicao and not carteira:
		conditions.append("COALESCE(repasse_entre_contas,0) = 0")
	if instituicao:
		conditions.append("instituicao = %(instituicao)s")
		params["instituicao"] = instituicao
	if carteira:
		conditions.append("carteira = %(carteira)s")
		params["carteira"] = carteira
	if centro_de_custo:
		conditions.append("centro_de_custo = %(centro_de_custo)s")
		params["centro_de_custo"] = centro_de_custo
	if ordinaria_extraordinaria:
		conditions.append("ordinaria_extraordinaria = %(ordinaria_extraordinaria)s")
		params["ordinaria_extraordinaria"] = ordinaria_extraordinaria
	_apply_fonte_filter(conditions, params)
	where_sql = " AND ".join(conditions)
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	query = f"""
		SELECT DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
			   COALESCE(categoria, 'Sem Categoria') AS categoria,
			   SUM(ABS(valor)) AS total
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym, categoria
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	c_map = {}
	categorias = set()
	for r in rows:
		categorias.add(r.categoria)
		c_map.setdefault(r.categoria, {})[r.ym] = float(r.total) if r.total else 0.0
	categorias = sorted(categorias)
	datasets = []
	for cat in categorias:
		vals = []
		for m in months:
			vals.append(c_map.get(cat, {}).get(m.strftime("%Y-%m"), 0.0))
		datasets.append({"name": cat, "chartType": "bar", "values": vals})
	return {"labels": labels, "datasets": datasets}


@frappe.whitelist()
def get_saidas_debito_mensal_por_centro_custo(
	instituicao: str | None = None,
	carteira: str | None = None,
	categoria: str | None = None,
	ordinaria_extraordinaria: str | None = None,
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"COALESCE(excluir_do_total,0) = 0",
		"valor < 0",
		"debito_credito = 'Débito'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if not categoria and not carteira:
		conditions.append("COALESCE(repasse_entre_contas,0) = 0")
	if instituicao:
		conditions.append("instituicao = %(instituicao)s")
		params["instituicao"] = instituicao
	if carteira:
		conditions.append("carteira = %(carteira)s")
		params["carteira"] = carteira
	if categoria:
		conditions.append("categoria = %(categoria)s")
		params["categoria"] = categoria
	if ordinaria_extraordinaria:
		conditions.append("ordinaria_extraordinaria = %(ordinaria_extraordinaria)s")
		params["ordinaria_extraordinaria"] = ordinaria_extraordinaria
	_apply_fonte_filter(conditions, params)
	where_sql = " AND ".join(conditions)
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	query = f"""
		SELECT DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
			   COALESCE(centro_de_custo, 'Sem Centro') AS centro,
			   SUM(ABS(valor)) AS total
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym, centro
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	map_c = {}
	centros = set()
	for r in rows:
		centros.add(r.centro)
		map_c.setdefault(r.centro, {})[r.ym] = float(r.total) if r.total else 0.0
	centros = sorted(centros)
	datasets = []
	for c in centros:
		vals = []
		for m in months:
			vals.append(map_c.get(c, {}).get(m.strftime("%Y-%m"), 0.0))
		datasets.append({"name": c, "chartType": "bar", "values": vals})
	return {"labels": labels, "datasets": datasets}


@frappe.whitelist()
def get_saidas_debito_mensal_por_tipo(
	instituicao: str | None = None,
	carteira: str | None = None,
	categoria: str | None = None,
	centro_de_custo: str | None = None,
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"COALESCE(excluir_do_total,0) = 0",
		"valor < 0",
		"debito_credito = 'Débito'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if not categoria and not carteira:
		conditions.append("COALESCE(repasse_entre_contas,0) = 0")
	if instituicao:
		conditions.append("instituicao = %(instituicao)s")
		params["instituicao"] = instituicao
	if carteira:
		conditions.append("carteira = %(carteira)s")
		params["carteira"] = carteira
	if categoria:
		conditions.append("categoria = %(categoria)s")
		params["categoria"] = categoria
	if centro_de_custo:
		conditions.append("centro_de_custo = %(centro_de_custo)s")
		params["centro_de_custo"] = centro_de_custo
	_apply_fonte_filter(conditions, params)
	where_sql = " AND ".join(conditions)
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	query = f"""
		SELECT DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
			SUM(CASE WHEN COALESCE(ordinaria_extraordinaria,'Ordinária') = 'Ordinária' THEN ABS(valor) ELSE 0 END) AS ordinaria_total,
			SUM(CASE WHEN ordinaria_extraordinaria = 'Extraordinária' THEN ABS(valor) ELSE 0 END) AS extraordinaria_total,
			SUM(CASE WHEN COALESCE(ordinaria_extraordinaria,'') NOT IN ('Ordinária','Extraordinária') THEN ABS(valor) ELSE 0 END) AS outros_total
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	row_map = {r.ym: r for r in rows}
	ord_vals, extra_vals, outros_vals = [], [], []
	for m in months:
		row = row_map.get(m.strftime("%Y-%m"))
		ord_vals.append(float(row.ordinaria_total) if row and row.ordinaria_total else 0.0)
		extra_vals.append(float(row.extraordinaria_total) if row and row.extraordinaria_total else 0.0)
		outros_vals.append(float(row.outros_total) if row and row.outros_total else 0.0)
	datasets = [
		{"name": "Ordinária", "chartType": "bar", "values": ord_vals},
		{"name": "Extraordinária", "chartType": "bar", "values": extra_vals},
	]
	if any(v > 0 for v in outros_vals):
		datasets.append({"name": "Outros", "chartType": "bar", "values": outros_vals})
	return {"labels": labels, "datasets": datasets}


# ─────────────────── contribuições mensais ───────────────────
#
# Estas três séries vêm da apuração de `gris.api.financeiro.contribuicoes`, a
# mesma que alimenta a página /financeiro/contribuicoes: um mês está quitado
# quando o crédito da categoria "Contribuição Mensal" atribuído ao associado,
# somado ao que sobrou dos meses anteriores, alcança o valor esperado.
#
# Antes elas contavam registros de `Pagamento Contribuicao Mensal`, alimentado
# por schedulers e por marcação manual — o que fazia o painel e a página darem
# números diferentes para a mesma competência. O DocType segue existindo para o
# fluxo de cobrança, mas não manda mais em nenhum gráfico.


def _apuracao_contribuicoes():
	"""Apuração dos 12 meses do painel.

	Cada endpoint faz a sua: o painel dispara as chamadas em paralelo, então não
	há requisição comum onde guardar o resultado. O custo é o mesmo da página de
	contribuições.
	"""
	return apurar(MESES_PADRAO)


def _rotulos_curtos(dados):
	"""Rótulos de mês no formato do painel (MM/AA).

	A apuração rotula em MM/AAAA, que é o certo na página de contribuições. Aqui
	os gráficos ficam lado a lado com os demais, todos em MM/AA — misturar os dois
	formatos no mesmo painel salta aos olhos.
	"""
	return [f"{mes['ym'][5:]}/{mes['ym'][2:4]}" for mes in dados["meses"]]


@frappe.whitelist()
def get_contribuicoes_mensais_por_status():
	"""Quantidade de meses devidos em cada situação, mês a mês.

	Conta obrigações, não associados: um associado com três meses em atraso pesa
	três. Meses fora da vigência da cobrança não entram — não há o que cobrar
	neles, e empilhá-los achataria as barras que interessam.
	"""
	dados = _apuracao_contribuicoes()
	por_situacao = dados["series"]["por_situacao"]

	datasets = [
		{"name": situacao, "chartType": "bar", "values": por_situacao[situacao]}
		for situacao in SITUACOES_DO_MES_DEVIDO
		if any(por_situacao[situacao])
	]
	return {"labels": _rotulos_curtos(dados), "datasets": datasets}


@frappe.whitelist()
def get_contribuicoes_mensais_inadimplencia():
	"""Percentual de meses vencidos e não quitados sobre os meses devidos."""
	dados = _apuracao_contribuicoes()
	return {
		"labels": _rotulos_curtos(dados),
		"datasets": [
			{
				"name": "Inadimplência (%)",
				"chartType": "line",
				"values": dados["series"]["inadimplencia"],
			}
		],
	}


@frappe.whitelist()
def get_inadimplencia_historica_12m():  # Renomeado de *_6m mantendo 12 meses
	"""Associados com ao menos um mês vencido e não quitado no período."""
	totais = _apuracao_contribuicoes()["totais"]
	return {
		"percent": totais["inadimplencia_associados"],
		"atrasado": totais["inadimplentes"],
		"total": totais["contribuintes"],
	}


# Alias para compatibilidade temporária (frontend ainda chama *_6m)
get_inadimplencia_historica_6m = get_inadimplencia_historica_12m
