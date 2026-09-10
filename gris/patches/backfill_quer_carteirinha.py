import frappe


def execute():
	"""Marca "quer carteirinha" nos registros anteriores à existência da pergunta.

	O switch da carteirinha nasce ligado no formulário do responsável (``quer_carteirinha``
	em Novo Associado e em Responsavel Vinculo). Quem enviou os dados antes disso nunca teve
	a chance de recusar, e um ``0`` herdado do banco faria a recepção deixar de solicitar a
	carteirinha desses jovens sem que ninguém tivesse pedido isso.

	Entre errar solicitando de quem não queria e errar não solicitando de quem queria, o
	primeiro é o barato: alinhamos o legado ao mesmo default do formulário.

	Nos vínculos o valor é derivado de ``sera_registrado``, nos dois sentidos: quem não tem
	registro não tem carteirinha, e a coluna nasce com o default 1 em *todas* as linhas (é
	assim que o Frappe cria uma coluna Check nova), então zerar é obrigatório — não é um
	caso hipotético.
	"""
	if frappe.db.table_exists("Novo Associado") and frappe.db.has_column(
		"Novo Associado", "quer_carteirinha"
	):
		frappe.db.sql("UPDATE `tabNovo Associado` SET `quer_carteirinha` = 1")

	if frappe.db.table_exists("Responsavel Vinculo") and frappe.db.has_column(
		"Responsavel Vinculo", "quer_carteirinha"
	):
		frappe.db.sql(
			"UPDATE `tabResponsavel Vinculo` SET `quer_carteirinha` = IF(`sera_registrado` = 1, 1, 0)"
		)

	frappe.db.commit()
