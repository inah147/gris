from datetime import date, datetime

import frappe


def _list_months(data_inicial, data_final):
	"""
	Retorna uma lista contendo as datas do primeiro dia de cada mês
	entre data_inicial e data_final (inclusive), ordenadas cronologicamente.

	Aceita objetos date ou strings no formato 'YYYY-MM-DD'.
	Se data_inicial > data_final elas são trocadas.
	"""
	if isinstance(data_inicial, str):
		data_inicial = datetime.strptime(data_inicial, "%Y-%m-%d").date()
	if isinstance(data_final, str):
		data_final = datetime.strptime(data_final, "%Y-%m-%d").date()

	if data_inicial > data_final:
		data_inicial, data_final = data_final, data_inicial

	# Normaliza para primeiro dia do mês inicial
	atual = date(data_inicial.year, data_inicial.month, 1)
	# Limite: primeiro dia do mês da data_final
	limite = date(data_final.year, data_final.month, 1)

	resultado = []
	while atual <= limite:
		resultado.append(atual)
		# Avança um mês
		if atual.month == 12:
			atual = date(atual.year + 1, 1, 1)
		else:
			atual = date(atual.year, atual.month + 1, 1)
	return resultado


def _get_associates(filters=None):
	if not filters:
		filters = {}

	return frappe.get_all(
		"Associado",
		fields=[
			"name",
			# "categoria",
			# "ramo",
			# "secao",
			# "funcao",
			"status_no_grupo",
			"status",
		],
	)


def _get_associates_history(associates):
	"""Retorna lista de dicts (associate, onboarding, offboarding) e menor data de ingresso."""
	history_rows = []
	min_date = date.today()
	for associate in associates:
		assoc_name = (
			associate.get("name") if isinstance(associate, dict) else getattr(associate, "name", None)
		)
		if not assoc_name:
			continue
		doc = frappe.get_doc("Associado", assoc_name)
		for row in doc.historico_no_grupo or []:
			if row.data_de_ingresso and row.data_de_ingresso < min_date:
				min_date = row.data_de_ingresso
			history_rows.append(
				{
					"associate": assoc_name,
					"onboarding": row.data_de_ingresso,
					"offboarding": row.data_de_desligamento,
				}
			)
	return history_rows, min_date


@frappe.whitelist()
def update_associates_time_series():
	associates = _get_associates()
	associates_history, min_date = _get_associates_history(associates)
	if not associates_history:
		return []

	months_list = _list_months(min_date, date.today())

	results = []
	for month_start in months_list:
		if month_start.month == 12:
			month_end = date(month_start.year + 1, 1, 1)
		else:
			month_end = date(month_start.year, month_start.month + 1, 1)

		# Entraram neste mês (qualquer dia do mês)
		joined = sum(
			1 for r in associates_history if r["onboarding"] and month_start <= r["onboarding"] < month_end
		)
		# Saíram neste mês (qualquer dia do mês)
		left = sum(
			1 for r in associates_history if r["offboarding"] and month_start <= r["offboarding"] < month_end
		)
		active = sum(
			1
			for r in associates_history
			if r["onboarding"]
			and r["onboarding"] < month_end
			and (not r["offboarding"] or r["offboarding"] >= month_end)
		)

		record = {
			"month": month_start.strftime("%Y-%m-01"),
			"joined": int(joined),
			"left": int(left),
			"active": int(active),
		}
		results.append(record)

		doctype = "Metrica Mensal de Associados"

		# Detecta dinamicamente o nome do campo que representa o mês
		def _month_field():
			meta = frappe.get_meta(doctype)
			candidates = ["mes", "month", "mes_referencia", "referencia", "competencia", "periodo"]
			for c in candidates:
				if any(df.fieldname == c for df in meta.fields):
					return c
			# fallback: se não existir, lança erro claro
			raise frappe.ValidationError(
				"Campo de mês não encontrado em 'Metrica Mensal de Associados'. Verifique o fieldname (ex: criar campo 'mes')."
			)

		month_field = _month_field()
		name = frappe.db.get_value(doctype, {month_field: month_start})
		if name:
			frappe.db.set_value(
				doctype,
				name,
				{
					"qt_novos": record["joined"],
					"qt_evasao": record["left"],
					"qt_ativos_uel": record["active"],
				},
			)
		else:
			doc = frappe.get_doc(
				{
					"doctype": doctype,
					month_field: month_start,
					"qt_novos": record["joined"],
					"qt_evasao": record["left"],
					"qt_ativos_uel": record["active"],
				}
			)
			doc.insert()
			# doc.insert(ignore_permissions=True)

	frappe.db.commit()
	return results
