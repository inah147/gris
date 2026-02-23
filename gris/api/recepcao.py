import frappe
from frappe import _
from frappe.utils import format_datetime, get_fullname, strip_html


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
def processar_desistencia(novo_associado_name, motivo=None):
	# 1. Get Novo Associado
	if not frappe.db.exists("Novo Associado", novo_associado_name):
		return

	novo_associado = frappe.get_doc("Novo Associado", novo_associado_name)
	cpf = novo_associado.cpf

	# 2. Delete scheduled visits
	frappe.db.delete("Agenda de Visitas", {"jovem": novo_associado_name})

	# 3. Handle Associado (Anonimizar + Desligamento context)
	# Check if effective
	is_effective = (
		novo_associado.registro_provisorio_efetivado or novo_associado.registro_definitivo_efetivado
	)

	if is_effective and cpf:
		# Try to find Associado by Name (CPF)
		associado_name = cpf
		if frappe.db.exists("Associado", associado_name):
			assoc_doc = frappe.get_doc("Associado", associado_name)

			# Anonimize fields
			fields_to_anonymize = [
				"nome_completo",
				"email",
				"telefone",
				"cep_residencia",
				"numero_residencia",
				"nome_responsavel_1",
				"cpf_responsavel_1",
				"email_responsavel_1",
				"telefone_responsavel_1",
				"nome_responsavel_2",
				"cpf_responsavel_2",
				"email_responsavel_2",
				"telefone_responsavel_2",
				"religiao",
				"etnia",
			]

			for field in fields_to_anonymize:
				if assoc_doc.meta.has_field(field):
					assoc_doc.set(field, "ANONIMIZADO")

			# Historico de Desligamento
			has_open_history = False
			if assoc_doc.historico_no_grupo:
				for row in assoc_doc.historico_no_grupo:
					if not row.data_de_desligamento:
						row.data_de_desligamento = frappe.utils.today()
						has_open_history = True
						break

			assoc_doc.save(ignore_permissions=True)

	# 4. Find and Clean Responsavel Vinculo
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": novo_associado_name},
		fields=["name", "responsavel"],
	)

	for vinculo in vinculos:
		responsavel_id = vinculo.responsavel

		# Delete the link
		frappe.delete_doc("Responsavel Vinculo", vinculo.name, ignore_permissions=True)

		# Check if Responsavel has other links (Vinculo)
		other_links_count = frappe.db.count("Responsavel Vinculo", {"responsavel": responsavel_id})

		if other_links_count == 0:
			# Check if Responsavel has Survey Answer
			# Note: Doctype has a typo 'Pesqusa' which is correct in the system
			if frappe.db.exists("Pesqusa de Novos Associados", {"responsavel": responsavel_id}):
				# Unlink Responsavel from Survey to keep the survey data but allow user deletion
				frappe.db.set_value(
					"Pesqusa de Novos Associados", {"responsavel": responsavel_id}, "responsavel", None
				)

			# No other links, delete Responsavel and User
			if frappe.db.exists("Responsavel", responsavel_id):
				responsavel_doc = frappe.get_doc("Responsavel", responsavel_id)
				user_email = responsavel_doc.email

				frappe.delete_doc("Responsavel", responsavel_id, ignore_permissions=True)

				if user_email and frappe.db.exists("User", user_email):
					frappe.delete_doc("User", user_email, ignore_permissions=True)

	# 5. Cleanup Fila de Espera (if any)
	frappe.db.delete("Fila de Espera", {"associado": novo_associado_name})

	# 6. Delete Novo Associado
	frappe.delete_doc("Novo Associado", novo_associado_name, ignore_permissions=True)

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


@frappe.whitelist()
def adicionar_comentario(novo_associado_name: str, content: str):
	"""Cria um Comment vinculado ao Novo Associado para uso interno da recepção."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Você precisa estar autenticado."), frappe.PermissionError)

	if not novo_associado_name:
		frappe.throw(_("Informe o registro do associado."))

	content = (content or "").strip()
	if not content:
		frappe.throw(_("O comentário não pode estar vazio."))

	# Verifica se o registro existe e se o usuário tem permissão de escrita
	doc = frappe.get_doc("Novo Associado", novo_associado_name)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para comentar."), frappe.PermissionError)

	comment = frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "Novo Associado",
			"reference_name": novo_associado_name,
			"content": content,
		}
	)
	comment.insert()

	clean_text = strip_html((content or "").replace("</p>", "\n").replace("<br>", "\n"))

	return {
		"name": comment.name,
		"content": comment.content,
		"content_text": clean_text,
		"owner": comment.owner,
		"owner_fullname": get_fullname(comment.owner),
		"creation": format_datetime(comment.creation, "dd/MM/yyyy HH:mm"),
	}


@frappe.whitelist()
def editar_comentario(comment_name: str, content: str):
	"""Edita um comentário existente se o usuário for dono ou tiver permissão de escrita no registro."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Você precisa estar autenticado."), frappe.PermissionError)

	content = (content or "").strip()
	if not content:
		frappe.throw(_("O comentário não pode estar vazio."))

	if not comment_name:
		frappe.throw(_("Comentário inválido."))

	comment = frappe.get_doc("Comment", comment_name)
	if comment.reference_doctype != "Novo Associado":
		frappe.throw(_("Edição não permitida."), frappe.PermissionError)

	ref_name = comment.reference_name
	if not ref_name or not frappe.db.exists("Novo Associado", ref_name):
		frappe.throw(_("Registro relacionado não encontrado."))

	ref_doc = frappe.get_doc("Novo Associado", ref_name)

	# Pode editar se for dono ou tiver permissão de escrita no Doc
	if comment.owner != frappe.session.user and not ref_doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para editar este comentário."), frappe.PermissionError)

	comment.content = content
	comment.save()

	clean_text = strip_html((content or "").replace("</p>", "\n").replace("<br>", "\n"))

	return {
		"name": comment.name,
		"content": comment.content,
		"content_text": clean_text,
		"owner": comment.owner,
		"owner_fullname": get_fullname(comment.owner),
		"creation": format_datetime(comment.creation, "dd/MM/yyyy HH:mm"),
	}
