import frappe


def execute():
	"""Marca as transações já existentes como fonte='Planilha' e normaliza excluir_do_total.

	Os campos `fonte`, `status_conciliacao` e `excluir_do_total` foram adicionados a
	`Transacao Extrato Geral`. Registros já existentes recebem NULL na migração — este patch
	garante que tudo que já existia (importado por planilha/Data Import ou entrada manual)
	fique com fonte='Planilha' e fora de qualquer conciliação, sem impactar os totais.
	"""
	doctype = "Transacao Extrato Geral"
	if not frappe.db.table_exists(doctype):
		return

	if frappe.db.has_column(doctype, "fonte"):
		frappe.db.sql(
			"UPDATE `tabTransacao Extrato Geral` SET `fonte` = 'Planilha' "
			"WHERE `fonte` IS NULL OR `fonte` = ''"
		)

	if frappe.db.has_column(doctype, "status_conciliacao"):
		frappe.db.sql(
			"UPDATE `tabTransacao Extrato Geral` SET `status_conciliacao` = 'Não conciliada' "
			"WHERE `status_conciliacao` IS NULL OR `status_conciliacao` = ''"
		)

	if frappe.db.has_column(doctype, "excluir_do_total"):
		frappe.db.sql(
			"UPDATE `tabTransacao Extrato Geral` SET `excluir_do_total` = 0 "
			"WHERE `excluir_do_total` IS NULL"
		)

	frappe.db.commit()
