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

	# --- demonstrativo data preparation ---
	# parâmetros: ano (query param) defaults to current year
	from datetime import datetime

	year = frappe.form_dict.get("ano") or str(datetime.now().year)
	try:
		year = int(year)
	except Exception:
		year = datetime.now().year

	# months labels and keys
	months = [
		{"key": 1, "label": "jan-" + str(year)[-2:]},
		{"key": 2, "label": "fev-" + str(year)[-2:]},
		{"key": 3, "label": "mar-" + str(year)[-2:]},
		{"key": 4, "label": "abr-" + str(year)[-2:]},
		{"key": 5, "label": "mai-" + str(year)[-2:]},
		{"key": 6, "label": "jun-" + str(year)[-2:]},
		{"key": 7, "label": "jul-" + str(year)[-2:]},
		{"key": 8, "label": "ago-" + str(year)[-2:]},
		{"key": 9, "label": "set-" + str(year)[-2:]},
		{"key": 10, "label": "out-" + str(year)[-2:]},
		{"key": 11, "label": "nov-" + str(year)[-2:]},
		{"key": 12, "label": "dez-" + str(year)[-2:]},
	]

	# fetch transactions for the year
	start = f"{year}-01-01"
	end = f"{year}-12-31"

	trans = frappe.get_all(
		"Transacao Extrato Geral",
		fields=["data_deposito", "categoria", "valor_absoluto", "debito_credito", "instituicao", "carteira"],
		filters=[["data_deposito", ">=", start], ["data_deposito", "<=", end], ["metodo", "!=", "Dinheiro"]],
		limit_page_length=0,
	)

	# group sums: section -> category -> month -> sum
	# section: 'entradas' for Crédito, 'saidas' for Débito
	data = {"entradas": {}, "saidas": {}}

	# month totals
	month_totals = {"entradas": {m["key"]: 0.0 for m in months}, "saidas": {m["key"]: 0.0 for m in months}}

	for t in trans:
		date = t.get("data_deposito")
		if not date:
			continue
		# ensure date is string YYYY-MM-DD or a date
		if isinstance(date, str):
			try:
				m = int(date.split("-")[1])
			except Exception:
				continue
		else:
			m = date.month

		cat = t.get("categoria") or "(Sem Categoria)"
		val = t.get("valor_absoluto") or 0.0
		sec = "entradas" if t.get("debito_credito") == "Crédito" else "saidas"

		data.setdefault(sec, {}).setdefault(cat, {}).setdefault(m, 0.0)
		data[sec][cat][m] += val
		month_totals[sec][m] += val

	# compute saldo inicial per month: saldo inicial month 1 = sum of transactions before year start
	# then saldo inicial for month N = saldo final month N-1
	# saldo final month = saldo inicial + (entradas - saidas)

	# compute prior balance up to day before year start
	saldo_prev = {}
	for sec in ["entradas", "saidas"]:
		saldo_prev[sec] = 0.0

	# we consider saldo as entradas - saidas across all categories and institutions
	# get total before year
	pre_tx = frappe.get_all(
		"Transacao Extrato Geral",
		fields=["SUM(valor) as total"],
		filters={"data_deposito": ["<", start], "metodo": ["!=", "Dinheiro"]},
		limit_page_length=0,
	)
	total_before = pre_tx[0].get("total") or 0.0 if pre_tx else 0.0

	# now build month-by-month balances
	saldo_inicial = {}
	saldo_final = {}
	saldo_inicial[1] = total_before
	for m in range(1, 13):
		entr = month_totals["entradas"].get(m, 0.0)
		saida = month_totals["saidas"].get(m, 0.0)
		resultado = entr - saida
		if m > 1:
			saldo_inicial[m] = saldo_final[m - 1]
		# final
		saldo_final[m] = saldo_inicial[m] + resultado

	# prepare sorted category lists
	entradas_cats = sorted(data.get("entradas", {}).keys())
	saidas_cats = sorted(data.get("saidas", {}).keys())

	# prepare year selector options: distinct years present in Transacao Extrato Geral
	try:
		rows = frappe.db.sql(
			"""
			SELECT DISTINCT YEAR(data_deposito) as y
			FROM `tabTransacao Extrato Geral`
			WHERE data_deposito IS NOT NULL
			ORDER BY y DESC
			""",
			as_list=True,
		)
		year_options = [int(r[0]) for r in rows if r and r[0]]
		# ensure current year appears
		if year not in year_options:
			year_options.insert(0, year)
	except Exception:
		# fallback to a small range if query fails
		year_options = list(range(year - 4, year + 2))

	# pass to context
	context.demonstrativo = {
		"year": year,
		"months": months,
		"entradas_cats": entradas_cats,
		"saidas_cats": saidas_cats,
		"data": data,
		"month_totals": month_totals,
		"saldo_inicial": saldo_inicial,
		"saldo_final": saldo_final,
		"year_options": year_options,
	}

	# include static assets
	context.add_css = "/financeiro/demonstrativo.css"
	context.add_js = "/financeiro/demonstrativo.js"
