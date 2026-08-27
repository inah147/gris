"""APIs para a pagina /gestao_tarefas (indice de quadros) e /gestao_tarefas/tarefas?board=...

Lida com listagem de quadros nao-pessoais visiveis ao usuario, criacao de
quadros "soltos" e gestao de tarefas dentro de um quadro especifico.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from gris.api.gestao_de_tarefas.minhas_tarefas import (
	TASK_CLIENT_FIELDS,
	_assert_payload,
	_clean_value,
	_enrich_tarefas_com_board,
	_normalize_dates,
	_parse_payload,
	_require_logged_user,
)


def _badge_for(board: dict[str, Any]) -> tuple[str, str, str]:
	ref_dt = (board.get("referencia_doctype") or "").strip()
	if ref_dt == "Projeto":
		return ("projeto", "Projeto", "default")
	if ref_dt == "Festa":
		return ("festa", "Festa", "secondary")
	return ("solto", "", "outline")


def _resolve_titulo(
	board: dict[str, Any], projeto_titulos: dict[str, str], festa_titulos: dict[str, str]
) -> str:
	ref_dt = (board.get("referencia_doctype") or "").strip()
	ref_nome = (board.get("referencia_nome") or "").strip()
	if ref_dt == "Projeto" and ref_nome:
		return projeto_titulos.get(ref_nome) or ref_nome
	if ref_dt == "Festa" and ref_nome:
		return festa_titulos.get(ref_nome) or ref_nome
	return board.get("titulo") or board.get("name") or ""


def listar_quadros_publicos() -> list[dict[str, Any]]:
	"""Lista quadros nao-pessoais visiveis ao usuario.

	Respeita `permission_query_conditions` registrado para Board, entao o
	resultado ja vem filtrado pelos quadros em que o usuario consta em
	`usuarios_autorizados` (ou pessoais proprios, que serao removidos abaixo).
	"""
	rows = frappe.get_list(
		"Board",
		filters={"ativo": 1},
		fields=["name", "titulo", "referencia_doctype", "referencia_nome", "owner", "modified"],
		order_by="modified desc",
		limit_page_length=0,
	)
	rows = [row for row in rows if (row.get("referencia_doctype") or "").strip() != "User"]

	projeto_names = {
		row.get("referencia_nome")
		for row in rows
		if (row.get("referencia_doctype") or "").strip() == "Projeto" and row.get("referencia_nome")
	}
	projeto_titulos: dict[str, str] = {}
	if projeto_names:
		projeto_rows = frappe.get_all(
			"Projeto",
			filters={"name": ["in", list(projeto_names)]},
			fields=["name", "nome_do_projeto"],
			limit_page_length=0,
		)
		projeto_titulos = {p["name"]: (p.get("nome_do_projeto") or p["name"]) for p in projeto_rows}

	festa_names = {
		row.get("referencia_nome")
		for row in rows
		if (row.get("referencia_doctype") or "").strip() == "Festa" and row.get("referencia_nome")
	}
	festa_titulos: dict[str, str] = {}
	if festa_names:
		festa_rows = frappe.get_all(
			"Festa",
			filters={"name": ["in", list(festa_names)]},
			fields=["name", "nome_festa"],
			limit_page_length=0,
		)
		festa_titulos = {f["name"]: (f.get("nome_festa") or f["name"]) for f in festa_rows}

	resultado: list[dict[str, Any]] = []
	for row in rows:
		badge_tipo, badge_label, badge_variant = _badge_for(row)
		resultado.append(
			{
				"name": row.get("name"),
				"titulo": _resolve_titulo(row, projeto_titulos, festa_titulos),
				"badge_tipo": badge_tipo,
				"badge_label": badge_label,
				"badge_variant": badge_variant,
				"detail_url": f"/gestao_tarefas/tarefas?board={row.get('name')}",
			}
		)
	return resultado


@frappe.whitelist()
def criar_quadro(titulo: str) -> dict[str, Any]:
	_require_logged_user()
	titulo = (titulo or "").strip()
	if not titulo:
		frappe.throw(_("Informe o titulo do quadro."))
	if len(titulo) > 140:
		frappe.throw(_("Titulo do quadro muito longo (max 140 caracteres)."))

	board = frappe.get_doc(
		{
			"doctype": "Board",
			"titulo": titulo,
			"ativo": 1,
		}
	).insert(ignore_permissions=True)

	return {"ok": True, "name": board.name, "titulo": board.titulo}


def _assert_board_acessivel(board_name: str) -> str:
	board_name = (board_name or "").strip()
	if not board_name:
		frappe.throw(_("Quadro nao informado."))
	if not frappe.db.exists("Board", board_name):
		frappe.throw(_("Quadro nao encontrado."))
	if not frappe.has_permission("Board", doc=board_name, ptype="read"):
		frappe.throw(_("Sem permissao para acessar este quadro."), frappe.PermissionError)
	return board_name


def _nivel_do_usuario(board_name: str, user: str) -> str:
	"""Retorna o nivel de acesso do usuario no board, ou '' se nao for membro."""
	row = frappe.db.get_value(
		"Board User",
		{"parent": board_name, "parenttype": "Board", "user": user},
		"nivel_acesso",
	)
	return (row or "").strip()


def _assert_pode_gerenciar(board_name: str) -> tuple[str, str]:
	user = _require_logged_user()
	board_name = _assert_board_acessivel(board_name)
	if "System Manager" in frappe.get_roles(user):
		return user, board_name
	if _nivel_do_usuario(board_name, user) != "Gerenciar":
		frappe.throw(
			_("Apenas membros com nivel Gerenciar podem gerir participantes."),
			frappe.PermissionError,
		)
	return user, board_name


def _assert_board_solto(board_name: str) -> None:
	ref_dt = (frappe.db.get_value("Board", board_name, "referencia_doctype") or "").strip()
	if ref_dt:
		frappe.throw(
			_("Apenas quadros soltos permitem gerir participantes manualmente."),
		)


def _listar_tarefas_do_quadro(board_name: str) -> list[dict[str, Any]]:
	rows = frappe.get_all(
		"Gestao de Tarefas",
		filters={"board": board_name},
		fields=["name", "board", *TASK_CLIENT_FIELDS],
		order_by="prazo asc, creation asc",
		limit_page_length=0,
		ignore_permissions=True,
	)
	return _enrich_tarefas_com_board(rows)


@frappe.whitelist()
def bootstrap_quadro(board_name: str) -> dict[str, Any]:
	user = _require_logged_user()
	board_name = _assert_board_acessivel(board_name)
	board = frappe.db.get_value(
		"Board",
		board_name,
		["name", "titulo", "referencia_doctype", "referencia_nome"],
		as_dict=True,
	)
	return {
		"ok": True,
		"user": user,
		"user_full_name": frappe.db.get_value("User", user, "full_name") or user,
		"user_board_name": board_name,
		"board": board,
		"tarefas": _listar_tarefas_do_quadro(board_name),
		"responsavel_options": _responsavel_options_do_quadro(board_name),
	}


def _responsavel_options_do_quadro(board_name: str) -> list[dict[str, Any]]:
	"""Usuarios autorizados do board (equipe da festa) como opcoes de responsavel
	para o combobox de tarefas: {user, full_name}."""
	return [
		{"user": membro["user"], "full_name": membro["full_name"]}
		for membro in _serializar_membros(board_name)
		if membro.get("user")
	]


@frappe.whitelist()
def salvar_tarefa_quadro(tarefa: str | dict[str, Any]) -> dict[str, Any]:
	_require_logged_user()
	payload = _parse_payload(tarefa)
	board_name = _assert_board_acessivel((payload.get("board") or "").strip())

	tarefa_name = (payload.get("name") or "").strip()
	existing = None
	previous_status = ""
	if tarefa_name:
		if not frappe.db.exists("Gestao de Tarefas", tarefa_name):
			frappe.throw(_("Tarefa nao encontrada."))
		existing = frappe.get_doc("Gestao de Tarefas", tarefa_name)
		if (existing.board or "") != board_name:
			frappe.throw(_("Tarefa nao pertence a este quadro."))
		previous_status = (existing.status or "").strip()

	if existing:
		clean = {field: _clean_value(payload.get(field, existing.get(field))) for field in TASK_CLIENT_FIELDS}
	else:
		clean = {field: _clean_value(payload.get(field)) for field in TASK_CLIENT_FIELDS}

	clean = _normalize_dates(clean, previous_status=previous_status)
	_assert_payload(clean)

	if existing:
		for field in TASK_CLIENT_FIELDS:
			existing.set(field, clean.get(field))
		existing.flags.ignore_version = True
		existing.save(ignore_permissions=True)
	else:
		frappe.get_doc(
			{
				"doctype": "Gestao de Tarefas",
				"board": board_name,
				**{field: clean.get(field) for field in TASK_CLIENT_FIELDS},
			}
		).insert(ignore_permissions=True)

	return {
		"ok": True,
		"tarefas": _listar_tarefas_do_quadro(board_name),
	}


@frappe.whitelist()
def atualizar_status_quadro(tarefa_name: str, status: str) -> dict[str, Any]:
	from frappe.utils import nowdate

	from gris.gris.doctype.gestao_de_tarefas.gestao_de_tarefas import TASK_STATUS_OPTIONS

	_require_logged_user()
	status = (status or "").strip()
	if status not in TASK_STATUS_OPTIONS:
		frappe.throw(_("Status da tarefa invalido."))
	if not tarefa_name:
		frappe.throw(_("Tarefa nao informada."))

	current = frappe.db.get_value(
		"Gestao de Tarefas",
		tarefa_name,
		["board", "status", "data_inicio"],
		as_dict=True,
	)
	if not current:
		frappe.throw(_("Tarefa nao encontrada."))
	board_name = _assert_board_acessivel(current.get("board") or "")

	previous_status = (current.get("status") or "").strip()
	updates: dict[str, Any] = {"status": status}
	if status != "Nao iniciado" and previous_status == "Nao iniciado" and not current.get("data_inicio"):
		updates["data_inicio"] = nowdate()
	updates["data_entrega"] = nowdate() if status == "Concluido" else None

	frappe.db.set_value("Gestao de Tarefas", tarefa_name, updates)
	return {
		"ok": True,
		"tarefas": _listar_tarefas_do_quadro(board_name),
	}


NIVEIS_ACESSO = ("Gerenciar", "Editar", "Visualizar")


def _serializar_membros(board_name: str) -> list[dict[str, Any]]:
	rows = frappe.get_all(
		"Board User",
		filters={"parent": board_name, "parenttype": "Board"},
		fields=["name", "user", "nivel_acesso", "adicionado_em"],
		order_by="adicionado_em asc, idx asc",
		limit_page_length=0,
	)
	if not rows:
		return []

	user_ids = [row["user"] for row in rows if row.get("user")]
	user_info = {}
	if user_ids:
		for u in frappe.get_all(
			"User",
			filters={"name": ["in", user_ids]},
			fields=["name", "full_name", "user_image"],
			limit_page_length=0,
		):
			user_info[u["name"]] = u

	owner = frappe.db.get_value("Board", board_name, "owner")
	resultado = []
	for row in rows:
		info = user_info.get(row.get("user"), {})
		resultado.append(
			{
				"name": row.get("name"),
				"user": row.get("user"),
				"full_name": info.get("full_name") or row.get("user"),
				"user_image": info.get("user_image"),
				"nivel_acesso": row.get("nivel_acesso") or "Visualizar",
				"adicionado_em": row.get("adicionado_em"),
				"is_owner": row.get("user") == owner,
			}
		)
	return resultado


@frappe.whitelist()
def listar_membros(board_name: str) -> dict[str, Any]:
	user = _require_logged_user()
	board_name = _assert_board_acessivel(board_name)
	nivel = _nivel_do_usuario(board_name, user)
	is_sm = "System Manager" in frappe.get_roles(user)
	pode_gerir = is_sm or nivel == "Gerenciar"
	ref_dt = (frappe.db.get_value("Board", board_name, "referencia_doctype") or "").strip()
	return {
		"ok": True,
		"membros": _serializar_membros(board_name),
		"nivel_atual": nivel or ("Gerenciar" if is_sm else ""),
		"pode_gerir": pode_gerir,
		"is_solto": not ref_dt,
		"niveis_disponiveis": list(NIVEIS_ACESSO),
	}


@frappe.whitelist()
def adicionar_membro(board_name: str, user: str, nivel_acesso: str = "Editar") -> dict[str, Any]:
	_, board_name = _assert_pode_gerenciar(board_name)
	_assert_board_solto(board_name)
	user = (user or "").strip()
	nivel_acesso = (nivel_acesso or "").strip()
	if not user:
		frappe.throw(_("Usuario nao informado."))
	if not frappe.db.exists("User", user):
		frappe.throw(_("Usuario nao encontrado."))
	if nivel_acesso not in NIVEIS_ACESSO:
		frappe.throw(_("Nivel de acesso invalido."))

	existente = frappe.db.exists(
		"Board User",
		{"parent": board_name, "parenttype": "Board", "user": user},
	)
	if existente:
		frappe.throw(_("Este usuario ja participa do quadro."))

	board = frappe.get_doc("Board", board_name)
	board.append(
		"usuarios_autorizados",
		{"user": user, "nivel_acesso": nivel_acesso, "adicionado_em": frappe.utils.nowdate()},
	)
	board.flags.ignore_version = True
	board.save(ignore_permissions=True)
	return {"ok": True, "membros": _serializar_membros(board_name)}


@frappe.whitelist()
def atualizar_nivel_membro(board_name: str, user: str, nivel_acesso: str) -> dict[str, Any]:
	_, board_name = _assert_pode_gerenciar(board_name)
	_assert_board_solto(board_name)
	user = (user or "").strip()
	nivel_acesso = (nivel_acesso or "").strip()
	if not user:
		frappe.throw(_("Usuario nao informado."))
	if nivel_acesso not in NIVEIS_ACESSO:
		frappe.throw(_("Nivel de acesso invalido."))

	owner = frappe.db.get_value("Board", board_name, "owner")
	if user == owner and nivel_acesso != "Gerenciar":
		frappe.throw(_("O criador do quadro precisa manter nivel Gerenciar."))

	row_name = frappe.db.get_value(
		"Board User",
		{"parent": board_name, "parenttype": "Board", "user": user},
		"name",
	)
	if not row_name:
		frappe.throw(_("Usuario nao participa do quadro."))

	frappe.db.set_value("Board User", row_name, "nivel_acesso", nivel_acesso)
	return {"ok": True, "membros": _serializar_membros(board_name)}


@frappe.whitelist()
def remover_membro(board_name: str, user: str) -> dict[str, Any]:
	_, board_name = _assert_pode_gerenciar(board_name)
	_assert_board_solto(board_name)
	user = (user or "").strip()
	if not user:
		frappe.throw(_("Usuario nao informado."))

	owner = frappe.db.get_value("Board", board_name, "owner")
	if user == owner:
		frappe.throw(_("Nao e possivel remover o criador do quadro."))

	board = frappe.get_doc("Board", board_name)
	novas_linhas = [row for row in (board.usuarios_autorizados or []) if (row.user or "") != user]
	if len(novas_linhas) == len(board.usuarios_autorizados or []):
		frappe.throw(_("Usuario nao participa do quadro."))

	board.set("usuarios_autorizados", novas_linhas)
	board.flags.ignore_version = True
	board.save(ignore_permissions=True)
	return {"ok": True, "membros": _serializar_membros(board_name)}


@frappe.whitelist()
def buscar_usuarios(board_name: str, query: str = "") -> dict[str, Any]:
	"""Autocomplete de Users (excluindo quem ja participa do board)."""
	_require_logged_user()
	board_name = _assert_board_acessivel(board_name)
	query = (query or "").strip()

	ja_membros = frappe.get_all(
		"Board User",
		filters={"parent": board_name, "parenttype": "Board"},
		pluck="user",
		limit_page_length=0,
	)

	filters = [
		["enabled", "=", 1],
		["user_type", "=", "System User"],
		["name", "not in", [*ja_membros, "Administrator", "Guest"]],
	]
	or_filters = None
	if query:
		like = f"%{query}%"
		or_filters = [
			["name", "like", like],
			["full_name", "like", like],
			["email", "like", like],
		]

	rows = frappe.get_all(
		"User",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "full_name", "user_image", "email"],
		order_by="full_name asc",
		limit_page_length=10,
	)
	return {"ok": True, "usuarios": rows}
