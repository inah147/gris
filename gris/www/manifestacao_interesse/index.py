import html
import json

import frappe
from frappe import _
from frappe.utils import now

from gris.api.portal_cache_utils import get_uel_cached


def get_context(context):
	context.title = "Manifestação de Interesse"
	context.show_sidebar = False

	uel_data = get_uel_cached()
	if uel_data:
		context.logo = uel_data.get("logo")
		context.subtitle = f"{uel_data.get('tipo_uel', '')} {uel_data.get('nome_da_uel', '')} - {uel_data.get('numeral', '')}/{uel_data.get('regiao', '')}".strip()


@frappe.whitelist(allow_guest=True)
def submit_interest(
	nome_responsavel,
	email_responsavel,
	celular_responsavel,
	cpf_responsavel,
	jovens,
):
	if not email_responsavel:
		return {"status": "error", "message": "E-mail é obrigatório."}

	# Check if user exists
	if frappe.db.exists("User", email_responsavel):
		return {
			"status": "error",
			"message": "Já existe um usuário com este e-mail. Por favor, faça login para acompanhar seu processo.",
		}

	core_savepoint = None
	try:
		jovens_list = []
		if isinstance(jovens, str):
			jovens_list = json.loads(jovens)
		else:
			jovens_list = jovens or []

		last_resposta = None
		for jovem in jovens_list:
			resposta = frappe.get_doc(
				{
					"doctype": "Resposta Manifestacao de Interesse",
					"nome_do_responsavel": nome_responsavel,
					"email_do_responsavel": email_responsavel,
					"celular_do_responsavel": celular_responsavel,
					"cpf_do_responsavel": cpf_responsavel,
					"nome_do_jovem": jovem.get("nome_jovem", ""),
					"data_de_nascimento_do_jovem": jovem.get("data_nascimento_jovem", ""),
					"cpf_do_jovem": jovem.get("cpf_jovem", ""),
					"data_e_horario_de_resposta": now(),
					"dados_confirmados": 1,
					"aceite_lgpd": 1,
				}
			)
			resposta.insert(ignore_permissions=True)
			last_resposta = resposta

		core_savepoint = f"manifestacao_core_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(core_savepoint)

		# Create User
		user = frappe.new_doc("User")
		user.email = email_responsavel
		user.first_name = nome_responsavel
		user.mobile_no = celular_responsavel
		user.enabled = 1
		user.send_welcome_email = 0
		user.append("roles", {"role": "Responsavel"})
		user.insert(ignore_permissions=True)

		# Create or Get Responsavel
		responsavel_doc = None
		# Check existence by CPF since ID generation is handled by DocType
		existing_responsavel = frappe.db.exists("Responsavel", {"cpf": cpf_responsavel})

		if existing_responsavel:
			responsavel_doc = frappe.get_doc("Responsavel", existing_responsavel)
		else:
			responsavel_doc = frappe.get_doc(
				{
					"doctype": "Responsavel",
					"nome_completo": nome_responsavel,
					"email": email_responsavel,
					"celular": celular_responsavel,
					"cpf": cpf_responsavel,
				}
			)
			responsavel_doc.insert(ignore_permissions=True)

		# Process Jovens data
		for jovem in jovens_list:
			# Create or Get Novo Associado
			novo_associado_doc = None
			cpf_jovem = jovem.get("cpf_jovem")
			if cpf_jovem:
				existing_jovem = frappe.db.exists("Novo Associado", {"cpf": cpf_jovem})
				if existing_jovem:
					novo_associado_doc = frappe.get_doc("Novo Associado", existing_jovem)
				else:
					novo_associado_doc = frappe.get_doc(
						{
							"doctype": "Novo Associado",
							"nome_completo": jovem.get("nome_jovem"),
							"data_de_nascimento": jovem.get("data_nascimento_jovem"),
							"cpf": cpf_jovem,
						}
					)
					novo_associado_doc.insert(ignore_permissions=True)

			# Create Responsavel Vinculo
			if responsavel_doc and novo_associado_doc:
				# Check existence by link fields
				existing_vinculo = frappe.db.exists(
					"Responsavel Vinculo",
					{
						"responsavel": responsavel_doc.name,
						"beneficiario_novo_associado": novo_associado_doc.name,
					},
				)

				if not existing_vinculo:
					vinculo = frappe.get_doc(
						{
							"doctype": "Responsavel Vinculo",
							"responsavel": responsavel_doc.name,
							"beneficiario_novo_associado": novo_associado_doc.name,
						}
					)
					vinculo.insert(ignore_permissions=True)

		# Send welcome email manually to suppress "Welcome email sent" message
		try:
			user.send_welcome_mail_to_user()
		except Exception as e:
			frappe.log_error(
				"Erro envio welcome mail", f"Error sending welcome mail to {email_responsavel}: {e!s}"
			)

		if last_resposta:
			try:
				email_template = frappe.get_doc("Email Template", "Confirmacao Manifestacao Interesse")
				context = {"doc": last_resposta}

				# Fix potential HTML entities in Jinja logic if loaded from JSON
				template_content = email_template.response.replace("&gt;", ">").replace("&lt;", "<")

				message = frappe.render_template(template_content, context)
				subject = frappe.render_template(email_template.subject, context)

				frappe.sendmail(recipients=[email_responsavel], subject=subject, message=message, now=True)
				frappe.log_error("DEBUG EMAIL SUCCESS", f"Email sent to {email_responsavel}")
			except Exception as e:
				frappe.log_error("DEBUG EMAIL ERROR", str(e))

		return {
			"status": "success",
			"message": "Sua manifestação de interesse foi registrada com sucesso! Um usuário foi criado para você. Verifique seu e-mail para definir sua senha e acessar o sistema.",
		}
	except Exception as e:
		if core_savepoint:
			frappe.db.rollback(save_point=core_savepoint)
		frappe.log_error("Erro Manifestacao Interesse", f"Error in submit_interest: {e!s}")
		return {
			"status": "error",
			"message": "Ocorreu um erro ao processar sua solicitação. Por favor, tente novamente.",
		}
