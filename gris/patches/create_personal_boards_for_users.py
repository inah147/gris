"""Cria um Board pessoal para cada Usuario existente que ainda nao possui.

Garante paridade com o hook `after_insert` de User, que passou a criar um
Board pessoal automaticamente para usuarios novos.
"""

from __future__ import annotations

import frappe

from gris.gestao_de_tarefas.user_board import (
	USER_TYPES_PERMITIDOS,
	USUARIOS_IGNORADOS,
	ensure_user_board,
)


def execute() -> None:
	if not frappe.db.exists("DocType", "Board"):
		return
	if not frappe.db.exists("DocType", "User"):
		return

	users = frappe.get_all(
		"User",
		filters={
			"enabled": 1,
			"user_type": ["in", list(USER_TYPES_PERMITIDOS)],
			"name": ["not in", list(USUARIOS_IGNORADOS)],
		},
		pluck="name",
		limit_page_length=0,
	)

	for user_name in users:
		try:
			ensure_user_board(user_name)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Falha ao criar Board pessoal para usuario {user_name}",
			)
