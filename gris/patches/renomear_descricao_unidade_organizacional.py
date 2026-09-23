import frappe

COLUNA_ANTIGA = "descrição"
COLUNA_NOVA = "descricao"
DOCTYPE = "Unidade Organizacional"


def execute():
	"""Migra `descrição` para `descricao` em Unidade Organizacional.

	O fieldname acentuado obrigava alias manual em toda query (ver
	`gris/api/mcp/geral.py`) e repetiria o problema no endpoint do organograma.

	Roda em post_model_sync: o sync já criou a coluna nova a partir do JSON, então
	aqui é copiar o conteúdo e derrubar a antiga. `rename_field` não serve — ele
	exige que o campo novo exista no meta e, com as duas colunas no lugar, o ALTER
	de rename colidiria.
	"""
	if not frappe.db.table_exists(DOCTYPE):
		return
	if not frappe.db.has_column(DOCTYPE, COLUNA_ANTIGA):
		return

	if frappe.db.has_column(DOCTYPE, COLUNA_NOVA):
		# Nomes de coluna não podem ser parametrizados, e aqui são literais fixos.
		frappe.db.sql(
			"""
			UPDATE `tabUnidade Organizacional`
			SET `descricao` = `descrição`
			WHERE (`descricao` IS NULL OR `descricao` = '')
			  AND `descrição` IS NOT NULL
			"""
		)

	frappe.db.sql_ddl("ALTER TABLE `tabUnidade Organizacional` DROP COLUMN `descrição`")

	# O DocField órfão sobrevive ao sync quando o campo some do JSON.
	frappe.db.delete("DocField", {"parent": DOCTYPE, "fieldname": COLUNA_ANTIGA})
	frappe.clear_cache(doctype=DOCTYPE)
	frappe.db.commit()
