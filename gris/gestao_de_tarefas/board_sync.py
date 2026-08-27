"""Sync de envolvidos do Projeto para o Board vinculado.

Disparado via hook `on_update` em `Projeto` (registrado em `hooks.py`).
Faz uniao (append-only): adiciona novos envolvidos a `usuarios_autorizados`
do Board sem remover quem ja estava la.
"""

from __future__ import annotations

import frappe
from frappe.utils import nowdate


def sync_projeto_envolvidos(doc, method=None) -> None:
	board_names = _localizar_boards_do_projeto(doc.name)
	if not board_names:
		return

	usuarios = _coletar_usuarios_do_projeto(doc)
	if not usuarios:
		return

	for board_name in board_names:
		try:
			board = frappe.get_doc("Board", board_name)
		except frappe.DoesNotExistError:
			continue
		_unir_usuarios(board, usuarios)


def _localizar_boards_do_projeto(projeto_name: str) -> list[str]:
	names: set[str] = set()

	board_tarefas = frappe.db.get_value("Projeto", projeto_name, "board_tarefas")
	if board_tarefas:
		names.add(board_tarefas)

	for row in frappe.get_all(
		"Board",
		filters={"referencia_doctype": "Projeto", "referencia_nome": projeto_name},
		fields=["name"],
		limit_page_length=0,
	):
		names.add(row["name"])

	return list(names)


def _coletar_usuarios_do_projeto(projeto) -> dict[str, str]:
	"""Retorna {user_email: nivel_acesso} a partir dos envolvidos e coordenador."""
	usuarios: dict[str, str] = {}

	for envolvido in getattr(projeto, "envolvidos", None) or []:
		user = (getattr(envolvido, "user", None) or "").strip()
		if not user:
			email = (getattr(envolvido, "email", None) or "").strip()
			if email and frappe.db.exists("User", email):
				user = email
		if user:
			nivel = "Gerenciar" if getattr(envolvido, "coordenador", 0) else "Editar"
			if _peso(nivel) > _peso(usuarios.get(user, "")):
				usuarios[user] = nivel

	coordenador = (getattr(projeto, "coordenador", None) or "").strip()
	if coordenador:
		email = frappe.db.get_value("Associado", coordenador, "email")
		if email and frappe.db.exists("User", email):
			if _peso("Gerenciar") > _peso(usuarios.get(email, "")):
				usuarios[email] = "Gerenciar"

	return usuarios


def _peso(nivel: str) -> int:
	return {"Visualizar": 1, "Editar": 2, "Gerenciar": 3}.get(nivel or "", 0)


def _unir_usuarios(board, usuarios: dict[str, str]) -> None:
	existentes = {(row.user or "").strip(): row for row in (board.usuarios_autorizados or [])}
	mudou = False
	for user, nivel in usuarios.items():
		if not user:
			continue
		if user not in existentes:
			board.append(
				"usuarios_autorizados",
				{"user": user, "nivel_acesso": nivel, "adicionado_em": nowdate()},
			)
			mudou = True

	if not mudou:
		return

	board.flags.ignore_version = True
	board.save(ignore_permissions=True)
