import frappe


@frappe.whitelist()
def update_novo_associado(name, responsavel_recepcao=None, status=None, ramo=None, motivo_desistencia=None):
	doc = frappe.get_doc("Novo Associado", name)
	if responsavel_recepcao:
		doc.responsavel_recepcao = responsavel_recepcao
	if status:
		doc.status = status
	if ramo:
		doc.ramo = ramo
	if motivo_desistencia:
		doc.motivo_desistencia = motivo_desistencia
	doc.save()
	return doc.as_dict()


@frappe.whitelist()
def processar_desistencia(novo_associado_name, motivo):
	# 1. Get Novo Associado
	if not frappe.db.exists("Novo Associado", novo_associado_name):
		return

	# 2. Find Responsavel Vinculo
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": novo_associado_name},
		fields=["name", "responsavel"],
	)

	# 3. Delete Novo Associado
	frappe.delete_doc("Novo Associado", novo_associado_name)

	# 4. Process Responsavel
	for vinculo in vinculos:
		responsavel_id = vinculo.responsavel

		# Delete the link
		frappe.delete_doc("Responsavel Vinculo", vinculo.name)

		# Check if Responsavel has other links
		other_links = frappe.get_all("Responsavel Vinculo", filters={"responsavel": responsavel_id}, limit=1)

		if not other_links:
			# No other links, delete Responsavel and User
			if frappe.db.exists("Responsavel", responsavel_id):
				responsavel_doc = frappe.get_doc("Responsavel", responsavel_id)
				user_email = responsavel_doc.email

				frappe.delete_doc("Responsavel", responsavel_id)

				if user_email and frappe.db.exists("User", user_email):
					frappe.delete_doc("User", user_email)

	return {"status": "success"}


@frappe.whitelist()
def enviar_para_fila_espera(novo_associado_name):
	if not frappe.db.exists("Novo Associado", novo_associado_name):
		frappe.throw("Novo Associado não encontrado")

	doc = frappe.get_doc("Novo Associado", novo_associado_name)

	# Update status
	doc.status = "Fila de espera"
	doc.save()

	# Create Fila de Espera entry
	fila = frappe.get_doc(
		{
			"doctype": "Fila de Espera",
			"associado": novo_associado_name,
			"ramo": doc.ramo,
			"dt_inclusao_fila": frappe.utils.now(),
		}
	)
	fila.insert()

	return {"status": "success"}


@frappe.whitelist()
def confirmar_visita(novo_associado_name):
	# Find the latest visit for this associate
	visits = frappe.get_all(
		"Agenda de Visitas",
		filters={"jovem": novo_associado_name},
		order_by="data_da_visita desc",
		limit=1,
	)

	if not visits:
		frappe.throw("Nenhuma visita agendada encontrada para este associado.")

	visit_name = visits[0].name
	frappe.db.set_value("Agenda de Visitas", visit_name, "visita_confirmada", 1)

	return {"status": "success"}


@frappe.whitelist()
def remover_confirmacao_visita(novo_associado_name):
	# Find the latest visit for this associate
	visits = frappe.get_all(
		"Agenda de Visitas",
		filters={"jovem": novo_associado_name},
		order_by="data_da_visita desc",
		limit=1,
	)

	if not visits:
		frappe.throw("Nenhuma visita agendada encontrada para este associado.")

	visit_name = visits[0].name
	frappe.db.set_value("Agenda de Visitas", visit_name, "visita_confirmada", 0)

	return {"status": "success"}


@frappe.whitelist()
def registrar_recepcao_realizada(novo_associado_name):
	if not frappe.db.exists("Novo Associado", novo_associado_name):
		frappe.throw("Novo Associado não encontrado")

	doc = frappe.get_doc("Novo Associado", novo_associado_name)
	doc.status = "Aguardar Dados"
	doc.primeira_visita_realizada = 1
	doc.save()

	return {"status": "success"}
