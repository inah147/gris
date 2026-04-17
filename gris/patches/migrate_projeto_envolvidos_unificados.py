from __future__ import annotations

import frappe

LEGACY_TEAM_DTYPE = "Equipe de Interesse Projeto"
LEGACY_APPROVER_DTYPE = "Aprovador Projeto"
LEGACY_OTHER_DTYPE = "Outro Envolvido Projeto"


def _get_projeto_module():
	from gris.gestao_de_projetos.doctype.projeto import projeto as projeto_module

	return projeto_module


def execute():
	if not frappe.db.exists("DocType", "Projeto"):
		return

	project_names = frappe.get_all("Projeto", pluck="name", limit_page_length=0)
	if not project_names:
		return

	for project_name in project_names:
		try:
			_migrate_project(project_name)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Falha ao migrar envolvidos unificados do projeto {project_name}",
			)


def _migrate_project(project_name: str) -> None:
	doc = frappe.get_doc("Projeto", project_name)
	if doc.get("envolvidos"):
		return

	envolvidos = _collect_envolvidos_from_legacy_sources(doc)
	if not envolvidos:
		return

	projeto_module = _get_projeto_module()
	projeto_module._set_doc_envolvidos(doc, envolvidos)
	projeto_module._sync_legacy_people_from_envolvidos(doc, envolvidos)

	doc.flags.ignore_validate = True
	doc.flags.portal_draft_save = True
	doc.flags.ignore_version = True
	doc.save(ignore_permissions=True)


def _collect_envolvidos_from_legacy_sources(doc) -> list[dict]:
	projeto_module = _get_projeto_module()
	rows: list[dict] = []

	coordenador = (doc.get("coordenador") or "").strip()
	if coordenador:
		rows.append(
			{
				"tipo_pessoa": projeto_module.APPROVER_TYPE_ASSOCIADO,
				"associado": coordenador,
				"coordenador": 1,
				"participa_avaliacao": 1,
			}
		)

	tipo_padrinho = (doc.get("tipo_padrinho_ou_orientador") or "").strip()
	padrinho_associado = (doc.get("padrinho_associado") or "").strip()
	padrinho_responsavel = (doc.get("padrinho_responsavel") or "").strip()
	if tipo_padrinho == projeto_module.APPROVER_TYPE_ASSOCIADO and padrinho_associado:
		rows.append(
			{
				"tipo_pessoa": projeto_module.APPROVER_TYPE_ASSOCIADO,
				"associado": padrinho_associado,
				"padrinho_orientador": 1,
				"aprovador": 1,
				"origem_regra_aprovador": projeto_module.APPROVER_ORIGIN_PADRINHO,
				"permite_remover": 0,
				"participa_avaliacao": 1,
			}
		)
	elif tipo_padrinho == projeto_module.APPROVER_TYPE_RESPONSAVEL and padrinho_responsavel:
		rows.append(
			{
				"tipo_pessoa": projeto_module.APPROVER_TYPE_RESPONSAVEL,
				"responsavel": padrinho_responsavel,
				"padrinho_orientador": 1,
				"aprovador": 1,
				"origem_regra_aprovador": projeto_module.APPROVER_ORIGIN_PADRINHO,
				"permite_remover": 0,
				"participa_avaliacao": 1,
			}
		)

	rows.extend(_collect_legacy_team_rows(doc.name))
	rows.extend(_collect_legacy_approver_rows(doc.name, projeto_module))
	rows.extend(_collect_legacy_other_rows(doc.name, projeto_module))

	normalized_rows = [
		normalized_row
		for normalized_row in (projeto_module._normalize_envolvido_row(row, strict=False) for row in rows)
		if normalized_row
	]
	return projeto_module._merge_duplicate_envolvidos(normalized_rows)


def _collect_legacy_team_rows(project_name: str) -> list[dict]:
	if not frappe.db.exists("DocType", LEGACY_TEAM_DTYPE):
		return []

	rows = frappe.get_all(
		LEGACY_TEAM_DTYPE,
		filters={"parent": project_name, "parenttype": "Projeto"},
		fields=["tipo_pessoa", "associado", "responsavel", "nome", "email", "telefone", "funcao"],
		limit_page_length=0,
	)

	return [
		{
			"tipo_pessoa": row.get("tipo_pessoa") or "Outro",
			"associado": row.get("associado") or "",
			"responsavel": row.get("responsavel") or "",
			"nome": row.get("nome") or "",
			"email": row.get("email") or "",
			"telefone": row.get("telefone") or "",
			"funcao": row.get("funcao") or "",
			"participa_avaliacao": 1,
		}
		for row in rows
	]


def _collect_legacy_approver_rows(project_name: str, projeto_module) -> list[dict]:
	if not frappe.db.exists("DocType", LEGACY_APPROVER_DTYPE):
		return []

	rows = frappe.get_all(
		LEGACY_APPROVER_DTYPE,
		filters={"parent": project_name, "parenttype": "Projeto"},
		fields=[
			"tipo_pessoa",
			"associado",
			"responsavel",
			"nome",
			"email",
			"telefone",
			"origem_regra",
			"permite_remover",
		],
		limit_page_length=0,
	)

	return [
		{
			"tipo_pessoa": row.get("tipo_pessoa") or projeto_module.APPROVER_TYPE_ASSOCIADO,
			"associado": row.get("associado") or "",
			"responsavel": row.get("responsavel") or "",
			"nome": row.get("nome") or "",
			"email": row.get("email") or "",
			"telefone": row.get("telefone") or "",
			"aprovador": 1,
			"origem_regra_aprovador": row.get("origem_regra") or projeto_module.APPROVER_ORIGIN_MANUAL,
			"permite_remover": row.get("permite_remover"),
			"participa_avaliacao": 1,
		}
		for row in rows
	]


def _collect_legacy_other_rows(project_name: str, projeto_module) -> list[dict]:
	if not frappe.db.exists("DocType", LEGACY_OTHER_DTYPE):
		return []

	rows = frappe.get_all(
		LEGACY_OTHER_DTYPE,
		filters={"parent": project_name, "parenttype": "Projeto"},
		fields=["associado", "email", "telefone"],
		limit_page_length=0,
	)

	return [
		{
			"tipo_pessoa": projeto_module.APPROVER_TYPE_ASSOCIADO,
			"associado": row.get("associado") or "",
			"email": row.get("email") or "",
			"telefone": row.get("telefone") or "",
			"participa_avaliacao": 1,
		}
		for row in rows
	]
