import frappe


def get_context(context):
	transparency_docs = frappe.get_doc("Transparencia")
	context.years = transparency_docs.ano_referencia
