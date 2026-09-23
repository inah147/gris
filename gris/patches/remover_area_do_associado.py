import frappe

DOCTYPE = "Associado"
COLUNA = "area"


def execute():
	"""Tira a área do cadastro da pessoa.

	A área passou a ser derivada da função interna: cada `Funcao Voluntario` aponta
	para uma `Unidade Organizacional`, e é desse mapeamento que o organograma monta
	a hierarquia. Manter o campo no Associado deixaria duas áreas concorrentes por
	pessoa, sem ninguém saber qual vale.
	"""
	if not frappe.db.table_exists(DOCTYPE):
		return
	if not frappe.db.has_column(DOCTYPE, COLUNA):
		return

	frappe.db.sql_ddl("ALTER TABLE `tabAssociado` DROP COLUMN `area`")

	# O DocField órfão sobrevive ao sync quando o campo some do JSON.
	frappe.db.delete("DocField", {"parent": DOCTYPE, "fieldname": COLUNA})
	frappe.clear_cache(doctype=DOCTYPE)
	frappe.db.commit()
