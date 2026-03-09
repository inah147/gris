from __future__ import annotations

from datetime import date

import frappe
from frappe import _
from frappe.utils import add_years, getdate

from gris.gestão_de_adultos.doctype.entrevista_por_competencias.entrevista_por_competencias import (
	MAPEAMENTO_DTYPE,
	QUESTION_FIELDS,
	SCORE_FIELDS,
	get_options_by_fieldname,
	get_question_by_fieldname,
)

INTERVIEW_DTYPE = "Entrevista por Competencias"
GESTOR_ROLE = "Gestor de Adultos"

QUESTION_SECTIONS = [
	{
		"id": "competencias_essenciais",
		"label": "Competências Essenciais",
		"fields": ["q_ce_1", "q_ce_2", "q_ce_3", "q_ce_4", "q_ce_5"],
	},
	{
		"id": "dirigente_institucional",
		"label": "Dirigente Institucional",
		"fields": ["q_di_1", "q_di_2", "q_di_3", "q_di_4", "q_di_5", "q_di_6", "q_di_7", "q_di_8"],
	},
	{
		"id": "escotista",
		"label": "Escotista",
		"fields": [
			"q_es_1",
			"q_es_2",
			"q_es_3",
			"q_es_4",
			"q_es_5",
			"q_es_6",
			"q_es_7",
			"q_es_8",
			"q_es_9",
			"q_es_10",
			"q_es_11",
		],
	},
]

MOTIVOS_ENTREVISTA = ["Ingresso", "Retorno", "Permanência", "Alteração de função"]


def _normalize_text(value: str | None) -> str:
	if not value:
		return ""
	return " ".join(str(value).strip().lower().split())


def _build_alert_categories_lookup(alert_rows: list[dict]) -> dict[tuple[str, str], list[str]]:
	if not alert_rows:
		return {}

	questions_by_fieldname = get_question_by_fieldname()
	competencias_essenciais_fields = next(
		(section["fields"] for section in QUESTION_SECTIONS if section["id"] == "competencias_essenciais"),
		[],
	)
	general_questions = {
		_normalize_text(questions_by_fieldname.get(fieldname))
		for fieldname in competencias_essenciais_fields
		if questions_by_fieldname.get(fieldname)
	}

	answers = sorted(
		{(row.get("resposta") or "").strip() for row in alert_rows if (row.get("resposta") or "").strip()}
	)
	if not answers:
		return {}

	mappings = frappe.get_all(
		MAPEAMENTO_DTYPE,
		filters={"resposta": ["in", answers]},
		fields=["pergunta", "resposta", *SCORE_FIELDS],
		limit_page_length=0,
	)

	lookup: dict[tuple[str, str], list[str]] = {}
	for mapping in mappings:
		question_key = _normalize_text(mapping.get("pergunta"))
		answer_key = _normalize_text(mapping.get("resposta"))
		if not question_key or not answer_key:
			continue

		key = (question_key, answer_key)
		current_categories = set(lookup.get(key, []))
		for fieldname in SCORE_FIELDS:
			if int(mapping.get(fieldname) or 0) != 0:
				current_categories.add(fieldname)
		lookup[key] = [fieldname for fieldname in SCORE_FIELDS if fieldname in current_categories]

	for row in alert_rows:
		question_key = _normalize_text(row.get("pergunta"))
		answer_key = _normalize_text(row.get("resposta"))
		if not question_key or not answer_key:
			continue

		if question_key in general_questions:
			key = (question_key, answer_key)
			categories = lookup.get(key, [])
			if "alerta_geral" not in categories:
				lookup[key] = ["alerta_geral", *categories]

	return lookup


def _require_authenticated_user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Usuário não autenticado."), frappe.PermissionError)


def _require_gestor_adultos():
	_require_authenticated_user()
	roles = frappe.get_roles(frappe.session.user)
	if GESTOR_ROLE not in roles and "System Manager" not in roles:
		frappe.throw(_("Você não tem permissão para acessar Gestão de Adultos."), frappe.PermissionError)


def _get_associado_do_usuario(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	return frappe.db.get_value("Associado", {"id_escoteiros": user}, "name")


def _is_adulto(data_nascimento) -> bool:
	if not data_nascimento:
		return False
	return add_years(getdate(data_nascimento), 18) <= date.today()


def _build_form_config():
	options_by_field = get_options_by_fieldname()
	questions_by_field = get_question_by_fieldname()
	alert_rules = frappe.get_all(
		MAPEAMENTO_DTYPE,
		filters={"alerta": 1},
		fields=["pergunta", "resposta", "motivo_do_alerta"],
		limit_page_length=0,
	)

	sections = []
	for section in QUESTION_SECTIONS:
		section_fields = []
		for fieldname in section["fields"]:
			section_fields.append(
				{
					"fieldname": fieldname,
					"label": questions_by_field.get(fieldname),
					"options": options_by_field.get(fieldname, []),
					"observation_fieldname": f"obs_{fieldname}",
				}
			)
		sections.append({"id": section["id"], "label": section["label"], "fields": section_fields})

	return {
		"motivos_entrevista": MOTIVOS_ENTREVISTA,
		"sections": sections,
		"alert_rules": [
			{
				"pergunta": row.get("pergunta"),
				"resposta": row.get("resposta"),
				"motivo_do_alerta": row.get("motivo_do_alerta"),
			}
			for row in alert_rules
		],
		"score_fields": [
			"pontuacao_dirigente_administrativo_financeiro",
			"pontuacao_dirigente_gestao_institucional",
			"pontuacao_dirigente_metodos_educativos",
			"pontuacao_ramo_lobinho",
			"pontuacao_ramo_escoteiro",
			"pontuacao_ramo_senior",
			"pontuacao_ramo_pioneiro",
		],
	}


def _serialize_entrevista(doc):
	question_fields = [item["fieldname"] for item in QUESTION_FIELDS]
	obs_fields = [f"obs_{field}" for field in question_fields]
	base_fields = [
		"name",
		"associado",
		"funcao_atual",
		"profissao",
		"formacao",
		"hobbies_e_interesses",
		"motivo_da_entrevista",
		"pontuacao_dirigente_administrativo_financeiro",
		"pontuacao_dirigente_gestao_institucional",
		"pontuacao_dirigente_metodos_educativos",
		"pontuacao_ramo_lobinho",
		"pontuacao_ramo_escoteiro",
		"pontuacao_ramo_senior",
		"pontuacao_ramo_pioneiro",
		"resumo",
		"data_da_ultima_atualizacao",
		"observacoes",
	]
	data = {field: doc.get(field) for field in base_fields + question_fields + obs_fields}
	data["associado_nome"] = (
		frappe.db.get_value("Associado", doc.get("associado"), "nome_completo")
		if doc.get("associado")
		else ""
	)
	alert_rows = [
		{
			"pergunta": row.pergunta,
			"resposta": row.resposta,
			"motivo_do_alerta": row.motivo_do_alerta,
		}
		for row in doc.get("alertas")
	]
	alert_categories_lookup = _build_alert_categories_lookup(alert_rows)
	data["alertas"] = [
		{
			"pergunta": row.pergunta,
			"resposta": row.resposta,
			"motivo_do_alerta": row.motivo_do_alerta,
			"categorias": alert_categories_lookup.get(
				(_normalize_text(row.pergunta), _normalize_text(row.resposta)),
				[],
			),
		}
		for row in doc.get("alertas")
	]
	return data


def _find_or_create_entrevista(associado: str):
	existing = frappe.db.get_value(INTERVIEW_DTYPE, {"associado": associado}, "name")
	if existing:
		return frappe.get_doc(INTERVIEW_DTYPE, existing), False

	doc = frappe.get_doc({"doctype": INTERVIEW_DTYPE, "associado": associado})
	doc.insert(ignore_permissions=True)
	return doc, True


def _sanitize_payload(payload: dict) -> dict:
	allowed_fields = {
		"funcao_atual",
		"profissao",
		"formacao",
		"hobbies_e_interesses",
		"motivo_da_entrevista",
		"observacoes",
		*[item["fieldname"] for item in QUESTION_FIELDS],
		*[f"obs_{item['fieldname']}" for item in QUESTION_FIELDS],
	}
	return {key: value for key, value in payload.items() if key in allowed_fields}


def _assert_owner_access_to_interview(doc):
	user_associado = _get_associado_do_usuario()
	if not user_associado or doc.associado != user_associado:
		frappe.throw(_("Você só pode acessar sua própria entrevista."), frappe.PermissionError)


@frappe.whitelist()
def get_opcoes_respostas_por_pergunta():
	_require_gestor_adultos()
	return get_options_by_fieldname()


@frappe.whitelist()
def listar_entrevistas(associado: str | None = None):
	_require_gestor_adultos()
	filters = {"associado": associado} if associado else {}
	rows = frappe.get_all(
		INTERVIEW_DTYPE,
		filters=filters,
		fields=["name", "associado", "data_da_ultima_atualizacao", "modified"],
		order_by="modified desc",
	)
	for row in rows:
		row["associado_nome"] = frappe.db.get_value("Associado", row["associado"], "nome_completo")
	return rows


@frappe.whitelist()
def listar_associados_adultos(search: str | None = None):
	_require_gestor_adultos()
	rows = frappe.get_all(
		"Associado",
		fields=["name", "nome_completo", "data_de_nascimento"],
		filters={"data_de_nascimento": ["is", "set"]},
		order_by="nome_completo asc",
		limit_page_length=0,
	)
	query = (search or "").strip().lower()
	result = []
	for row in rows:
		if not _is_adulto(row.get("data_de_nascimento")):
			continue
		nome = (row.get("nome_completo") or "").lower()
		if query and query not in nome and query not in row.get("name", "").lower():
			continue
		result.append(row)
	return result


@frappe.whitelist()
def obter_ou_criar_entrevista(associado: str):
	_require_gestor_adultos()
	if not associado:
		frappe.throw(_("Associado é obrigatório."))
	doc, created = _find_or_create_entrevista(associado)
	return {"name": doc.name, "created": created}


@frappe.whitelist()
def obter_formulario_entrevista(name: str):
	_require_gestor_adultos()
	if not name:
		frappe.throw(_("Informe o nome da entrevista."))
	doc = frappe.get_doc(INTERVIEW_DTYPE, name)
	return {"config": _build_form_config(), "entrevista": _serialize_entrevista(doc)}


@frappe.whitelist()
def salvar_entrevista(name: str, payload: str):
	_require_gestor_adultos()
	if not name:
		frappe.throw(_("Informe o nome da entrevista."))
	doc = frappe.get_doc(INTERVIEW_DTYPE, name)
	data = frappe.parse_json(payload) if isinstance(payload, str) else payload
	for fieldname, value in _sanitize_payload(data).items():
		doc.set(fieldname, value)
	doc.save(ignore_permissions=True)
	return {"name": doc.name}


@frappe.whitelist()
def obter_ou_criar_minha_entrevista():
	_require_authenticated_user()
	associado = _get_associado_do_usuario()
	if not associado:
		frappe.throw(_("Seu usuário não está vinculado a um associado."), frappe.PermissionError)
	doc, created = _find_or_create_entrevista(associado)
	return {"name": doc.name, "created": created}


@frappe.whitelist()
def obter_minha_entrevista(name: str):
	_require_authenticated_user()
	if not name:
		frappe.throw(_("Informe o nome da entrevista."))
	doc = frappe.get_doc(INTERVIEW_DTYPE, name)
	_assert_owner_access_to_interview(doc)
	return {"config": _build_form_config(), "entrevista": _serialize_entrevista(doc)}


@frappe.whitelist()
def salvar_minha_entrevista(name: str, payload: str):
	_require_authenticated_user()
	if not name:
		frappe.throw(_("Informe o nome da entrevista."))
	doc = frappe.get_doc(INTERVIEW_DTYPE, name)
	_assert_owner_access_to_interview(doc)
	data = frappe.parse_json(payload) if isinstance(payload, str) else payload
	for fieldname, value in _sanitize_payload(data).items():
		doc.set(fieldname, value)
	doc.save(ignore_permissions=True)
	return {"name": doc.name}
