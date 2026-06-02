"""Cria e mantem o Board pessoal de cada usuario do GRIS.

Cada User (System User ou Website User) tem um Board pessoal com
`referencia_doctype="User"` e `referencia_nome=user.name`. Tarefas pessoais
do usuario vivem neste board.
"""

from __future__ import annotations

import frappe
from frappe.utils import get_fullname

USER_TYPES_PERMITIDOS = {"System User", "Website User"}
USUARIOS_IGNORADOS = {"Guest", "Administrator"}


def criar_board_pessoal(doc, method: str | None = None) -> str | None:
	"""Hook de `after_insert` em `User`. Cria Board pessoal idempotente.

	Retorna o nome do Board criado/existente, ou None se o usuario for ignorado.
	"""
	if doc is None:
		return None

	user_name = (getattr(doc, "name", "") or "").strip()
	if not user_name or user_name in USUARIOS_IGNORADOS:
		return None

	user_type = (getattr(doc, "user_type", "") or "").strip()
	if user_type and user_type not in USER_TYPES_PERMITIDOS:
		return None

	return ensure_user_board(user_name)


def ensure_user_board(user_name: str) -> str | None:
	"""Garante que o Board pessoal exista. Idempotente."""
	user_name = (user_name or "").strip()
	if not user_name:
		return None

	existing = frappe.db.get_value(
		"Board",
		{"referencia_doctype": "User", "referencia_nome": user_name},
		"name",
	)
	if existing:
		return existing

	titulo = f"Tarefas pessoais — {get_fullname(user_name) or user_name}"
	board = frappe.get_doc(
		{
			"doctype": "Board",
			"titulo": titulo,
			"referencia_doctype": "User",
			"referencia_nome": user_name,
		}
	).insert(ignore_permissions=True)
	return board.name
