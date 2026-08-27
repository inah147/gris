"""APIs do portal para a pagina /gestao_tarefas e o popover da topbar.

Trata tarefas atribuidas ao usuario logado em qualquer board (pessoal ou de
projeto). Tarefas em board pessoal sao totalmente editaveis aqui; tarefas em
board de Projeto sao read-only nos campos descritivos, mas podem ter status
e comentarios atualizados pelo responsavel.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate, strip_html

from gris.gestao_de_tarefas.user_board import ensure_user_board
from gris.gris.doctype.gestao_de_tarefas.gestao_de_tarefas import (
	TASK_FIELDS,
	TASK_STATUS_OPTIONS,
)

TASK_CLIENT_FIELDS = tuple(f for f in TASK_FIELDS if f != "board")

_TASK_STATUS_FINAL = {"Concluido", "Cancelado"}


def _require_logged_user() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Voce precisa estar autenticado."), frappe.PermissionError)
	return user


def _ensure_board_pessoal(user: str) -> str:
	board_name = frappe.db.get_value(
		"Board",
		{"referencia_doctype": "User", "referencia_nome": user},
		"name",
	)
	if board_name:
		return board_name
	board_name = ensure_user_board(user)
	if not board_name:
		frappe.throw(_("Nao foi possivel localizar o quadro pessoal."))
	return board_name


def _enrich_tarefas_com_board(
	tarefas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
	"""Adiciona board_titulo, board_referencia_doctype, board_referencia_nome
	e projeto_titulo a cada tarefa em uma unica passada (sem N+1).
	"""
	board_ids = {(t.get("board") or "").strip() for t in tarefas if t.get("board")}
	if not board_ids:
		return tarefas

	boards = frappe.get_all(
		"Board",
		filters={"name": ["in", list(board_ids)]},
		fields=["name", "titulo", "referencia_doctype", "referencia_nome"],
		limit_page_length=0,
	)
	boards_by_name = {b["name"]: b for b in boards}

	projeto_names = {
		b.get("referencia_nome")
		for b in boards
		if (b.get("referencia_doctype") or "") == "Projeto" and b.get("referencia_nome")
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

	for tarefa in tarefas:
		board = boards_by_name.get((tarefa.get("board") or "").strip()) or {}
		ref_dt = (board.get("referencia_doctype") or "").strip()
		ref_nome = (board.get("referencia_nome") or "").strip()
		tarefa["board_titulo"] = board.get("titulo") or ""
		tarefa["board_referencia_doctype"] = ref_dt
		tarefa["board_referencia_nome"] = ref_nome
		if ref_dt == "Projeto":
			tarefa["projeto_titulo"] = projeto_titulos.get(ref_nome, "")
			tarefa["board_badge_label"] = projeto_titulos.get(ref_nome, "") or board.get("titulo") or ""
			tarefa["board_badge_tipo"] = "projeto"
		elif ref_dt == "User":
			tarefa["projeto_titulo"] = ""
			tarefa["board_badge_label"] = "Pessoal"
			tarefa["board_badge_tipo"] = "pessoal"
		else:
			tarefa["projeto_titulo"] = ""
			tarefa["board_badge_label"] = board.get("titulo") or ""
			tarefa["board_badge_tipo"] = "outro"
	return tarefas


def _listar_tarefas_do_usuario(
	user: str,
	*,
	apenas_urgentes: bool,
	limite: int | None = None,
) -> list[dict[str, Any]]:
	filters: dict[str, Any] = {
		"responsavel": user,
	}

	rows = frappe.get_all(
		"Gestao de Tarefas",
		filters=filters,
		fields=["name", "board", *TASK_CLIENT_FIELDS],
		order_by="prazo asc, creation asc",
		limit_page_length=limite or 0,
		ignore_permissions=True,
	)

	if apenas_urgentes:
		limite_data = add_days(nowdate(), 7)
		rows = [
			row
			for row in rows
			if row.get("status") not in _TASK_STATUS_FINAL
			and (
				row.get("status") == "Atrasado"
				or (row.get("prazo") and getdate(row.get("prazo")) <= getdate(limite_data))
			)
		]

	rows = _enrich_tarefas_com_board(rows)
	return rows


def count_minhas_tarefas_urgentes(user: str | None = None) -> int:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return 0
	limite_data = add_days(nowdate(), 7)
	rows = frappe.get_all(
		"Gestao de Tarefas",
		filters={
			"responsavel": user,
			"status": ["not in", list(_TASK_STATUS_FINAL)],
		},
		fields=["name", "status", "prazo"],
		limit_page_length=0,
		ignore_permissions=True,
	)
	count = 0
	for row in rows:
		if row.get("status") == "Atrasado":
			count += 1
			continue
		prazo = row.get("prazo")
		if prazo and getdate(prazo) <= getdate(limite_data):
			count += 1
	return count


def context_inject(context) -> None:
	"""Hook em `update_website_context` para popular `context.tarefas_count`."""
	user = frappe.session.user
	if not user or user == "Guest":
		context.tarefas_count = 0
		return
	try:
		context.tarefas_count = count_minhas_tarefas_urgentes(user)
	except Exception:
		context.tarefas_count = 0


@frappe.whitelist()
def list_proximos_7_dias() -> dict[str, Any]:
	user = _require_logged_user()
	tarefas = _listar_tarefas_do_usuario(user, apenas_urgentes=True, limite=100)
	return {
		"ok": True,
		"tarefas": tarefas,
		"hoje": nowdate(),
	}


@frappe.whitelist()
def bootstrap_gestao_tarefas() -> dict[str, Any]:
	user = _require_logged_user()
	user_board_name = _ensure_board_pessoal(user)
	tarefas = _listar_tarefas_do_usuario(user, apenas_urgentes=False)
	return {
		"ok": True,
		"user": user,
		"user_full_name": frappe.db.get_value("User", user, "full_name") or user,
		"user_board_name": user_board_name,
		"tarefas": tarefas,
	}


def _parse_payload(value: Any) -> dict[str, Any]:
	if isinstance(value, dict):
		return value
	if isinstance(value, str):
		import json

		try:
			parsed = json.loads(value)
		except Exception:
			frappe.throw(_("Payload da tarefa invalido."))
		if not isinstance(parsed, dict):
			frappe.throw(_("Payload da tarefa invalido."))
		return parsed
	frappe.throw(_("Payload da tarefa invalido."))
	return {}


def _clean_value(value: Any) -> Any:
	if isinstance(value, str):
		return value.strip()
	return value


def _normalize_dates(payload: dict[str, Any], previous_status: str = "") -> dict[str, Any]:
	status = (payload.get("status") or "").strip()
	data_inicio = payload.get("data_inicio")
	if isinstance(data_inicio, str):
		data_inicio = data_inicio.strip()

	if (
		status not in {"Nao iniciado", ""}
		and not data_inicio
		and (not previous_status or previous_status == "Nao iniciado")
	):
		payload["data_inicio"] = nowdate()
	else:
		payload["data_inicio"] = data_inicio or None

	if status == "Concluido":
		payload["data_entrega"] = payload.get("data_entrega") or nowdate()
	else:
		payload["data_entrega"] = None
	return payload


def _assert_payload(payload: dict[str, Any]) -> None:
	if not (payload.get("descricao") or "").strip():
		frappe.throw(_("Informe o titulo da tarefa."))
	status = (payload.get("status") or "Nao iniciado").strip()
	if status not in TASK_STATUS_OPTIONS:
		frappe.throw(_("Status da tarefa invalido."))
	payload["status"] = status

	data_inicio = payload.get("data_inicio")
	prazo = payload.get("prazo")
	if data_inicio and prazo and getdate(data_inicio) > getdate(prazo):
		frappe.throw(_("Data de inicio nao pode ser maior que o prazo."))


def _get_tarefa_for_user(tarefa_name: str, user: str) -> Any:
	if not tarefa_name:
		frappe.throw(_("Tarefa nao informada."))
	if not frappe.db.exists("Gestao de Tarefas", tarefa_name):
		frappe.throw(_("Tarefa nao encontrada."))
	tarefa = frappe.get_doc("Gestao de Tarefas", tarefa_name)
	if (tarefa.responsavel or "") != user:
		frappe.throw(
			_("Voce so pode alterar tarefas onde voce e responsavel."),
			frappe.PermissionError,
		)
	return tarefa


@frappe.whitelist()
def salvar_tarefa_pessoal(tarefa: str | dict[str, Any]) -> dict[str, Any]:
	user = _require_logged_user()
	user_board = _ensure_board_pessoal(user)
	payload = _parse_payload(tarefa)
	tarefa_name = (payload.get("name") or "").strip()

	existing = None
	previous_status = ""
	if tarefa_name:
		existing = _get_tarefa_for_user(tarefa_name, user)
		previous_status = (existing.status or "").strip()

	if existing:
		clean = {field: _clean_value(payload.get(field, existing.get(field))) for field in TASK_CLIENT_FIELDS}
	else:
		clean = {field: _clean_value(payload.get(field)) for field in TASK_CLIENT_FIELDS}

	clean["responsavel"] = user
	clean = _normalize_dates(clean, previous_status=previous_status)
	_assert_payload(clean)

	if existing:
		for field in TASK_CLIENT_FIELDS:
			existing.set(field, clean.get(field))
		existing.flags.ignore_version = True
		existing.save()
	else:
		frappe.get_doc(
			{
				"doctype": "Gestao de Tarefas",
				"board": user_board,
				**{field: clean.get(field) for field in TASK_CLIENT_FIELDS},
			}
		).insert()

	return {
		"ok": True,
		"tarefas": _listar_tarefas_do_usuario(user, apenas_urgentes=False),
	}


@frappe.whitelist()
def atualizar_status(tarefa_name: str, status: str) -> dict[str, Any]:
	user = _require_logged_user()
	status = (status or "").strip()
	if status not in TASK_STATUS_OPTIONS:
		frappe.throw(_("Status da tarefa invalido."))

	if not tarefa_name:
		frappe.throw(_("Tarefa nao informada."))
	current = frappe.db.get_value(
		"Gestao de Tarefas",
		tarefa_name,
		["responsavel", "status", "data_inicio"],
		as_dict=True,
	)
	if not current:
		frappe.throw(_("Tarefa nao encontrada."))
	if (current.get("responsavel") or "") != user:
		frappe.throw(
			_("Voce so pode alterar tarefas onde voce e responsavel."),
			frappe.PermissionError,
		)

	previous_status = (current.get("status") or "").strip()
	updates: dict[str, Any] = {"status": status}
	if status != "Nao iniciado" and previous_status == "Nao iniciado" and not current.get("data_inicio"):
		updates["data_inicio"] = nowdate()
	updates["data_entrega"] = nowdate() if status == "Concluido" else None

	frappe.db.set_value("Gestao de Tarefas", tarefa_name, updates)

	return {
		"ok": True,
		"tarefas": _listar_tarefas_do_usuario(user, apenas_urgentes=False),
	}


def _can_user_access_tarefa(tarefa, user: str) -> bool:
	if (tarefa.responsavel or "") == user:
		return True
	if not tarefa.board:
		return False
	# Delega ao sistema de permissao de Board (board_has_permission), que cobre
	# uniformemente quadros de Projeto, Festa e soltos via `usuarios_autorizados`.
	return bool(frappe.has_permission("Board", doc=tarefa.board, ptype="read", user=user))


def _serialize_comentarios(tarefa_name: str) -> list[dict[str, Any]]:
	rows = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Gestao de Tarefas",
			"reference_name": tarefa_name,
			"comment_type": "Comment",
		},
		fields=["name", "content", "comment_by", "comment_email", "owner", "creation"],
		order_by="creation asc",
		limit_page_length=200,
	)

	serialized: list[dict[str, Any]] = []
	for row in rows:
		owner_email = (row.get("comment_email") or "").strip()
		owner = (row.get("owner") or owner_email).strip()
		author = (row.get("comment_by") or "").strip()
		if not author and owner_email:
			author = frappe.db.get_value("User", owner_email, "full_name") or owner_email
		serialized.append(
			{
				"name": row.get("name"),
				"content": row.get("content") or "",
				"content_text": strip_html(
					(row.get("content") or "").replace("</p>", "\n").replace("<br>", "\n")
				),
				"author": author or owner_email or _("Usuario"),
				"author_email": owner_email,
				"owner": owner,
				"creation": row.get("creation"),
			}
		)
	return serialized


@frappe.whitelist()
def get_comentarios(tarefa_name: str) -> dict[str, Any]:
	user = _require_logged_user()
	if not frappe.db.exists("Gestao de Tarefas", tarefa_name):
		frappe.throw(_("Tarefa nao encontrada."))
	tarefa = frappe.get_doc("Gestao de Tarefas", tarefa_name)
	if not _can_user_access_tarefa(tarefa, user):
		frappe.throw(
			_("Voce nao tem permissao para visualizar comentarios desta tarefa."),
			frappe.PermissionError,
		)
	return {"ok": True, "comentarios": _serialize_comentarios(tarefa.name)}


@frappe.whitelist()
def adicionar_comentario(tarefa_name: str, texto: str) -> dict[str, Any]:
	user = _require_logged_user()
	texto = (texto or "").strip()
	if not texto:
		frappe.throw(_("Comentario vazio."))
	if not frappe.db.exists("Gestao de Tarefas", tarefa_name):
		frappe.throw(_("Tarefa nao encontrada."))
	tarefa = frappe.get_doc("Gestao de Tarefas", tarefa_name)
	if not _can_user_access_tarefa(tarefa, user):
		frappe.throw(
			_("Voce nao tem permissao para comentar nesta tarefa."),
			frappe.PermissionError,
		)
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "Gestao de Tarefas",
			"reference_name": tarefa.name,
			"content": texto,
			"comment_by": frappe.db.get_value("User", user, "full_name") or user,
			"comment_email": user,
		}
	).insert(ignore_permissions=True)
	return {"ok": True, "comentarios": _serialize_comentarios(tarefa.name)}


@frappe.whitelist()
def editar_comentario(comentario_name: str, texto: str) -> dict[str, Any]:
	user = _require_logged_user()
	texto = (texto or "").strip()
	if not texto:
		frappe.throw(_("Comentario vazio."))
	if not frappe.db.exists("Comment", comentario_name):
		frappe.throw(_("Comentario nao encontrado."))
	comment = frappe.get_doc("Comment", comentario_name)
	if (comment.reference_doctype or "") != "Gestao de Tarefas":
		frappe.throw(_("Comentario invalido."))
	if (comment.owner or comment.comment_email or "").lower() != user.lower():
		frappe.throw(
			_("Somente o autor pode editar este comentario."),
			frappe.PermissionError,
		)
	comment.content = texto
	comment.save(ignore_permissions=True)
	return {
		"ok": True,
		"comentarios": _serialize_comentarios(comment.reference_name),
	}


@frappe.whitelist()
def apagar_comentario(comentario_name: str) -> dict[str, Any]:
	user = _require_logged_user()
	if not frappe.db.exists("Comment", comentario_name):
		frappe.throw(_("Comentario nao encontrado."))
	comment = frappe.get_doc("Comment", comentario_name)
	if (comment.reference_doctype or "") != "Gestao de Tarefas":
		frappe.throw(_("Comentario invalido."))
	if (comment.owner or comment.comment_email or "").lower() != user.lower():
		frappe.throw(
			_("Somente o autor pode apagar este comentario."),
			frappe.PermissionError,
		)
	tarefa_name = comment.reference_name
	frappe.delete_doc("Comment", comentario_name, ignore_permissions=True)
	return {"ok": True, "comentarios": _serialize_comentarios(tarefa_name)}
