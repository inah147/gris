import frappe


def execute():
	"""Preenche a data de ativação do registro provisório para os registros já existentes.

	O campo ``data_registro_provisorio_efetivado`` passou a ser gravado pelo controller de
	Novo Associado quando o flag ``registro_provisorio_efetivado`` é marcado. Para os registros
	anteriores ao campo, usamos ``modified`` como melhor aproximação disponível da data de
	ativação — é a partir dela que o aviso de seguimento (20 dias) passa a contar.
	"""
	if not frappe.db.table_exists("Novo Associado"):
		return

	if not frappe.db.has_column("Novo Associado", "data_registro_provisorio_efetivado"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabNovo Associado`
		SET `data_registro_provisorio_efetivado` = DATE(`modified`)
		WHERE `registro_provisorio_efetivado` = 1
			AND `data_registro_provisorio_efetivado` IS NULL
		"""
	)

	frappe.db.commit()
