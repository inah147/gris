"""Permission hooks para Board e Gestao de Tarefas.

Boards pessoais (`referencia_doctype='User'`) sao visiveis apenas para o
proprio dono e para System Managers. Boards de Projeto e soltos sao visiveis
para usuarios listados em `usuarios_autorizados`. Boards de Festa podem ser
lidos por qualquer usuario logado, mas so a equipe da festa (nivel Editar ou
Gerenciar) e o papel "Gestor de festas" editam. Tarefas herdam a visibilidade
do board ao qual pertencem.

As condicoes de listagem (`*_permission_query_conditions`) seguem restritas aos
membros: a leitura aberta dos quadros de festa vale ao abrir o quadro, sem
inundar o indice /gestao_tarefas com todas as festas.
"""

from __future__ import annotations

import frappe

PAPEL_GESTOR_DE_FESTAS = "Gestor de festas"
NIVEIS_QUE_EDITAM = {"Editar", "Gerenciar"}
PTYPES_DE_LEITURA = {None, "read", "print", "email", "export", "report"}


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

	if referencia_doctype == "Festa":
		if ptype in PTYPES_DE_LEITURA:
			return bool(user) and user != "Guest"
		return _pode_editar_board_festa(doc, user)

	autorizados = getattr(doc, "usuarios_autorizados", None) or []
	return any((getattr(row, "user", None) or "").strip() == user for row in autorizados)


def _pode_editar_board_festa(doc, user: str) -> bool:
	if PAPEL_GESTOR_DE_FESTAS in frappe.get_roles(user):
		return True
	return any(
		(getattr(row, "user", None) or "").strip() == user
		and (getattr(row, "nivel_acesso", None) or "").strip() in NIVEIS_QUE_EDITAM
		for row in (getattr(doc, "usuarios_autorizados", None) or [])
	)


def pode_acessar_board(board_name: str, user: str | None = None, *, editar: bool = False) -> bool:
	"""Decide se o usuario le (ou edita, com `editar=True`) as tarefas do quadro.

	Quadro de festa: aplica direto a regra de `board_has_permission`, sem passar
	pela permissao por papel do DocType Board (concedida so aos papeis de
	projeto), para que quem nao recebeu esses papeis tambem leia o quadro.

	Demais quadros: mantem a regra anterior (papel + membro), em que ler basta
	para criar e mover tarefas.
	"""
	user = user or frappe.session.user
	board = frappe.get_doc("Board", board_name)
	if (board.referencia_doctype or "").strip() == "Festa":
		return board_has_permission(board, ptype="write" if editar else "read", user=user)
	return bool(frappe.has_permission("Board", doc=board, ptype="read", user=user))


def gestao_de_tarefas_permission_query_conditions(user: str | None = None) -> str:
	user = user or frappe.session.user
	if user == "Administrator" or _user_is_system_manager(user):
		return ""

	escaped_user = frappe.db.escape(user)
	board_clause = _board_visibility_clause("tabBoard", escaped_user)
	return f"`tabGestao de Tarefas`.`board` IN (SELECT `name` FROM `tabBoard` WHERE {board_clause})"


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
