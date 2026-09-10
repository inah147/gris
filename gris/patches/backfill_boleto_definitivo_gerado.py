import frappe


def execute():
	"""Marca a etapa nova "boleto definitivo gerado" em quem já efetivou o registro definitivo.

	A etapa nasce desmarcada em todos os registros, e quem já está com o registro definitivo
	efetivado apareceria no funil como boleto pendente — exatamente o contrário do que a etapa
	existe para mostrar. Um registro definitivo efetivado só existe porque o boleto foi emitido
	e pago, então a conclusão é histórica, não uma suposição.

	Sem carimbo no histórico de etapas de propósito: ninguém marcou essa etapa, e a interface
	já sabe dizer "não registrado" no lugar de atribuir a conclusão a quem rodou a migração.
	"""
	if not frappe.db.table_exists("Novo Associado"):
		return

	if not frappe.db.has_column("Novo Associado", "boleto_definitivo_gerado"):
		return

	novo_associado = frappe.qb.DocType("Novo Associado")
	(
		frappe.qb.update(novo_associado)
		.set(novo_associado.boleto_definitivo_gerado, 1)
		.where(novo_associado.registro_definitivo_efetivado == 1)
	).run()

	frappe.db.commit()
