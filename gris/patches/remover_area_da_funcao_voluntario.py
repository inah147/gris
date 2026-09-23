import frappe

DOCTYPE = "Funcao Voluntario"
COLUNA = "area"


def execute():
	"""Tira a área da definição da função.

	O vínculo virou M:N do lado da área (`Unidade Organizacional.funcoes`) e a posição
	da pessoa no organograma passou a sair de `Funcao do Associado.area`. Manter a
	coluna aqui deixaria duas áreas concorrentes por função, sem ninguém saber qual
	vale — o mesmo motivo que tirou `area` do Associado.

	Último da série: `popular_funcoes_das_unidades_organizacionais`,
	`backfill_area_da_funcao_do_associado` e `unificar_funcoes_de_secao` leem esta
	coluna antes de ela cair.
	"""
	if not frappe.db.table_exists(DOCTYPE):
		return
	if not frappe.db.has_column(DOCTYPE, COLUNA):
		return

	frappe.db.sql_ddl("ALTER TABLE `tabFuncao Voluntario` DROP COLUMN `area`")

	# O DocField órfão sobrevive ao sync quando o campo some do JSON.
	frappe.db.delete("DocField", {"parent": DOCTYPE, "fieldname": COLUNA})
	frappe.clear_cache(doctype=DOCTYPE)
	frappe.db.commit()
