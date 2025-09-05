import frappe


def get_context(context):
	years = frappe.get_all(
		"Transparencia", fields=["ano_referencia"], distinct=True, order_by="ano_referencia desc"
	)
	context.years = [row.ano_referencia for row in years if row.ano_referencia]
