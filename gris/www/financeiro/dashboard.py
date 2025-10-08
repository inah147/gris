import frappe

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


# Formatar em BRL (R$ 1.234,56)
def _format_brl(v: float) -> str:
	try:
		return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
	except Exception:
		return f"R$ {v}"


def _get_total_amount(context) -> float:
	try:
		pre_tx = frappe.get_all(
			"Transacao Extrato Geral",
			fields=["SUM(valor) as total"],
			filters={"metodo": ["!=", "Dinheiro"]},
			limit_page_length=0,
		)
		total_amount = pre_tx[0].get("total") or 0.0 if pre_tx else 0.0
	except Exception:
		total_amount = 0.0

	return total_amount


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect_to=/financeiro/dashboard"
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
	context.active_link = "/financeiro/dashboard"
	enrich_context(context, "/financeiro/dashboard")

	# Total em conta: soma dos valores (saldo agregado) considerando CREDITOS - DEBITOS
	context.total_amount = _get_total_amount(context)
	context.total_amount_fmt = _format_brl(context.total_amount)

	# Listas distintas para filtros (categoria, instituicao, carteira, centro_de_custo)
	# Utilizadas apenas para gráficos; cards iniciais não sofrem filtragem.
	try:
		context.filter_categorias = [
			r.get("categoria")
			for r in frappe.get_all(
				"Transacao Extrato Geral",
				fields=["distinct categoria as categoria"],
				filters={"categoria": ["is", "set"], "metodo": ["!=", "Dinheiro"]},
				order_by="categoria asc",
				limit_page_length=0,
			)
			if r.get("categoria")
		]
	except Exception:
		context.filter_categorias = []

	try:
		context.filter_instituicoes = [
			r.get("instituicao")
			for r in frappe.get_all(
				"Transacao Extrato Geral",
				fields=["distinct instituicao as instituicao"],
				filters={"instituicao": ["is", "set"], "metodo": ["!=", "Dinheiro"]},
				order_by="instituicao asc",
				limit_page_length=0,
			)
			if r.get("instituicao")
		]
	except Exception:
		context.filter_instituicoes = []

	try:
		context.filter_carteiras = [
			r.get("carteira")
			for r in frappe.get_all(
				"Transacao Extrato Geral",
				fields=["distinct carteira as carteira"],
				filters={"carteira": ["is", "set"], "metodo": ["!=", "Dinheiro"]},
				order_by="carteira asc",
				limit_page_length=0,
			)
			if r.get("carteira")
		]
	except Exception:
		context.filter_carteiras = []

	try:
		context.filter_centros_custo = [
			r.get("centro_de_custo")
			for r in frappe.get_all(
				"Transacao Extrato Geral",
				fields=["distinct centro_de_custo as centro_de_custo"],
				filters={"centro_de_custo": ["is", "set"], "metodo": ["!=", "Dinheiro"]},
				order_by="centro_de_custo asc",
				limit_page_length=0,
			)
			if r.get("centro_de_custo")
		]
	except Exception:
		context.filter_centros_custo = []
	return context


@frappe.whitelist()
def get_entradas_saidas_mensal(
	categoria=None, instituicao=None, carteira=None, centro_de_custo=None, ordinaria_extraordinaria=None
):
	"""Retorna dados dos últimos 12 meses (inclui mês atual) com somatório de entradas (>0) e saídas (<0) em valores absolutos.

	Estrutura para frappe-charts (bar):
	{
	  labels: ['01/25','02/25',...],
	  datasets: [
	    { name: 'Entradas', chartType: 'bar', values: [...] },
	    { name: 'Saídas', chartType: 'bar', values: [...] }
	  ]
	}
	Exclui metodo = 'Dinheiro'.
	"""
	# Construir sequência de meses (YYYY-MM-01) iniciando 11 meses atrás até atual
	from frappe.utils import add_months, getdate

	today = getdate()
	start = add_months(getdate(f"{today.year}-{today.month}-01"), -11)

	month_cursor = start
	months = []  # (dateobj)
	for _ in range(12):
		months.append(month_cursor)
		month_cursor = add_months(month_cursor, 1)

	# Formatar para labels e para junção SQL
	labels = [m.strftime("%m/%y") for m in months]
	# Construir lista de primeiros dias 'YYYY-MM-01'
	first_days = [m.strftime("%Y-%m-01") for m in months]
	min_day = first_days[0]
	max_day = first_days[-1]

	# Para delimitar range até o último dia do mês atual usamos add_months(max_day, 1)
	next_month = add_months(getdate(max_day), 1)

	# Query agrega por ano-mes usando data_deposito caso exista, senão timestamp_transacao
	# Montar condições dinâmicas
	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	# Se nenhum filtro de categoria nem carteira foi aplicado, excluir transferências entre contas
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
		SELECT
		  DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
		  SUM(CASE WHEN valor > 0 THEN valor ELSE 0 END) AS entradas,
		  SUM(CASE WHEN valor < 0 THEN ABS(valor) ELSE 0 END) AS saidas
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, params, as_dict=True)

	map_rows = {r.ym: r for r in rows}
	entradas_values = []
	saidas_values = []
	resultado_values = []
	for m in months:
		key = m.strftime("%Y-%m")
		row = map_rows.get(key)
		entradas_values.append(float(row.entradas) if row and row.entradas else 0.0)
		saidas_values.append(float(row.saidas) if row and row.saidas else 0.0)
		resultado_values.append(entradas_values[-1] - saidas_values[-1])

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
	"""Total de entradas (Crédito) por mês nos últimos 12 meses.

	Retorna estrutura para gráfico de linha: labels, dataset único 'Entradas (Crédito)'.
	Aplica mesmos filtros e exclui metodo = 'Dinheiro'.
	"""
	from frappe.utils import add_months, getdate

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
		SELECT
		  DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
		  SUM(valor) AS total_credito
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	map_rows = {r.ym: r for r in rows}
	values = []
	for m in months:
		key = m.strftime("%Y-%m")
		row = map_rows.get(key)
		values.append(float(row.total_credito) if row and row.total_credito else 0.0)

	return {
		"labels": labels,
		"datasets": [{"name": "Entradas (Crédito)", "chartType": "line", "values": values}],
	}


@frappe.whitelist()
def get_entradas_credito_mensal_por_categoria(
	instituicao=None, carteira=None, centro_de_custo=None, ordinaria_extraordinaria=None
):
	"""Entradas (Crédito) empilhadas por categoria por mês (últimos 12 meses).

	Aplica filtros: instituicao, carteira, centro_de_custo, ordinaria_extraordinaria.
	Ignora filtro de categoria (cada categoria vira um dataset). Exclui metodo = 'Dinheiro'.
	"""
	from frappe.utils import add_months, getdate

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

	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"valor > 0",
		"debito_credito = 'Crédito'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if (
		not instituicao and not carteira
	):  # categoria é ignorada neste (cada categoria vira dataset) então usamos carteira
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
		SELECT
		  DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
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
		values = []
		for m in months:
			ym = m.strftime("%Y-%m")
			values.append(cat_month_map.get(cat, {}).get(ym, 0.0))
		datasets.append({"name": cat, "chartType": "bar", "values": values})

	return {"labels": labels, "datasets": datasets}


@frappe.whitelist()
def get_entradas_credito_mensal_por_centro_custo(
	instituicao=None, carteira=None, categoria=None, ordinaria_extraordinaria=None
):
	"""Entradas (Crédito) empilhadas por centro de custo por mês (últimos 12 meses).

	Filtros aplicados: instituicao, carteira, categoria, ordinaria_extraordinaria.
	Ignora filtro de centro_de_custo individual (cada centro vira dataset). Exclui metodo = 'Dinheiro'.
	"""
	from frappe.utils import add_months, getdate

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
		SELECT
		  DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
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
		values = []
		for m in months:
			ym = m.strftime("%Y-%m")
			values.append(centro_month_map.get(centro, {}).get(ym, 0.0))
		datasets.append({"name": centro, "chartType": "bar", "values": values})

	return {"labels": labels, "datasets": datasets}


@frappe.whitelist()
def get_entradas_credito_mensal_por_tipo(
	instituicao=None, carteira=None, categoria=None, centro_de_custo=None
):
	"""Entradas (Crédito) empilhadas por tipo (Ordinária/Extraordinária) por mês.

	Filtros aplicados: instituicao, carteira, categoria, centro_de_custo.
	Ignora filtro de ordinaria_extraordinaria para construir ambos datasets.
	"""
	from frappe.utils import add_months, getdate

	# Construção do range de 12 meses (inclui mês atual)
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

	# Observado valor inflado em 'Ordinária'. Reescrevemos a query usando pivot por CASE.
	# Assim cada linha (mês) aparece uma vez e distribuímos valores nas colunas.
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
		SELECT
		  DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
		  SUM(CASE WHEN COALESCE(ordinaria_extraordinaria,'Ordinária') = 'Ordinária' THEN valor ELSE 0 END) AS ordinaria_total,
		  SUM(CASE WHEN ordinaria_extraordinaria = 'Extraordinária' THEN valor ELSE 0 END) AS extraordinaria_total,
		  SUM(CASE WHEN COALESCE(ordinaria_extraordinaria,'') NOT IN ('Ordinária','Extraordinária') THEN valor ELSE 0 END) AS outros_total
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	row_map = {r.ym: r for r in rows}

	# Construir datasets garantindo ordem: Ordinária, Extraordinária, Outros (se houver)
	ordinaria_vals = []
	extra_vals = []
	outros_vals = []
	for m in months:
		ym = m.strftime("%Y-%m")
		row = row_map.get(ym)
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
	"""Total de saídas (Débito) por mês (valores positivos representando o absoluto do débito).

	Estrutura similar a get_entradas_credito_mensal só que para Débito.
	"""
	from frappe.utils import add_months, getdate

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
		SELECT
		  DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
		  SUM(ABS(valor)) AS total_debito
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	row_map = {r.ym: r for r in rows}
	values = []
	for m in months:
		key = m.strftime("%Y-%m")
		row = row_map.get(key)
		values.append(float(row.total_debito) if row and row.total_debito else 0.0)

	return {
		"labels": labels,
		"datasets": [{"name": "Saídas (Débito)", "chartType": "line", "values": values}],
	}


@frappe.whitelist()
def get_saidas_debito_mensal_por_categoria(
	instituicao=None, carteira=None, centro_de_custo=None, ordinaria_extraordinaria=None
):
	"""Saídas (Débito) empilhadas por categoria.

	Ignora filtro de categoria individual.
	"""
	from frappe.utils import add_months, getdate

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

	conditions = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(min_day)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(next_month)s",
		"metodo != 'Dinheiro'",
		"valor < 0",
		"debito_credito = 'Débito'",
	]
	params = {"min_day": min_day, "next_month": next_month}
	if not instituicao and not carteira:  # categoria ignorada (cada categoria dataset)
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
		SELECT
		  DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
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
	"""Saídas (Débito) empilhadas por centro de custo.

	Ignora filtro individual de centro_de_custo.
	"""
	from frappe.utils import add_months, getdate

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
		SELECT
		  DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
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
	"""Saídas (Débito) empilhadas por tipo (Ordinária/Extraordinária) por mês (pivot)."""
	from frappe.utils import add_months, getdate

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
		SELECT
		  DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
		  SUM(CASE WHEN COALESCE(ordinaria_extraordinaria,'Ordinária') = 'Ordinária' THEN ABS(valor) ELSE 0 END) AS ordinaria_total,
		  SUM(CASE WHEN ordinaria_extraordinaria = 'Extraordinária' THEN ABS(valor) ELSE 0 END) AS extraordinaria_total,
		  SUM(CASE WHEN COALESCE(ordinaria_extraordinaria,'') NOT IN ('Ordinária','Extraordinária') THEN ABS(valor) ELSE 0 END) AS outros_total
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, params, as_dict=True)
	row_map = {r.ym: r for r in rows}
	ord_vals = []
	extra_vals = []
	outros_vals = []
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
	"""Quantidade de contribuições mensais por status (empilhado) nos últimos 12 meses.

	Origem: DocType Pagamento Contribuicao Mensal.
	Agrupa por mes_de_referencia (DATE) e status. Assume que campo mes_de_referencia é data do 1º dia do mês.
	"""
	from frappe.utils import add_months, getdate

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

	# Consulta counts por status
	query = """
		SELECT
		  DATE_FORMAT(mes_de_referencia, '%%Y-%%m') AS ym,
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

	return {"labels": labels, "datasets": datasets}


@frappe.whitelist()
def get_contribuicoes_mensais_atrasadas():
	"""Quantidade de contribuições com status 'Atrasado' por mês (últimos 12 meses).

	Estrutura:
	{
	  labels: ['01/25',...],
	  datasets: [ { name: 'Atrasadas', chartType: 'bar', values: [...] } ]
	}
	"""
	from frappe.utils import add_months, getdate

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

	# Contagem de registros com status 'Atrasado'
	query = """
		SELECT
		  DATE_FORMAT(mes_de_referencia, '%%Y-%%m') AS ym,
		  COUNT(name) AS qty
		FROM `tabPagamento Contribuicao Mensal`
		WHERE mes_de_referencia >= %(min_day)s AND mes_de_referencia < %(next_month)s
		  AND status = 'Atrasado'
		GROUP BY ym
	"""
	rows = frappe.db.sql(query, {"min_day": min_day, "next_month": next_month}, as_dict=True)
	row_map = {r.ym: int(r.qty) if r.qty else 0 for r in rows}
	values = []
	for m in months:
		values.append(row_map.get(m.strftime("%Y-%m"), 0))
	return {"labels": labels, "datasets": [{"name": "Atrasadas", "chartType": "bar", "values": values}]}


@frappe.whitelist()
def get_contribuicoes_mensais_inadimplencia():
	"""Percentual de inadimplência por mês (Atrasado / Total * 100) últimos 12 meses.

	Nota: Total considera todos os registros (independente de status) do mês.
	"""
	from frappe.utils import add_months, getdate

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

	# Agora baseado em associados distintos: (associados com pelo menos uma linha atrasou) / (total de associados distintos)
	# Construímos duas subqueries agregadas por mês e unimos.
	query = """
		SELECT
		  base.ym,
		  COALESCE(a.atrasados, 0) AS atrasados,
		  base.total_associados
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
		ym = m.strftime("%Y-%m")
		row = row_map.get(ym)
		if row and row.total_associados:
			pct = (float(row.atrasados or 0) / float(row.total_associados)) * 100.0
		else:
			pct = 0.0
		# Arredonda para 2 casas (mantém float para chart)
		values.append(round(pct, 2))
	return {
		"labels": labels,
		"datasets": [{"name": "Inadimplência (%)", "chartType": "line", "values": values}],
	}


@frappe.whitelist()
def get_inadimplencia_historica_6m():
	"""Retorna percentual agregado de inadimplência (associados com atraso / associados distintos) nos últimos 12 meses.

	Considera meses completos incluindo o mês atual: 12 meses (mês corrente + 11 anteriores).
	Base em associados distintos.
	"""
	from frappe.utils import add_months, getdate

	today = getdate()
	start = add_months(
		getdate(f"{today.year}-{today.month}-01"), -11
	)  # inclui mês atual + 11 anteriores (12 meses)
	min_day = start.strftime("%Y-%m-%d")
	# limite superior: primeiro dia do próximo mês
	from datetime import date

	next_month = add_months(getdate(f"{today.year}-{today.month}-01"), 1)

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
