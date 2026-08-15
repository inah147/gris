from __future__ import annotations

import frappe

from gris.api.users.roles import add_user_roles

PROJECT_ROLES = ("Visualizador de projetos", "Editor de projetos")
EXCLUDED_USERS = ("Guest",)


def execute():
	available_roles = tuple(
		frappe.get_all("Role", filters={"name": ("in", PROJECT_ROLES)}, pluck="name")
	)
	if not available_roles:
		return

	users = frappe.get_all("User", filters={"name": ("not in", EXCLUDED_USERS)}, pluck="name")
	if not users:
		return

	existing_user_roles = frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "role": ("in", available_roles)},
		fields=["parent", "role"],
		limit_page_length=0,
	)
	existing_pairs = {(row.parent, row.role) for row in existing_user_roles}

	for user_name in users:
		roles_to_add = [role for role in available_roles if (user_name, role) not in existing_pairs]
		if not roles_to_add:
			continue

		# add_roles() grava o usuário e faz o Frappe repopular a lista de papéis a
		# partir do Role Profile, removendo concessões manuais. Concedemos de
		# forma aditiva.
		add_user_roles(user_name, roles_to_add)
