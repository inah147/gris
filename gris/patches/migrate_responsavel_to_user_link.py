"""Migra Gestao de Tarefas.responsavel de string (nome) para Link -> User.

Para cada tarefa com `responsavel` nao vazio, tenta encontrar o User correto
percorrendo o Board associado ao Projeto e os Envolvidos do Projeto. Tarefas
sem mapeamento ficam com `responsavel` nulo e o caso e registrado em Error Log
para revisao manual.

Idempotente: tarefas ja com `responsavel` no formato de User name (contem '@')
sao puladas.
"""

from __future__ import annotations

import frappe


def execute() -> None:
	if not frappe.db.exists("DocType", "Gestao de Tarefas"):
		return
	if not frappe.db.exists("DocType", "Board"):
		return

	tarefas = frappe.get_all(
		"Gestao de Tarefas",
		filters={"responsavel": ["not in", (None, "")]},
		fields=["name", "responsavel", "board"],
		limit_page_length=0,
	)

	user_emails = {row.get("name") for row in frappe.get_all("User", fields=["name"])}

	envolvidos_por_projeto: dict[str, list[dict]] = {}

	for tarefa in tarefas:
		responsavel_anterior = (tarefa.get("responsavel") or "").strip()
		if not responsavel_anterior:
			continue

		if responsavel_anterior in user_emails:
			continue

		board_name = (tarefa.get("board") or "").strip()
		if not board_name:
			_clear_and_log(tarefa.get("name"), responsavel_anterior, "tarefa sem board")
			continue

		board = frappe.db.get_value(
			"Board",
			board_name,
			["referencia_doctype", "referencia_nome"],
			as_dict=True,
		)
		if not board or board.get("referencia_doctype") != "Projeto":
			_clear_and_log(
				tarefa.get("name"),
				responsavel_anterior,
				f"board {board_name} nao referencia Projeto",
			)
			continue

		projeto_name = (board.get("referencia_nome") or "").strip()
		if not projeto_name:
			_clear_and_log(
				tarefa.get("name"),
				responsavel_anterior,
				f"board {board_name} sem referencia_nome",
			)
			continue

		envolvidos = envolvidos_por_projeto.get(projeto_name)
		if envolvidos is None:
			envolvidos = frappe.get_all(
				"Envolvido no Projeto",
				filters={"parent": projeto_name, "parenttype": "Projeto"},
				fields=["nome", "email"],
				limit_page_length=0,
			)
			envolvidos_por_projeto[projeto_name] = envolvidos

		match_email = ""
		for envolvido in envolvidos:
			if (envolvido.get("nome") or "").strip() == responsavel_anterior:
				match_email = (envolvido.get("email") or "").strip()
				break

		if not match_email:
			_clear_and_log(
				tarefa.get("name"),
				responsavel_anterior,
				f"envolvido com nome '{responsavel_anterior}' nao encontrado no projeto {projeto_name}",
			)
			continue

		if match_email not in user_emails:
			_clear_and_log(
				tarefa.get("name"),
				responsavel_anterior,
				f"email '{match_email}' nao corresponde a um User",
			)
			continue

		frappe.db.set_value(
			"Gestao de Tarefas",
			tarefa.get("name"),
			"responsavel",
			match_email,
			update_modified=False,
		)


def _clear_and_log(tarefa_name: str, responsavel_anterior: str, motivo: str) -> None:
	frappe.db.set_value(
		"Gestao de Tarefas",
		tarefa_name,
		"responsavel",
		None,
		update_modified=False,
	)
	frappe.log_error(
		title="Tarefa orfa na migracao responsavel->User",
		message=(f"Tarefa: {tarefa_name}\nResponsavel anterior: {responsavel_anterior}\nMotivo: {motivo}"),
	)
