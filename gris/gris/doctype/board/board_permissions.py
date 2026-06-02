"""Permission hooks para Board e Gestao de Tarefas.

Boards pessoais (`referencia_doctype='User'`) sao visiveis apenas para o
proprio dono e para System Managers. Boards nao-pessoais (Projeto, Festa
ou soltos) sao visiveis para usuarios listados em `usuarios_autorizados`.
Tarefas herdam a visibilidade do board ao qual pertencem.
"""

from __future__ import annotations

import frappe


def _user_is_system_manager(user: str | None) -> bool:
	if not user:
		return False
	return "System Manager" in frappe.get_roles(user)


def _board_visibility_clause(table_alias: str, escaped_user: str) -> str:
	"""Clausula SQL para boards visiveis ao usuario nao-administrador."""
	return (
		f"("
		f"(`{table_alias}`.`referencia_doctype` = 'User' "
		f"AND `{table_alias}`.`referencia_nome` = {escaped_user})"
		f" OR `{table_alias}`.`name` IN ("
		f"SELECT `parent` FROM `tabBoard User` "
		f"WHERE `parenttype` = 'Board' AND `user` = {escaped_user}"
		f")"
		f")"
	)


def board_permission_query_conditions(user: str | None = None) -> str:
	user = user or frappe.session.user
	if user == "Administrator" or _user_is_system_manager(user):
		return ""

	escaped_user = frappe.db.escape(user)
	return _board_visibility_clause("tabBoard", escaped_user)


def board_has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator" or _user_is_system_manager(user):
		return True

	referencia_doctype = (getattr(doc, "referencia_doctype", "") or "").strip()
	referencia_nome = (getattr(doc, "referencia_nome", "") or "").strip()

	if referencia_doctype == "User":
		return referencia_nome == user

	autorizados = getattr(doc, "usuarios_autorizados", None) or []
	return any((getattr(row, "user", None) or "").strip() == user for row in autorizados)


def gestao_de_tarefas_permission_query_conditions(user: str | None = None) -> str:
	user = user or frappe.session.user
	if user == "Administrator" or _user_is_system_manager(user):
		return ""

	escaped_user = frappe.db.escape(user)
	board_clause = _board_visibility_clause("tabBoard", escaped_user)
	return (
		f"`tabGestao de Tarefas`.`board` IN ("
		f"SELECT `name` FROM `tabBoard` WHERE {board_clause}"
		f")"
	)


def gestao_de_tarefas_has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator" or _user_is_system_manager(user):
		return True

	board_name = (getattr(doc, "board", "") or "").strip()
	if not board_name:
		return True

	try:
		board = frappe.get_cached_doc("Board", board_name)
	except frappe.DoesNotExistError:
		return True

	return board_has_permission(board, ptype=ptype, user=user)
