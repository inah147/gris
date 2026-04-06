import frappe

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

STATUS_LABELS = {
	"Rascunho": "Rascunho",
	"Em aprovacao": "Em aprovação",
	"Aprovado": "Aprovado",
	"Em execucao": "Em execução",
	"Concluido": "Concluído",
	"Cancelado": "Cancelado",
}


def _get_responsavel_by_email(user_email: str | None) -> str | None:
	if not user_email:
		return None

	responsavel_name = frappe.db.get_value("Responsavel", {"email": user_email}, "name")
	return str(responsavel_name) if responsavel_name else None


def _get_associado_by_user(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	associado_name = frappe.db.get_value("Associado", {"id_escoteiros": user}, "name")
	return str(associado_name) if associado_name else None


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


def _get_related_project_names(
	associado_name: str | None,
	responsavel_name: str | None,
	user_email: str | None,
) -> set[str]:
	project_names: set[str] = set()

	if associado_name:
		project_names.update(frappe.get_all("Projeto", filters={"coordenador": associado_name}, pluck="name"))
		project_names.update(
			frappe.get_all("Projeto", filters={"padrinho_associado": associado_name}, pluck="name")
		)
		project_names.update(
			frappe.get_all(
				"Equipe de Interesse Projeto",
				filters={"parenttype": "Projeto", "associado": associado_name},
				pluck="parent",
			)
		)
		project_names.update(
			frappe.get_all(
				"Outro Envolvido Projeto",
				filters={"parenttype": "Projeto", "associado": associado_name},
				pluck="parent",
			)
		)

	# Fallback para usuário que não é Associado: vínculo por e-mail
	if not associado_name and responsavel_name:
		project_names.update(
			frappe.get_all("Projeto", filters={"padrinho_responsavel": responsavel_name}, pluck="name")
		)
		project_names.update(
			frappe.get_all(
				"Equipe de Interesse Projeto",
				filters={"parenttype": "Projeto", "responsavel": responsavel_name},
				pluck="parent",
			)
		)

	if not associado_name and user_email:
		project_names.update(
			frappe.get_all(
				"Equipe de Interesse Projeto",
				filters={"parenttype": "Projeto", "email": user_email},
				pluck="parent",
			)
		)
		project_names.update(
			frappe.get_all(
				"Outro Envolvido Projeto",
				filters={"parenttype": "Projeto", "email": user_email},
				pluck="parent",
			)
		)

	return project_names


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/projetos/meus_projetos"
		raise frappe.Redirect

	if not user_has_access("/projetos/meus_projetos"):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/projetos/meus_projetos"
	enrich_context(context, "/projetos/meus_projetos")

	associado_name = _get_associado_by_user(frappe.session.user)
	user_email = frappe.session.user
	responsavel_name = _get_responsavel_by_email(user_email) if not associado_name else None
	project_names = _get_related_project_names(associado_name, responsavel_name, user_email)

	if not project_names:
		context.meus_projetos = []
		return context

	projects = frappe.get_all(
		"Projeto",
		filters={"name": ["in", list(project_names)]},
		fields=["name", "nome_do_projeto", "coordenador", "status"],
		order_by="modified desc",
	)

	coordinator_names = _resolve_coordinators_names(projects)
	context.meus_projetos = [
		{
			"name": project.get("name"),
			"titulo": project.get("nome_do_projeto") or project.get("name"),
			"coordenador": coordinator_names.get(project.get("coordenador"))
			or project.get("coordenador")
			or "Não informado",
			"status_label": STATUS_LABELS.get(project.get("status"), project.get("status") or "Sem status"),
		}
		for project in projects
	]
	return context
