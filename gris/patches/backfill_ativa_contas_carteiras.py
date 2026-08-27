import frappe


def execute():
	"""Garante ativa=1 em todas as Carteiras e Instituições Financeiras existentes.

	O campo ativa foi adicionado com default=1, mas registros já existentes no banco
	recebem NULL na migração — este patch normaliza para 1 (ativo).
	"""
	for doctype in ("Carteira", "Instituicao Financeira"):
		if not frappe.db.table_exists(doctype):
			continue
		if not frappe.db.has_column(doctype, "ativa"):
			continue
		# Interpolação segura: `doctype` vem da tupla literal acima.
		frappe.db.sql(f"UPDATE `tab{doctype}` SET `ativa` = 1 WHERE `ativa` IS NULL OR `ativa` = 0")

	frappe.db.commit()
