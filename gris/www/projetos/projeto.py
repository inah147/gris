from urllib.parse import quote

import frappe

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

STATUS_EM_EXECUCAO = "Em execucao"
STATUS_CONCLUIDO = "Concluido"
STATUS_CANCELADO = "Cancelado"
STATUS_READ_ONLY = {STATUS_CONCLUIDO, STATUS_CANCELADO}
STATUS_ALLOWED_ON_PROJECT_PAGE = {STATUS_EM_EXECUCAO, *STATUS_READ_ONLY}


def _redirect_by_status(status: str, projeto_name: str) -> None:
	encoded_name = quote(projeto_name)
	if status == "Rascunho":
		frappe.local.flags.redirect_location = f"/projetos/cadastrar_novo_projeto?projeto={encoded_name}"
		raise frappe.Redirect
	if status == "Em aprovacao":
		frappe.local.flags.redirect_location = f"/projetos/aprovacao_projeto?projeto={encoded_name}"
		raise frappe.Redirect
	if status == "Aprovado":
		frappe.local.flags.redirect_location = f"/projetos/projeto_aprovado?projeto={encoded_name}"
		raise frappe.Redirect
	frappe.local.flags.redirect_location = "/projetos/visao_geral"
	raise frappe.Redirect


def get_context(context):
	# Requisições de assets (CSS/JS) não têm parâmetro de projeto — retorna contexto vazio.
	request_path = (getattr(frappe.local, "request", None) and frappe.local.request.path) or ""
	if request_path.endswith((".css", ".js")):
		return context

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/projetos/projeto"
		raise frappe.Redirect

	if not user_has_access("/projetos/projeto"):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	projeto_name = (frappe.form_dict.get("projeto") or "").strip()
	if not projeto_name:
		frappe.throw("Projeto não informado.")

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("read"):
		frappe.throw("Você não tem permissão para visualizar este projeto.", frappe.PermissionError)

	status = doc.get("status")
	if status not in STATUS_ALLOWED_ON_PROJECT_PAGE:
		_redirect_by_status(status, projeto_name)

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/projetos/visao_geral"
	context.projeto_name = projeto_name
	context.projeto_titulo = (doc.get("nome_do_projeto") or "").strip() or projeto_name
	context.projeto_status = status or ""
	context.projeto_read_only = status in STATUS_READ_ONLY
	enrich_context(context, "/projetos/projeto")
	return context
