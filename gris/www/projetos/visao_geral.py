import frappe
from frappe import _

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

PROJECT_STATUSES = ["Rascunho", "Em aprovacao", "Aprovado", "Em execucao", "Concluido", "Cancelado"]
STATUS_LABELS = {
	"Rascunho": "Rascunho",
	"Em aprovacao": "Em aprovação",
	"Aprovado": "Aprovado",
	"Em execucao": "Em execução",
	"Concluido": "Concluído",
	"Cancelado": "Cancelado",
}


def _resolve_coordinators_names(projects):
	coordinator_ids = {project.get("coordenador") for project in projects if project.get("coordenador")}
	if not coordinator_ids:
		return {}

	coordinators = frappe.get_all(
		"Associado",
		filters={"name": ["in", list(coordinator_ids)]},
		fields=["name", "nome_completo"],
	)
	return {item.get("name"): item.get("nome_completo") for item in coordinators}


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/projetos/visao_geral"
		raise frappe.Redirect

	if not user_has_access("/projetos/visao_geral"):
		frappe.throw(_("Você não tem permissão para acessar esta página."), frappe.PermissionError)

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
	enrich_context(context, "/projetos/visao_geral")

	projects = frappe.get_all(
		"Projeto",
		fields=["name", "nome_do_projeto", "coordenador", "status"],
		order_by="modified desc",
	)

	coordinator_names = _resolve_coordinators_names(projects)
	columns = PROJECT_STATUSES
	kanban_data = {status: [] for status in columns}

	for project in projects:
		status = project.get("status")
		if status not in kanban_data:
			continue
		kanban_data[status].append(
			{
				"name": project.get("name"),
				"titulo": project.get("nome_do_projeto") or project.get("name"),
				"coordenador": coordinator_names.get(project.get("coordenador"))
				or project.get("coordenador")
				or "Não informado",
				"status": status,
				"status_label": STATUS_LABELS.get(status, status),
			}
		)

	context.kanban_columns = columns
	context.kanban_data = kanban_data
	context.status_labels = STATUS_LABELS
	return context
