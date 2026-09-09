import frappe


def execute():
	"""Remove duplicatas de Agenda de Visitas por jovem (SUG-00046).

	Antes da trava adicionada ao controller, agendar uma visita para um jovem que
	já tinha uma podia deixar o registro antigo órfão no banco (o fluxo de
	reagendamento do portal do responsável cancelava só visitas com data futura
	e recriava sem checar duplicidade). Isso causou o envio da mensagem diária
	de visitas com um registro de data antiga que não deveria mais existir.

	Mantém, por jovem, o registro modificado mais recentemente — o que melhor
	reflete a última ação tomada — e apaga o restante.
	"""
	if not frappe.db.table_exists("Agenda de Visitas"):
		return

	duplicados = frappe.db.sql(
		"""
		SELECT `jovem`
		FROM `tabAgenda de Visitas`
		WHERE `jovem` IS NOT NULL AND `jovem` != ''
		GROUP BY `jovem`
		HAVING COUNT(*) > 1
		""",
		as_dict=True,
	)

	for row in duplicados:
		visitas = frappe.get_all(
			"Agenda de Visitas",
			filters={"jovem": row.jovem},
			fields=["name"],
			order_by="modified desc",
		)
		for visita in visitas[1:]:
			frappe.delete_doc("Agenda de Visitas", visita.name, ignore_permissions=True, force=True)

	frappe.db.commit()
