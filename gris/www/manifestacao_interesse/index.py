import frappe
from frappe import _

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

	try:
		# Create User
		user = frappe.new_doc("User")
		user.email = email_responsavel
		user.first_name = nome_responsavel
		user.mobile_no = celular_responsavel
		user.enabled = 1
		user.send_welcome_email = 1
		user.insert(ignore_permissions=True)

		# Process Jovens data if needed
		# import json
		# if isinstance(jovens, str):
		# 	jovens_list = json.loads(jovens)
		# 	for jovem in jovens_list:
		# 		# Create records for each youth...
		# 		pass

		return {
			"status": "success",
			"message": "Sua manifestação de interesse foi registrada com sucesso! Um usuário foi criado para você. Verifique seu e-mail para definir sua senha e acessar o sistema.",
		}
	except Exception as e:
		frappe.log_error(f"Error in submit_interest: {e!s}")
		return {
			"status": "error",
			"message": "Ocorreu um erro ao processar sua solicitação. Por favor, tente novamente.",
		}
