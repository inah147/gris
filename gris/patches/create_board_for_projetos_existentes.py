"""Cria um Board de tarefas para cada Projeto existente que ainda nao tem
`board_tarefas` preenchido. Garante paridade com `Projeto.after_insert`
que passou a criar Board automaticamente para projetos novos.
"""

from __future__ import annotations

import frappe


def execute() -> None:
	if not frappe.db.exists("DocType", "Board"):
		return
	if not frappe.db.exists("DocType", "Projeto"):
		return

	projetos = frappe.get_all(
		"Projeto",
		filters={"board_tarefas": ["in", (None, "")]},
		pluck="name",
		limit_page_length=0,
	)

	for projeto_name in projetos:
		try:
			_create_board_for_projeto(projeto_name)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Falha ao criar Board para projeto {projeto_name}",
			)


def _create_board_for_projeto(projeto_name: str) -> None:
	existing_board = frappe.db.get_value(
		"Board",
		{"referencia_doctype": "Projeto", "referencia_nome": projeto_name},
		"name",
	)
	if existing_board:
		frappe.db.set_value(
			"Projeto", projeto_name, "board_tarefas", existing_board, update_modified=False
		)
		return

	board = frappe.get_doc(
		{
			"doctype": "Board",
			"titulo": f"Tarefas — {projeto_name}",
			"referencia_doctype": "Projeto",
			"referencia_nome": projeto_name,
		}
	).insert(ignore_permissions=True)

	frappe.db.set_value(
		"Projeto", projeto_name, "board_tarefas", board.name, update_modified=False
	)
