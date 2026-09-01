import frappe


def execute():
	"""Preenche desde quando cada jovem está parado em "Aguardar Dados".

	O campo ``data_status_aguardar_dados`` passou a ser gravado pelo controller de Novo
	Associado quando o status entra em "Aguardar Dados", e é a base da escada de lembretes
	de preenchimento (ver ``gris.api.recepcao_mensagens``). Sem este backfill, quem já estava
	nesse status ficaria de fora dos lembretes até alguém salvar o registro de novo.

	A melhor aproximação disponível é a data da visita mais recente — o status é gravado logo
	depois da recepção realizada. Sem visita registrada, cai em ``modified``.
	"""
	if not frappe.db.table_exists("Novo Associado"):
		return

	if not frappe.db.has_column("Novo Associado", "data_status_aguardar_dados"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabNovo Associado` na
		LEFT JOIN (
			SELECT `jovem`, MAX(`data_da_visita`) AS `ultima_visita`
			FROM `tabAgenda de Visitas`
			GROUP BY `jovem`
		) av ON av.`jovem` = na.`name`
		SET na.`data_status_aguardar_dados` = COALESCE(av.`ultima_visita`, DATE(na.`modified`))
		WHERE na.`status` = 'Aguardar Dados'
			AND na.`data_status_aguardar_dados` IS NULL
		"""
	)

	frappe.db.commit()
