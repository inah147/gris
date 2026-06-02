from __future__ import annotations

import frappe
from frappe import _

from gris.api.gestao_de_tarefas.minhas_tarefas import _ensure_board_pessoal
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def _listar_usuarios_elegiveis() -> list[dict]:
	"""Lista usuarios candidatos para participar de quadros (Users habilitados,
	tipo System User, exceto admin/guest)."""
	rows = frappe.get_all(
		"User",
		filters=[
			["enabled", "=", 1],
			["user_type", "=", "System User"],
			["name", "not in", ["Administrator", "Guest"]],
		],
		fields=["name", "full_name", "email"],
		order_by="full_name asc",
		limit_page_length=0,
	)
	return [
		{
			"value": row["name"],
			"label": row.get("full_name") or row["name"],
			"email": row.get("email") or row["name"],
		}
		for row in rows
	]


def get_context(context):
	request_path = (getattr(frappe.local, "request", None) and frappe.local.request.path) or ""
	if request_path.endswith((".css", ".js")):
		return context

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/gestao_tarefas/tarefas"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/gestao_tarefas"

	board_param = (frappe.form_dict.get("board") or "").strip()
	if board_param:
		if not frappe.db.exists("Board", board_param):
			frappe.local.flags.redirect_location = "/gestao_tarefas"
			raise frappe.Redirect
		if not frappe.has_permission("Board", doc=board_param, ptype="read"):
			frappe.throw(_("Sem permissao para acessar este quadro."), frappe.PermissionError)
		board_meta = frappe.db.get_value(
			"Board",
			board_param,
			["titulo", "referencia_doctype", "referencia_nome"],
			as_dict=True,
		) or {}
		ref_dt = (board_meta.get("referencia_doctype") or "").strip()
		ref_nome = (board_meta.get("referencia_nome") or "").strip()
		if ref_dt == "Projeto" and ref_nome:
			titulo = frappe.db.get_value("Projeto", ref_nome, "nome_do_projeto") or ref_nome
		elif ref_dt == "Festa" and ref_nome:
			titulo = frappe.db.get_value("Festa", ref_nome, "nome_festa") or ref_nome
		else:
			titulo = board_meta.get("titulo") or board_param
		context.user_board_name = board_param
		context.kanban_modo = "projeto"
		context.kanban_titulo = titulo
		context.page_title = titulo
		context.page_subtitle = "Tarefas deste quadro."
		context.is_quadro_solto = not ref_dt
		nivel_atual = frappe.db.get_value(
			"Board User",
			{"parent": board_param, "parenttype": "Board", "user": frappe.session.user},
			"nivel_acesso",
		) or ""
		is_sm = "System Manager" in frappe.get_roles(frappe.session.user)
		context.board_nivel_atual = nivel_atual or ("Gerenciar" if is_sm else "")
		context.pode_gerir_membros = (is_sm or nivel_atual == "Gerenciar") and not ref_dt
		context.usuarios_elegiveis = _listar_usuarios_elegiveis() if context.pode_gerir_membros else []
	else:
		try:
			context.user_board_name = _ensure_board_pessoal(frappe.session.user) or ""
		except Exception:
			context.user_board_name = ""
		context.kanban_modo = "pessoal"
		context.kanban_titulo = "Gestao de tarefas"
		context.page_title = "Minhas tarefas"
		context.page_subtitle = "Acompanhe e gerencie tarefas atribuidas a voce em todos os quadros."
		context.is_quadro_solto = False
		context.board_nivel_atual = ""
		context.pode_gerir_membros = False
		context.usuarios_elegiveis = []

	context.current_user = frappe.session.user
	context.current_user_full_name = (
		frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
	)
	enrich_context(context, "/gestao_tarefas")
	return context
