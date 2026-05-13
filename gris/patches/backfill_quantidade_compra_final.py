import frappe


def execute():
	if not frappe.db.table_exists("Compra Festa"):
		return
	if not frappe.db.has_column("Compra Festa", "quantidade_compra_final"):
		return
	frappe.db.sql(
		"""
		update `tabCompra Festa`
		set quantidade_compra_final = quantidade_compra
		where ifnull(quantidade_compra_final, 0) = 0
			and ifnull(quantidade_compra, 0) != 0
		"""
	)
