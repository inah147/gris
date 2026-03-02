import json
import re

import frappe
from frappe.utils import cint

from gris.api.portal_access import enrich_context


def get_context(context):
	# Get current user
	user = frappe.session.user
	if user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/responsavel/beneficiarios"
		raise frappe.Redirect

	# Get Novo Associado ID from request
	novo_associado_name = frappe.form_dict.get("novo_associado")
	if not novo_associado_name:
		frappe.throw("Novo Associado não especificado.")

	# Find Responsavel linked to current user
	responsavel = frappe.get_value("Responsavel", {"email": user}, "name")
	if not responsavel:
		frappe.throw("Perfil de Responsável não encontrado para este usuário.")

	# Check permission via Responsavel Vinculo
	has_permission = frappe.db.exists(
		"Responsavel Vinculo",
		{"responsavel": responsavel, "beneficiario_novo_associado": novo_associado_name},
	)

	if not has_permission:
		frappe.throw("Você não tem permissão para editar este associado.")

	# Fetch Novo Associado data
	novo_associado = frappe.get_doc("Novo Associado", novo_associado_name)

	context.novo_associado = novo_associado

	# Fetch Responsibles via Responsavel Vinculo
	vinculos = frappe.get_all(
		"Responsavel Vinculo", filters={"beneficiario_novo_associado": novo_associado_name}, fields=["*"]
	)

	responsaveis = []
	family_info = {"guarda_unilateral": 0}

	for v in vinculos:
		# Capture family info from the first link (assuming they are synced)
		if not responsaveis:
			family_info["guarda_unilateral"] = cint(v.guarda_unilateral)

		if v.responsavel:
			resp_doc = frappe.get_doc("Responsavel", v.responsavel)
			responsaveis.append({"vinculo": v, "doc": resp_doc})

	responsaveis.sort(key=lambda x: (x["doc"].nome_completo or ""))

	# Ensure at least 2 items for the UI
	while len(responsaveis) < 2:
		responsaveis.append({"vinculo": {}, "doc": {}, "is_placeholder": True})

	context.responsaveis = responsaveis
	context.family_info = family_info

	# Fetch options for Select fields
	meta = frappe.get_meta("Novo Associado")
	context.options = {}
	for field in meta.fields:
		if field.fieldtype == "Select" and field.options:
			context.options[field.fieldname] = field.options.split("\n")

	# Sidebar context
	context.sidebar_title = "Painel do Responsável"
	context.active_link = "/responsavel/beneficiarios"
	enrich_context(context, "/responsavel/beneficiarios")


def format_phone(phone):
	if not phone:
		return phone

	# Remove non-digits
	digits = "".join(filter(str.isdigit, str(phone)))

	if not digits:
		return ""

	# If it doesn't start with country code (assuming Brazil +55 for now based on context)
	# Brazil numbers are usually 10 or 11 digits (2 digit area code + 8 or 9 digit number)
	if len(digits) in [10, 11]:
		return f"+55{digits}"

	# If it already has 55 at start (12 or 13 digits)
	if len(digits) in [12, 13] and digits.startswith("55"):
		return f"+{digits}"

	return phone


@frappe.whitelist()
def update_novo_associado(novo_associado_name, data, responsaveis_data=None):
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Você precisa estar logado.", frappe.PermissionError)

	responsavel = frappe.get_value("Responsavel", {"email": user}, "name")
	if not responsavel:
		frappe.throw("Perfil de Responsável não encontrado.")

	has_permission = frappe.db.exists(
		"Responsavel Vinculo",
		{"responsavel": responsavel, "beneficiario_novo_associado": novo_associado_name},
	)

	if not has_permission:
		frappe.throw("Você não tem permissão para editar este associado.")

	# Update Novo Associado
	doc = frappe.get_doc("Novo Associado", novo_associado_name)

	# Parse data if it's a string
	if isinstance(data, str):
		data = json.loads(data)

	guarda_unilateral = cint(data.get("guarda_unilateral", 0))
	data["guarda_unilateral"] = guarda_unilateral

	email_cobranca = (data.get("email_cobranca") or "").strip()
	telefone_cobranca = data.get("telefone_cobranca") or ""

	if not email_cobranca:
		frappe.throw("Email de cobrança é obrigatório.")

	if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email_cobranca):
		frappe.throw("Email de cobrança inválido.")

	phone_digits = "".join(filter(str.isdigit, str(telefone_cobranca)))
	if len(phone_digits) < 10:
		frappe.throw("Telefone de cobrança inválido.")

	data["email_cobranca"] = email_cobranca

	# Allowed fields to update
	allowed_fields = [
		"tipo_de_registro",
		"nome_completo",
		"data_de_nascimento",
		"etnia",
		"sexo",
		"estrangeiro",
		"pais_nascimento",
		"uf_de_nascimento",
		"cidade_de_nascimento",
		"rg",
		"orgao_expedidor",
		"cpf",
		"estado_civil",
		"religiao",
		"escolaridade",
		"profissao",
		"local_de_trabalho",
		"cep",
		"endereco",
		"numero",
		"complemento",
		"estado",
		"cidade",
		"bairro",
		"email",
		"celular",
		"telefone_secundario",
		"email_cobranca",
		"telefone_cobranca",
	]

	for field in allowed_fields:
		if field in data:
			val = data[field]
			if field in ["celular", "telefone_secundario", "telefone_cobranca"]:
				val = format_phone(val)
			doc.set(field, val)

	# Update status and flag indicating data submission
	doc.status = "Fazer Registro"
	doc.dados_para_registro_enviados = 1

	doc.save(ignore_permissions=True)

	# Update Family Info on ALL Links (Responsavel Vinculo)
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": novo_associado_name},
		fields=["name"],
	)
	for v in vinculos:
		frappe.db.set_value("Responsavel Vinculo", v.name, "guarda_unilateral", guarda_unilateral)

	# Update Responsibles
	if responsaveis_data:
		if isinstance(responsaveis_data, str):
			responsaveis_data = json.loads(responsaveis_data)

		for resp_item in responsaveis_data:
			resp_id = resp_item.get("name")

			# Handle New Responsible
			if not resp_id:
				# Check if we have enough data to create (skip empty placeholders)
				if not resp_item.get("nome_completo") and not resp_item.get("cpf"):
					continue

				# Create new Responsavel
				new_resp = frappe.new_doc("Responsavel")

				# Set fields
				resp_allowed_fields = [
					"cpf",
					"rg",
					"orgao_expedidor",
					"data_de_nascimento",
					"sexo",
					"estado_civil",
					"escolaridade",
					"profissao",
					"local_de_trabalho",
					"endereco",
					"numero",
					"complemento",
					"bairro",
					"cidade",
					"estado",
					"cep",
					"email",
					"celular",
					"telefone_secundario",
					"nome_completo",
				]

				# Field mapping for Responsavel (frontend -> backend)
				field_mapping = {"endereco": "endereço", "numero": "número", "profissao": "profissão"}

				for field in resp_allowed_fields:
					if field in resp_item:
						val = resp_item[field]
						if field in ["celular", "telefone_secundario"]:
							val = format_phone(val)

						target_field = field_mapping.get(field, field)
						new_resp.set(target_field, val)

				new_resp.save(ignore_permissions=True)
				resp_id = new_resp.name

				# Create Link
				new_link = frappe.new_doc("Responsavel Vinculo")
				new_link.beneficiario_novo_associado = novo_associado_name
				new_link.responsavel = resp_id
				new_link.guarda_unilateral = guarda_unilateral

				# Set specific link info
				if "é_guardiao_legal" in resp_item:
					new_link.é_guardiao_legal = resp_item["é_guardiao_legal"]

				new_link.save(ignore_permissions=True)

				continue

			# Verify if this responsible is linked to the Novo Associado
			# This is a security check to ensure user is not updating random responsibles
			# We also need to fetch the link name to update 'é_guardiao_legal'
			link_name = frappe.db.get_value(
				"Responsavel Vinculo",
				{"responsavel": resp_id, "beneficiario_novo_associado": novo_associado_name},
				"name",
			)

			if link_name:
				# Update Link specific fields
				if "é_guardiao_legal" in resp_item:
					frappe.db.set_value(
						"Responsavel Vinculo", link_name, "é_guardiao_legal", resp_item["é_guardiao_legal"]
					)

				resp_doc = frappe.get_doc("Responsavel", resp_id)

				# Allowed fields for Responsavel
				resp_allowed_fields = [
					"cpf",
					"rg",
					"orgao_expedidor",
					"data_de_nascimento",
					"sexo",
					"estado_civil",
					"escolaridade",
					"profissao",
					"local_de_trabalho",
					"endereco",
					"numero",
					"complemento",
					"bairro",
					"cidade",
					"estado",
					"cep",
					"email",
					"celular",
					"telefone_secundario",
					"nome_completo",
				]

				# Field mapping for Responsavel (frontend -> backend)
				field_mapping = {"endereco": "endereço", "numero": "número", "profissao": "profissão"}

				for field in resp_allowed_fields:
					if field in resp_item:
						val = resp_item[field]
						if field in ["celular", "telefone_secundario"]:
							val = format_phone(val)

						target_field = field_mapping.get(field, field)
						resp_doc.set(target_field, val)

				resp_doc.save(ignore_permissions=True)

	all_vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_novo_associado": novo_associado_name},
		fields=["name", "\u00e9_guardiao_legal"],
	)

	if guarda_unilateral:
		guardioes = [v for v in all_vinculos if cint(v.get("\u00e9_guardiao_legal")) == 1]
		if len(guardioes) != 1:
			frappe.throw("Com guarda unilateral, exatamente um responsável deve ser marcado como guardião legal.")
	else:
		for v in all_vinculos:
			if cint(v.get("\u00e9_guardiao_legal")) != 1:
				frappe.db.set_value("Responsavel Vinculo", v.name, "\u00e9_guardiao_legal", 1)

	return {"status": "success"}
