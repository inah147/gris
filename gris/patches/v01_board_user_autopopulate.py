"""Backfill da child table `Board User` em Boards existentes.

Popula `usuarios_autorizados` em todos os Boards nao-pessoais que ainda
nao tem usuarios listados:

- Boards de Projeto: adiciona envolvidos do projeto + coordenador.
- Boards de Festa: adiciona o `owner` do board.
- Boards soltos (sem referencia): adiciona o `owner` do board.

Idempotente: pula Boards que ja tem entradas em `usuarios_autorizados`.
"""

from __future__ import annotations

import frappe
from frappe.utils import nowdate


def execute() -> None:
	if not frappe.db.exists("DocType", "Board"):
		return
	if not frappe.db.exists("DocType", "Board User"):
		return

	boards = frappe.get_all(
		"Board",
		filters=[["referencia_doctype", "!=", "User"]],
		fields=["name", "referencia_doctype", "referencia_nome", "owner"],
		limit_page_length=0,
	)

	for board_row in boards:
		try:
			_processar_board(board_row)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Falha ao popular Board User em {board_row.get('name')}",
			)


def _processar_board(board_row: dict) -> None:
	board_name = board_row["name"]
	board = frappe.get_doc("Board", board_name)
	if board.usuarios_autorizados:
		return

	usuarios: set[str] = set()
	owner = (board.owner or "").strip()
	if owner and owner not in {"Administrator", "Guest"} and frappe.db.exists("User", owner):
		usuarios.add(owner)

	ref_dt = (board.referencia_doctype or "").strip()
	ref_nome = (board.referencia_nome or "").strip()
	if ref_dt == "Projeto" and ref_nome and frappe.db.exists("Projeto", ref_nome):
		usuarios.update(_envolvidos_do_projeto(ref_nome))

	if not usuarios:
		return

	for user in usuarios:
		board.append("usuarios_autorizados", {"user": user, "adicionado_em": nowdate()})

	board.flags.ignore_version = True
	board.save(ignore_permissions=True)


def _envolvidos_do_projeto(projeto_name: str) -> set[str]:
	usuarios: set[str] = set()

	envolvidos = frappe.get_all(
		"Envolvido no Projeto",
		filters={"parent": projeto_name, "parenttype": "Projeto"},
		fields=["user", "email"],
	)
	for row in envolvidos:
		user = (row.get("user") or "").strip()
		if not user:
			email = (row.get("email") or "").strip()
			if email and frappe.db.exists("User", email):
				user = email
		if user:
			usuarios.add(user)

	coordenador = frappe.db.get_value("Projeto", projeto_name, "coordenador")
	if coordenador:
		email = frappe.db.get_value("Associado", coordenador, "email")
		if email and frappe.db.exists("User", email):
			usuarios.add(email)

	return usuarios
