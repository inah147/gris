import uuid

import frappe


def _logger():
	return frappe.logger("associate_user", allow_site=True, file_count=10)


# 1. Recuperar lista de associados
def _get_associados():
	associates = frappe.get_all(
		"Associado",
		fields=[
			"name",
			"id_escoteiros",
			"status",
			"status_no_grupo",
			"nome_completo",
			"categoria",
			"funcao",
			"registro",
		],
	)
	return associates


def _get_associate(registro):
	user = frappe.get_doc("Associado", registro)
	return user


# 2. Recuperar lista de usuários
def _get_users():
	users = frappe.get_list("User", filters={"enabled": 1}, fields=["name", "full_name", "email", "enabled"])
	return users


def _get_user(email):
	"""Return User doc or None if email is falsy or user doesn't exist."""
	if not email:
		return None
	try:
		return frappe.get_doc("User", email)
	except frappe.DoesNotExistError:
		return None
	except Exception:
		# swallow unexpected errors and return None to keep caller defensive
		return None


def _is_valid_associate(associate):
	return associate.status != "Vencido" and associate.status_no_grupo != "Inativo"


# 3. Selecionar usuários a serem criados
def _associate_users_to_create_or_activate(associates, users):
	user_emails = [user.name for user in users]
	deactivated_user_emails = [user.name for user in users if user.enabled == 0]

	users_to_create = []
	users_to_activate = []

	for associate in associates:
		if (
			associate.id_escoteiros is not None
			and _is_valid_associate(associate)
			and associate.id_escoteiros not in user_emails
		):
			users_to_create.append(associate)

		if (
			associate.id_escoteiros is not None
			and _is_valid_associate(associate)
			and associate.id_escoteiros in deactivated_user_emails
		):
			users_to_activate.append(associate)

	return users_to_create, users_to_activate


# 4. Users to deactivate
def _associate_users_to_deactivate(associates, users):
	associate_id_escoteiros = [
		associate.id_escoteiros for associate in associates if not _is_valid_associate(associate)
	]

	users_to_deactivate = []

	for user in users:
		if user.enabled == 1 and user.email in associate_id_escoteiros:
			users_to_deactivate.append(user)

	return users_to_deactivate


def _define_role_profile(associate):
	# if beneficiary
	role_profile = "Guest"
	if associate.categoria == "Beneficiário":
		role_profile = "Beneficiário"

	if associate.categoria == "Dirigente":
		if associate.funcao in ["Comissão Fiscal"]:
			role_profile = associate.funcao

		role_profile = "Dirigente"

	if associate.categoria == "Escotista":
		if associate.funcao in ["Assistente"]:
			role_profile = associate.funcao

	return role_profile


@frappe.whitelist()
def create_associate_user(associate):
	role_profile = _define_role_profile(associate)

	if associate.registro and associate.id_escoteiros:
		registro = associate.registro.split("-")[0]
		enabled = 1 if _is_valid_associate(associate) else 0

		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": associate.id_escoteiros,
				"first_name": associate.nome_completo.split(" ")[0],
				"last_name": " ".join(associate.nome_completo.split(" ")[1:]),
				"new_password": f"gepim{registro}",
				"send_welcome_email": 1,
				"role_profile_name": role_profile,
				"reset_password_key": str(uuid.uuid4()),
				"enabled": enabled,
			}
		)
		user.insert()


@frappe.whitelist()
def activate_associate_user(associate):
	user_doc = frappe.get_doc("User", associate.id_escoteiros)
	user_doc.enabled = 1
	user_doc.save()


@frappe.whitelist()
def deactivate_associate_user(user):
	user_doc = frappe.get_doc("User", user.name)
	user_doc.enabled = 0
	user_doc.save()


@frappe.whitelist()
def update_associate_user(associate_name, old_funcao_categoria=None, new_funcao_categoria=None, **_kwargs):
	log = _logger()
	try:
		if not frappe.db.exists("Associado", associate_name):
			return

		associate = frappe.get_doc("Associado", associate_name)

		if not associate.id_escoteiros:
			log.info(f"[UPDATE] skip associate_name={associate_name} reason=missing id_escoteiros")
			return

		user = _get_user(associate.id_escoteiros)
		if not user:
			log.info(f"[UPDATE] skip associate_name={associate_name} reason=user not found")
			return

		# Ativar / desativar conforme validade
		valid = _is_valid_associate(associate)
		if user.enabled and not valid:
			deactivate_associate_user(user)
		elif (not user.enabled) and valid:
			activate_associate_user(associate)

		# Atualizar role profile se mudou função/categoria
		if old_funcao_categoria != new_funcao_categoria:
			role_profile = _define_role_profile(associate)
			if role_profile and user.role_profile_name != role_profile:
				user.role_profile_name = role_profile
				user.save(ignore_permissions=True)

		log.info(f"[UPDATE] done associate_name={associate_name}")

	except Exception:
		tb = frappe.get_traceback()
		frappe.log_error(tb, f"update_associate_user:{associate_name}")
		log.error(f"[UPDATE] exception associate_name={associate_name}\n{tb}")


@frappe.whitelist()
def manage_associate_users():
	associates = _get_associados()
	users = _get_users()

	users_to_create, users_to_activate = _associate_users_to_create_or_activate(associates, users)
	users_to_deactivate = _associate_users_to_deactivate(associates, users)

	print(users_to_deactivate)

	for associate in users_to_create:
		create_associate_user(associate)

	for associate in users_to_activate:
		activate_associate_user(associate)

	for user in users_to_deactivate:
		deactivate_associate_user(user)
