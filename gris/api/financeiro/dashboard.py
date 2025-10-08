import frappe
from frappe.utils import add_months, getdate

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


@frappe.whitelist()
def get_entradas_saidas_mensal(
	categoria=None, instituicao=None, carteira=None, centro_de_custo=None, ordinaria_extraordinaria=None
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
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
	where_sql = " AND ".join(conditions)
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
	categoria=None, instituicao=None, carteira=None, centro_de_custo=None, ordinaria_extraordinaria=None
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
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
	where_sql = " AND ".join(conditions)
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
	instituicao=None, carteira=None, centro_de_custo=None, ordinaria_extraordinaria=None
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
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
	where_sql = " AND ".join(conditions)
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
	instituicao=None, carteira=None, categoria=None, ordinaria_extraordinaria=None
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
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
	where_sql = " AND ".join(conditions)
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
	instituicao=None, carteira=None, categoria=None, centro_de_custo=None
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
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
	where_sql = " AND ".join(conditions)
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
	categoria=None, instituicao=None, carteira=None, centro_de_custo=None, ordinaria_extraordinaria=None
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
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
	where_sql = " AND ".join(conditions)
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
	instituicao=None, carteira=None, centro_de_custo=None, ordinaria_extraordinaria=None
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
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
	where_sql = " AND ".join(conditions)
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
	instituicao=None, carteira=None, categoria=None, ordinaria_extraordinaria=None
):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
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
	where_sql = " AND ".join(conditions)
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
def get_saidas_debito_mensal_por_tipo(instituicao=None, carteira=None, categoria=None, centro_de_custo=None):
	months, labels, min_day, next_month = _build_month_sequence()
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
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
	where_sql = " AND ".join(conditions)
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


@frappe.whitelist()
def get_contribuicoes_mensais_por_status():
	months, labels, min_day, next_month = _build_month_sequence()
	query = """
		SELECT DATE_FORMAT(mes_de_referencia, '%%Y-%%m') AS ym,
		       COALESCE(status, 'Sem Status') AS status,
		       COUNT(name) AS qty
		FROM `tabPagamento Contribuicao Mensal`
		WHERE mes_de_referencia >= %(min_day)s AND mes_de_referencia < %(next_month)s
		GROUP BY ym, status
	"""
	rows = frappe.db.sql(query, {"min_day": min_day, "next_month": next_month}, as_dict=True)
	status_month_map = {}
	statuses = set()
	for r in rows:
		statuses.add(r.status)
		status_month_map.setdefault(r.status, {})[r.ym] = int(r.qty) if r.qty else 0
	statuses = sorted(statuses)
	datasets = []
	for st in statuses:
		vals = []
		for m in months:
			vals.append(status_month_map.get(st, {}).get(m.strftime("%Y-%m"), 0))
		datasets.append({"name": st, "chartType": "bar", "values": vals})
	return {"labels": labels, "datasets": datasets}


@frappe.whitelist()
def get_contribuicoes_mensais_inadimplencia():
	months, labels, min_day, next_month = _build_month_sequence()
	query = """
		SELECT base.ym, COALESCE(a.atrasados, 0) AS atrasados, base.total_associados
		FROM (
		  SELECT DATE_FORMAT(mes_de_referencia, '%%Y-%%m') AS ym,
		         COUNT(DISTINCT associado) AS total_associados
		  FROM `tabPagamento Contribuicao Mensal`
		  WHERE mes_de_referencia >= %(min_day)s AND mes_de_referencia < %(next_month)s
		  GROUP BY ym
		) base
		LEFT JOIN (
		  SELECT DATE_FORMAT(mes_de_referencia, '%%Y-%%m') AS ym,
		         COUNT(DISTINCT associado) AS atrasados
		  FROM `tabPagamento Contribuicao Mensal`
		  WHERE mes_de_referencia >= %(min_day)s AND mes_de_referencia < %(next_month)s
		    AND COALESCE(atrasou,0) = 1
		  GROUP BY ym
		) a ON a.ym = base.ym
	"""
	rows = frappe.db.sql(query, {"min_day": min_day, "next_month": next_month}, as_dict=True)
	row_map = {r.ym: r for r in rows}
	values = []
	for m in months:
		row = row_map.get(m.strftime("%Y-%m"))
		if row and row.total_associados:
			pct = (float(row.atrasados or 0) / float(row.total_associados)) * 100.0
		else:
			pct = 0.0
		values.append(round(pct, 2))
	return {
		"labels": labels,
		"datasets": [{"name": "Inadimplência (%)", "chartType": "line", "values": values}],
	}


@frappe.whitelist()
def get_inadimplencia_historica_12m():  # Renomeado de *_6m mantendo 12 meses
	_, _labels, min_day, next_month = _build_month_sequence()
	query = """
		SELECT
		  (SELECT COUNT(DISTINCT associado) FROM `tabPagamento Contribuicao Mensal`
		    WHERE mes_de_referencia >= %(min_day)s AND mes_de_referencia < %(next_month)s) AS total_associados,
		  (SELECT COUNT(DISTINCT associado) FROM `tabPagamento Contribuicao Mensal`
		    WHERE mes_de_referencia >= %(min_day)s AND mes_de_referencia < %(next_month)s AND COALESCE(atrasou,0)=1) AS atrasados
	"""
	row = frappe.db.sql(query, {"min_day": min_day, "next_month": next_month}, as_dict=True)
	total_ass = float(row[0].total_associados) if row and row[0].total_associados else 0.0
	atrasados = float(row[0].atrasados) if row and row[0].atrasados else 0.0
	pct = (atrasados / total_ass * 100.0) if total_ass else 0.0
	return {"percent": round(pct, 2), "atrasado": int(atrasados), "total": int(total_ass)}


# Alias para compatibilidade temporária (frontend ainda chama *_6m)
get_inadimplencia_historica_6m = get_inadimplencia_historica_12m
