"""Backfill de `nivel_acesso` em Board Users existentes.

Define nivel inicial seguindo as regras:
- Owner do Board (criador): Gerenciar.
- Coordenador de Projeto (linha em Envolvido no Projeto com flag coordenador): Gerenciar.
- Coordenador do campo `Projeto.coordenador`: Gerenciar.
- Outros envolvidos do Projeto: Editar.
- Demais entradas existentes (provavelmente vindas do owner em boards de Festa
  ou soltos): Gerenciar para o owner, Visualizar para os outros.

Idempotente: pula registros que ja tem `nivel_acesso` preenchido nao-default.
"""

from __future__ import annotations

import frappe

NIVEIS = {"Gerenciar", "Editar", "Visualizar"}
PESO = {"Visualizar": 1, "Editar": 2, "Gerenciar": 3}


def execute() -> None:
	if not frappe.db.exists("DocType", "Board User"):
		return
	if not frappe.db.exists("DocType", "Board"):
		return

	boards = frappe.get_all(
		"Board",
		filters=[["referencia_doctype", "!=", "User"]],
		fields=["name", "owner", "referencia_doctype", "referencia_nome"],
		limit_page_length=0,
	)

	for board_row in boards:
		try:
			_processar_board(board_row)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Falha ao backfill nivel_acesso Board {board_row.get('name')}",
			)


def _processar_board(board_row: dict) -> None:
	board_name = board_row["name"]
	rows = frappe.get_all(
		"Board User",
		filters={"parent": board_name, "parenttype": "Board"},
		fields=["name", "user", "nivel_acesso"],
	)
	if not rows:
		return

	niveis_alvo = _calcular_niveis(board_row, [r["user"] for r in rows])

	for row in rows:
		user = (row.get("user") or "").strip()
		atual = (row.get("nivel_acesso") or "").strip()
		alvo = niveis_alvo.get(user, "Visualizar")
		if atual == alvo:
			continue
		frappe.db.set_value("Board User", row["name"], "nivel_acesso", alvo)


def _calcular_niveis(board_row: dict, users: list[str]) -> dict[str, str]:
	niveis: dict[str, str] = {}
	owner = (board_row.get("owner") or "").strip()
	for user in users:
		niveis[user] = "Visualizar"

	if owner in niveis:
		niveis[owner] = "Gerenciar"

	ref_dt = (board_row.get("referencia_doctype") or "").strip()
	ref_nome = (board_row.get("referencia_nome") or "").strip()

	if ref_dt == "Projeto" and ref_nome and frappe.db.exists("Projeto", ref_nome):
		envolvidos = frappe.get_all(
			"Envolvido no Projeto",
			filters={"parent": ref_nome, "parenttype": "Projeto"},
			fields=["user", "email", "coordenador"],
		)
		for env in envolvidos:
			user_email = (env.get("user") or "").strip()
			if not user_email:
				email = (env.get("email") or "").strip()
				if email and email in niveis:
					user_email = email
			if not user_email or user_email not in niveis:
				continue
			alvo = "Gerenciar" if env.get("coordenador") else "Editar"
			if PESO.get(alvo, 0) > PESO.get(niveis[user_email], 0):
				niveis[user_email] = alvo

		coord = frappe.db.get_value("Projeto", ref_nome, "coordenador")
		if coord:
			email = frappe.db.get_value("Associado", coord, "email")
			if email and email in niveis:
				niveis[email] = "Gerenciar"

	return niveis
