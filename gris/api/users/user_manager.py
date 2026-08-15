import uuid

import frappe
from frappe.utils import cint

from gris.api.users.roles import PERFIL_SEM_ACESSO, apply_role_profile, save_user_preserving_roles


def _logger():
	return frappe.logger("associate_user", allow_site=True, file_count=10)


def _should_auto_create_users() -> bool:
	"""Retorna se a criação automática de usuários para associados está habilitada."""
	return cint(frappe.db.get_single_value("Configuracoes de Associados", "criar_usuarios")) == 1


def _has_desk_access(user: str) -> bool:
	if not user or user == "Guest":
		return False

	return "Acesso ao Desk" in frappe.get_roles(user)


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


def _define_role_profile_por_funcao(categoria: str | None, funcao: str | None) -> str | None:
	"""Deriva o Role Profile a partir da categoria/função do associado.

	Retorna `None` quando não há mapeamento definido. Nesse caso o perfil atual
	do usuário **não deve ser alterado** automaticamente, sob risco de remover
	acessos já concedidos.
	"""
	categoria = (categoria or "").strip()
	funcao = (funcao or "").strip()

	if categoria == "Beneficiário":
		return "Beneficiário"

	if categoria == "Dirigente":
		if funcao in ("Comissão Fiscal",):
			return funcao
		return "Dirigente"

	if categoria == "Escotista" and funcao in ("Assistente", "Chefe de Seção"):
		return funcao

	return None


def _define_role_profile(associate):
	return _define_role_profile_por_funcao(
		getattr(associate, "categoria", None), getattr(associate, "funcao", None)
	)


@frappe.whitelist()
def create_associate_user(associate=None, associate_name=None, force=False):
	if associate_name and not associate:
		associate = frappe.get_doc("Associado", associate_name)

	if not associate:
		return

	if not force and not _should_auto_create_users():
		_logger().info(
			f"[CREATE] skip associate_name={getattr(associate, 'name', None)} reason=auto create disabled"
		)
		return

	# Na criação, a ausência de mapeamento vira perfil sem acesso (Guest):
	# o usuário nasce sem papéis e recebe acesso por concessão explícita.
	role_profile = _define_role_profile(associate) or PERFIL_SEM_ACESSO

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
def create_missing_associate_users():
	user = frappe.session.user if getattr(frappe.local, "session", None) else "Guest"
	if not _has_desk_access(user):
		frappe.throw("Sem permissão para criar usuários de associados.", frappe.PermissionError)

	associates = _get_associados()
	associate_emails = {
		(associate.id_escoteiros or "").strip().lower()
		for associate in associates
		if (associate.id_escoteiros or "").strip()
	}

	existing_users = set()
	if associate_emails:
		existing_users = {
			user_doc.name.lower()
			for user_doc in frappe.get_all(
				"User", filters={"name": ["in", list(associate_emails)]}, fields=["name"]
			)
		}

	results = {
		"total_associates": len(associates),
		"created": 0,
		"skipped_existing_user": 0,
		"skipped_invalid_status": 0,
		"skipped_invalid_domain": 0,
		"skipped_missing_data": 0,
		"errors": 0,
	}

	log = _logger()
	for associate in associates:
		email = (associate.id_escoteiros or "").strip().lower()

		if not email:
			results["skipped_missing_data"] += 1
			continue

		if not email.endswith("@escoteiros.org.br"):
			results["skipped_invalid_domain"] += 1
			continue

		if not _is_valid_associate(associate):
			results["skipped_invalid_status"] += 1
			continue

		if not associate.registro or not associate.nome_completo:
			results["skipped_missing_data"] += 1
			continue

		if email in existing_users:
			results["skipped_existing_user"] += 1
			continue

		try:
			associate.id_escoteiros = email
			create_associate_user(associate=associate, force=True)
			results["created"] += 1
			existing_users.add(email)
		except Exception:
			results["errors"] += 1
			tb = frappe.get_traceback()
			frappe.log_error(tb, f"create_missing_associate_users:{associate.name}")
			log.error(f"[CREATE BATCH] exception associate_name={associate.name}\n{tb}")

	return results


@frappe.whitelist()
def create_associate_user_manually(associate_name):
	user = frappe.session.user if getattr(frappe.local, "session", None) else "Guest"
	if not _has_desk_access(user):
		frappe.throw("Sem permissão para criar usuários de associados.", frappe.PermissionError)

	if not associate_name:
		frappe.throw("Associado não informado.")

	associate = frappe.get_doc("Associado", associate_name)
	email = (associate.id_escoteiros or "").strip().lower()

	if not email:
		frappe.throw("Associado sem ID Escoteiros informado.")

	if not email.endswith("@escoteiros.org.br"):
		frappe.throw("ID Escoteiros inválido. Use um e-mail @escoteiros.org.br.")

	if not _is_valid_associate(associate):
		frappe.throw("Associado com registro inválido para criação de usuário.")

	if not associate.registro or not associate.nome_completo:
		frappe.throw("Dados incompletos do associado para criação de usuário.")

	if frappe.db.exists("User", email):
		return {"created": 0, "already_exists": 1, "email": email}

	try:
		associate.id_escoteiros = email
		create_associate_user(associate=associate, force=True)
		return {"created": 1, "already_exists": 0, "email": email}
	except Exception:
		tb = frappe.get_traceback()
		frappe.log_error(tb, f"create_associate_user_manually:{associate_name}")
		_logger().error(f"[CREATE SINGLE] exception associate_name={associate_name}\n{tb}")
		raise


@frappe.whitelist()
def activate_associate_user(associate):
	user_doc = frappe.get_doc("User", associate.id_escoteiros)
	user_doc.enabled = 1
	# Gravar o usuário faz o Frappe recalcular os papéis a partir do perfil;
	# preservamos as concessões manuais.
	save_user_preserving_roles(user_doc)


@frappe.whitelist()
def deactivate_associate_user(user):
	user_doc = frappe.get_doc("User", user.name)
	user_doc.enabled = 0
	save_user_preserving_roles(user_doc)


def _sync_role_profile(user, associate, old_categoria=None, old_funcao=None, log=None):
	"""Sincroniza o Role Profile do usuário após mudança de função/categoria.

	Regra: a automação só substitui um perfil que ela mesma teria atribuído.
	Se o usuário está num perfil diferente do derivado da função/categoria
	anterior (ex.: "Diretoria Eleita" ou "Gestor Financeiro" definidos
	manualmente), o perfil é mantido — gravar `role_profile_name` zeraria todos
	os papéis do usuário e removeria acessos concedidos fora da automação.
	"""
	log = log or _logger()

	perfil_novo = _define_role_profile(associate)
	if not perfil_novo:
		log.info(
			f"[UPDATE] skip role profile associate_name={associate.name} "
			f"reason=sem mapeamento para categoria='{associate.categoria}' funcao='{associate.funcao}'"
		)
		return

	perfil_atual = user.role_profile_name
	if perfil_atual == perfil_novo:
		return

	perfil_anterior_derivado = _define_role_profile_por_funcao(old_categoria, old_funcao)
	perfil_gerenciado_pela_automacao = perfil_atual in (None, "", PERFIL_SEM_ACESSO, perfil_anterior_derivado)

	if not perfil_gerenciado_pela_automacao:
		log.info(
			f"[UPDATE] skip role profile associate_name={associate.name} "
			f"reason=perfil '{perfil_atual}' definido manualmente (derivado seria '{perfil_novo}')"
		)
		return

	resultado = apply_role_profile(user, perfil_novo)
	log.info(
		f"[UPDATE] role profile associate_name={associate.name} "
		f"'{resultado['perfil_anterior']}' -> '{resultado['perfil_novo']}' "
		f"papeis_preservados={resultado['papeis_preservados']}"
	)


@frappe.whitelist()
def update_associate_user(
	associate_name,
	old_funcao_categoria=None,
	new_funcao_categoria=None,
	old_categoria=None,
	old_funcao=None,
	**_kwargs,
):
	log = _logger()
	if not _should_auto_create_users():
		log.info(f"[UPDATE] skip associate_name={associate_name} reason=auto create disabled")
		return
	try:
		if not frappe.db.exists("Associado", associate_name):
			return

		associate = frappe.get_doc("Associado", associate_name)

		if not associate.id_escoteiros:
			log.info(f"[UPDATE] skip associate_name={associate_name} reason=missing id_escoteiros")
			return

		user = _get_user(associate.id_escoteiros)
		if not user:
			log.info(f"[UPDATE] user not found for associate_name={associate_name}, creating")
			create_associate_user(associate=associate)
			return

		# Ativar / desativar conforme validade
		valid = _is_valid_associate(associate)
		if user.enabled and not valid:
			deactivate_associate_user(user)
		elif (not user.enabled) and valid:
			activate_associate_user(associate)

		# Atualizar role profile se mudou função/categoria
		if old_funcao_categoria != new_funcao_categoria:
			# Recarrega o usuário: activate/deactivate acima gravam o documento.
			user = _get_user(associate.id_escoteiros) or user
			_sync_role_profile(user, associate, old_categoria, old_funcao, log)

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
