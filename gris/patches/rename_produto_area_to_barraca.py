import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	"""Renomeia o campo 'area' para 'barraca' no DocType Produto de Venda Festa."""
	if not frappe.db.table_exists("Produto de Venda Festa"):
		return
	if frappe.db.has_column("Produto de Venda Festa", "area"):
		rename_field("Produto de Venda Festa", "area", "barraca")
