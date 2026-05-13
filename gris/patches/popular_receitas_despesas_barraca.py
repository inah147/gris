import frappe


def execute():
	"""Popula as novas child tables `receitas_por_barraca` e `despesas_por_barraca`
	em todas as Festas existentes, disparando o validate() do doctype Festa."""
	if not frappe.db.table_exists("Festa"):
		return
	if not frappe.db.table_exists("Receita por Barraca Festa"):
		return
	if not frappe.db.table_exists("Despesa por Barraca Festa"):
		return

	festas = frappe.get_all("Festa", pluck="name")
	for nome in festas:
		try:
			doc = frappe.get_doc("Festa", nome)
			doc.save()
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Falha ao popular receitas/despesas por barraca: {nome}",
			)
