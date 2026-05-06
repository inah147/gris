from __future__ import annotations

import json
import unicodedata
from typing import Any
from urllib.parse import quote

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_datetime, get_fullname, getdate, now_datetime, nowdate, strip_html

from gris.api.google_workspace.project_drive import is_valid_drive_folder_link
from gris.gestao_de_projetos.doctype.avaliacao_de_projeto.avaliacao_de_projeto import (
	_get_all_reviewer_data,
)
from gris.utils.whatsapp import enviar_mensagem_formatada, enviar_texto


def _is_beneficiario_categoria(categoria: str | None) -> bool:
	return bool((categoria or "").strip().lower().startswith("benefici"))


def _normalize_text(value: str | None) -> str:
	text = (value or "").strip().lower()
	if not text:
		return ""
	decomposed = unicodedata.normalize("NFKD", text)
	return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _is_section_chief_function(value: str | None) -> bool:
	normalized = _normalize_text(value)
	return "chefe" in normalized and "secao" in normalized


class Projeto(Document):
	def validate(self):
		self._validate_dates()
		self._validate_drive_folder_link()
		if getattr(self.flags, "portal_draft_save", False):
			return
		self._hydrate_people_data()
		self._validate_sponsor_category()
		self._validate_people_scopes()

	def after_insert(self):
		_enqueue_project_drive_folder_creation(self.name)

	def _validate_dates(self):
		if self.data_de_inicio and self.data_de_termino:
			if getdate(self.data_de_inicio) > getdate(self.data_de_termino):
				frappe.throw(_("Data de inicio nao pode ser maior que data de termino."))

		for tarefa in self.tarefas or []:
			if tarefa.data_inicio and tarefa.prazo and getdate(tarefa.data_inicio) > getdate(tarefa.prazo):
				frappe.throw(
					_("Tarefa '{0}' com data de inicio maior que prazo.").format(
						tarefa.descricao or tarefa.idx
					)
				)
			if tarefa.status == "Concluido" and not tarefa.data_entrega:
				tarefa.data_entrega = nowdate()

		for item in self.cronograma or []:
			if (
				item.data_inicio
				and item.data_termino
				and getdate(item.data_inicio) > getdate(item.data_termino)
			):
				frappe.throw(_("Cronograma com data de inicio maior que data de termino."))

	def _hydrate_people_data(self):
		envolvidos = _get_normalized_envolvidos(self, strict=True, include_legacy=True)

		coordenadores = [row for row in envolvidos if cint(row.get("coordenador"))]
		if len(coordenadores) > 1:
			frappe.throw(_("Apenas um envolvido pode ser marcado como coordenador."))
		if coordenadores and coordenadores[0].get("tipo_pessoa") != APPROVER_TYPE_ASSOCIADO:
			frappe.throw(_("O coordenador do projeto deve ser do tipo Associado."))

		padrinhos = [row for row in envolvidos if cint(row.get("padrinho_orientador"))]
		if len(padrinhos) > 1:
			frappe.throw(_("Apenas um envolvido pode ser marcado como padrinho/orientador."))

		_set_doc_envolvidos(self, envolvidos)
		_sync_legacy_people_from_envolvidos(self, envolvidos)

	def _validate_people_scopes(self):
		team_names = {
			(row.get("nome") or "").strip()
			for row in _get_normalized_envolvidos(self, strict=False, include_legacy=True)
			if (row.get("nome") or "").strip()
		}

		for tarefa in self.tarefas or []:
			if tarefa.responsavel and tarefa.responsavel not in team_names:
				frappe.throw(
					_("Responsavel '{0}' da tarefa deve existir entre os envolvidos do projeto.").format(
						tarefa.responsavel
					)
				)

	def _validate_sponsor_category(self):
		padrinho = _get_padrinho_envolvido(self)
		if not padrinho:
			return

		if (padrinho.get("tipo_pessoa") or "") != APPROVER_TYPE_ASSOCIADO:
			return

		padrinho_associado = (padrinho.get("associado") or "").strip()
		if not padrinho_associado:
			return

		categoria = frappe.db.get_value("Associado", padrinho_associado, "categoria")
		if _is_beneficiario_categoria(categoria):
			frappe.throw(_("Padrinho associado nao pode ter categoria Beneficiario."))

	def _validate_drive_folder_link(self):
		link = (self.get("link_pasta_google_drive") or "").strip()
		if not link:
			self.link_pasta_google_drive = ""
			return

		if not is_valid_drive_folder_link(link):
			frappe.throw(_("Link da pasta Google Drive invalido."))

		self.link_pasta_google_drive = link


@frappe.whitelist()
def get_contato_pessoa(doctype_name: str, docname: str) -> dict[str, Any]:
	if doctype_name not in {"Associado", "Responsavel"}:
		frappe.throw(_("Tipo de pessoa invalido."))

	if doctype_name == "Associado":
		return _get_associado_payload(docname)

	return _get_responsavel_payload(docname)


def _get_associado_payload(name: str) -> dict[str, str]:
	data = frappe.db.get_value(
		"Associado",
		name,
		["nome_completo", "id_escoteiros", "email", "telefone"],
		as_dict=True,
	)
	if not data:
		frappe.throw(_("Associado nao encontrado."))

	email = data.get("id_escoteiros") or data.get("email")
	if not email or not data.get("telefone"):
		frappe.throw(_("Associado selecionado nao possui email ou telefone preenchido."))

	return {
		"nome": data.get("nome_completo") or name,
		"email": email,
		"telefone": data.get("telefone"),
	}


def _get_responsavel_payload(name: str) -> dict[str, str]:
	data = frappe.db.get_value(
		"Responsavel",
		name,
		["nome_completo", "email", "celular", "telefone_secundario"],
		as_dict=True,
	)
	if not data:
		frappe.throw(_("Responsavel nao encontrado."))

	telefone = data.get("celular") or data.get("telefone_secundario")
	if not data.get("email") or not telefone:
		frappe.throw(_("Responsavel selecionado nao possui email ou telefone preenchido."))

	return {
		"nome": data.get("nome_completo") or name,
		"email": data.get("email"),
		"telefone": telefone,
	}


STATUS_EM_APROVACAO = "Em aprovacao"
STATUS_APROVADO = "Aprovado"
STATUS_EM_EXECUCAO = "Em execucao"
STATUS_CONCLUIDO = "Concluido"
STATUS_CANCELADO = "Cancelado"
STATUS_EXECUCAO_PAGE_READ_ONLY = {STATUS_CONCLUIDO, STATUS_CANCELADO}
STATUS_EXECUCAO_PAGE_ALLOWED = {STATUS_EM_EXECUCAO, *STATUS_EXECUCAO_PAGE_READ_ONLY}
AVALIACAO_EM_PROCESSAMENTO = "Gerando avaliação..."
REVIEW_TYPE_APROVACAO = "Aprovacao"
REVIEW_TYPE_AJUSTE = "Solicitacao de alteracoes"
STAGE_APROVADORES_INICIAIS = "aprovadores_iniciais"
STAGE_CHEFE_SECAO = "chefe_secao"
STAGE_DIRETOR = "diretor_presidente"

APPROVER_TYPE_ASSOCIADO = "Associado"
APPROVER_TYPE_RESPONSAVEL = "Responsavel"
APPROVER_ORIGIN_MANUAL = "manual"
APPROVER_ORIGIN_DIRETOR = "diretor_presidente"
APPROVER_ORIGIN_PADRINHO = "padrinho_orientador"
APPROVER_ORIGIN_CHEFE_SECAO = "chefe_secao"

APPROVAL_STAGE_LABELS = {
	STAGE_APROVADORES_INICIAIS: "Padrinho / Orientador e demais aprovadores",
	STAGE_CHEFE_SECAO: "Chefe de Seção",
	STAGE_DIRETOR: "Diretor Presidente",
}

TASK_FIELDS = [
	"data_inicio",
	"prazo",
	"data_entrega",
	"descricao",
	"responsavel",
	"status",
	"observacoes",
]

TASK_STATUS_OPTIONS = {
	"Nao iniciado",
	"Em andamento",
	"Atrasado",
	"Concluido",
	"Cancelado",
}

MEETING_FIELDS = ["data_hora", "descricao", "pauta", "ata"]

AVALIACAO_RESUMO_EM_PROCESSAMENTO = "Gerando resumo..."
AVALIACAO_STATUS_EM_ANDAMENTO = "Em andamento"
AVALIACAO_STATUS_INDIVIDUAIS_CONCLUIDAS = "Avaliacoes individuais concluidas"
AVALIACAO_STATUS_CONCLUIDA = "Concluida"

SIMPLE_FORM_FIELDS = [
	"nome_do_projeto",
	"coordenador",
	"data_de_inicio",
	"data_de_termino",
	"tipo_padrinho_ou_orientador",
	"padrinho_associado",
	"padrinho_responsavel",
	"justificativa",
	"alinhamento_com_escotismo",
	"competencias",
	"especialidade",
	"observacoes_e_comentarios",
]

ENVOLVIDO_FIELDS = [
	"tipo_pessoa",
	"associado",
	"responsavel",
	"nome",
	"email",
	"telefone",
	"funcao",
	"coordenador",
	"padrinho_orientador",
	"aprovador",
	"origem_regra_aprovador",
	"permite_remover",
	"participa_avaliacao",
]

TABLE_FIELD_MAP = {
	"envolvidos": ENVOLVIDO_FIELDS,
	"objetivos": ["objetivo", "metrica_de_sucesso"],
	"ods": ["ods"],
	"cronograma": ["data_inicio", "data_termino", "tarefa"],
	"recursos": ["recurso"],
	"riscos": ["risco", "mitigacao"],
}


def _doc_has_field(doc: Document, fieldname: str) -> bool:
	meta = getattr(doc, "meta", None)
	return bool(meta and meta.has_field(fieldname))


def _to_bool_flag(value: Any, default: int = 0) -> int:
	if value in (None, ""):
		return 1 if default else 0
	return 1 if cint(value) else 0


def _normalize_envolvido_tipo_pessoa(value: Any) -> str:
	raw = (value or "").strip() if isinstance(value, str) else ""
	if raw in {APPROVER_TYPE_ASSOCIADO, APPROVER_TYPE_RESPONSAVEL, "Outro"}:
		return raw
	if raw.lower() == "nome livre":
		return "Outro"
	return "Outro"


def _make_envolvido_row_key(row: dict[str, Any]) -> str:
	tipo = (row.get("tipo_pessoa") or "").strip()
	if tipo == APPROVER_TYPE_ASSOCIADO and (row.get("associado") or "").strip():
		return f"Associado:{(row.get('associado') or '').strip()}"
	if tipo == APPROVER_TYPE_RESPONSAVEL and (row.get("responsavel") or "").strip():
		return f"Responsavel:{(row.get('responsavel') or '').strip()}"

	nome = _normalize_text(row.get("nome") or "")
	email = (row.get("email") or "").strip().lower()
	if nome or email:
		return f"Outro:{nome}:{email}"

	return ""


def _normalize_envolvido_row(row: Document | dict[str, Any], strict: bool = False) -> dict[str, Any] | None:
	tipo_pessoa = _normalize_envolvido_tipo_pessoa(row.get("tipo_pessoa"))
	associado = (row.get("associado") or "").strip() if tipo_pessoa == APPROVER_TYPE_ASSOCIADO else ""
	responsavel = (row.get("responsavel") or "").strip() if tipo_pessoa == APPROVER_TYPE_RESPONSAVEL else ""

	if tipo_pessoa == APPROVER_TYPE_ASSOCIADO and not associado:
		if strict:
			frappe.throw(_("Selecione um associado para envolvidos do tipo Associado."))
		return None

	if tipo_pessoa == APPROVER_TYPE_RESPONSAVEL and not responsavel:
		if strict:
			frappe.throw(_("Selecione um responsável para envolvidos do tipo Responsável."))
		return None

	if tipo_pessoa == APPROVER_TYPE_ASSOCIADO:
		payload = _get_associado_payload(associado) if strict else _get_associado_payload_loose(associado)
		nome = payload.get("nome") or (row.get("nome") or "")
		email = payload.get("email") or (row.get("email") or "")
		telefone = payload.get("telefone") or (row.get("telefone") or "")
	elif tipo_pessoa == APPROVER_TYPE_RESPONSAVEL:
		payload = (
			_get_responsavel_payload(responsavel) if strict else _get_responsavel_payload_loose(responsavel)
		)
		nome = payload.get("nome") or (row.get("nome") or "")
		email = payload.get("email") or (row.get("email") or "")
		telefone = payload.get("telefone") or (row.get("telefone") or "")
	else:
		nome = (row.get("nome") or "").strip()
		email = (row.get("email") or "").strip()
		telefone = (row.get("telefone") or "").strip()
		if strict and (not nome or not email or not telefone):
			frappe.throw(
				_("Para envolvidos do tipo Outro, preencha nome, email e telefone obrigatoriamente.")
			)

	funcao = (row.get("funcao") or "").strip()
	coordenador = _to_bool_flag(row.get("coordenador"), default=0)
	e_padrinho = _to_bool_flag(row.get("padrinho_orientador"), default=0)
	aprovador = _to_bool_flag(row.get("aprovador"), default=0)
	participa_avaliacao = _to_bool_flag(row.get("participa_avaliacao"), default=1)

	origem_regra_aprovador = (
		row.get("origem_regra_aprovador") or row.get("origem_regra") or APPROVER_ORIGIN_MANUAL
	).strip()
	if origem_regra_aprovador not in {
		APPROVER_ORIGIN_MANUAL,
		APPROVER_ORIGIN_DIRETOR,
		APPROVER_ORIGIN_PADRINHO,
		APPROVER_ORIGIN_CHEFE_SECAO,
	}:
		origem_regra_aprovador = APPROVER_ORIGIN_MANUAL

	if aprovador and tipo_pessoa not in {APPROVER_TYPE_ASSOCIADO, APPROVER_TYPE_RESPONSAVEL}:
		if strict:
			frappe.throw(_("Aprovadores devem ser do tipo Associado ou Responsável."))
		aprovador = 0

	if aprovador:
		if origem_regra_aprovador in {APPROVER_ORIGIN_PADRINHO, APPROVER_ORIGIN_CHEFE_SECAO}:
			permite_remover = 0
		else:
			permite_remover = _to_bool_flag(row.get("permite_remover"), default=1)
	else:
		origem_regra_aprovador = ""
		permite_remover = 1

	if strict and tipo_pessoa in {APPROVER_TYPE_ASSOCIADO, APPROVER_TYPE_RESPONSAVEL}:
		if not (email or "").strip() or not (telefone or "").strip():
			frappe.throw(_("Todos os envolvidos devem possuir email e telefone preenchidos."))

	normalized = {
		"tipo_pessoa": tipo_pessoa,
		"associado": associado,
		"responsavel": responsavel,
		"nome": (nome or "").strip(),
		"email": (email or "").strip(),
		"telefone": (telefone or "").strip(),
		"funcao": funcao,
		"coordenador": coordenador,
		"padrinho_orientador": e_padrinho,
		"aprovador": aprovador,
		"origem_regra_aprovador": origem_regra_aprovador,
		"permite_remover": 1 if permite_remover else 0,
		"participa_avaliacao": 1 if participa_avaliacao else 0,
	}
	normalized["key"] = _make_envolvido_row_key(normalized)
	if not normalized["key"]:
		if strict:
			frappe.throw(_("Não foi possível identificar um envolvido válido."))
		return None
	return normalized


def _merge_duplicate_envolvidos(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	origem_priority = {
		APPROVER_ORIGIN_MANUAL: 0,
		APPROVER_ORIGIN_DIRETOR: 1,
		APPROVER_ORIGIN_CHEFE_SECAO: 2,
		APPROVER_ORIGIN_PADRINHO: 3,
		"": -1,
	}

	merged: dict[str, dict[str, Any]] = {}
	order: list[str] = []

	for row in rows:
		key = (row.get("key") or "").strip()
		if not key:
			continue

		current = merged.get(key)
		if not current:
			merged[key] = row.copy()
			order.append(key)
			continue

		for fieldname in ["nome", "email", "telefone", "funcao", "associado", "responsavel"]:
			if not (current.get(fieldname) or "").strip() and (row.get(fieldname) or "").strip():
				current[fieldname] = (row.get(fieldname) or "").strip()

		current["coordenador"] = 1 if cint(current.get("coordenador")) or cint(row.get("coordenador")) else 0
		current["padrinho_orientador"] = (
			1 if cint(current.get("padrinho_orientador")) or cint(row.get("padrinho_orientador")) else 0
		)
		current["participa_avaliacao"] = (
			1 if cint(current.get("participa_avaliacao")) or cint(row.get("participa_avaliacao")) else 0
		)

		is_aprovador = 1 if cint(current.get("aprovador")) or cint(row.get("aprovador")) else 0
		current["aprovador"] = is_aprovador

		if is_aprovador:
			current_origin = (current.get("origem_regra_aprovador") or "").strip()
			row_origin = (row.get("origem_regra_aprovador") or "").strip()
			chosen_origin = row_origin
			if origem_priority.get(current_origin, -1) > origem_priority.get(row_origin, -1):
				chosen_origin = current_origin
			current["origem_regra_aprovador"] = chosen_origin or APPROVER_ORIGIN_MANUAL

			if current["origem_regra_aprovador"] in {
				APPROVER_ORIGIN_PADRINHO,
				APPROVER_ORIGIN_CHEFE_SECAO,
			}:
				current["permite_remover"] = 0
			else:
				row_perm = 1 if cint(row.get("permite_remover")) else 0
				current_perm = 1 if cint(current.get("permite_remover")) else 0
				current["permite_remover"] = 1 if current_perm and row_perm else 0
		else:
			current["origem_regra_aprovador"] = ""
			current["permite_remover"] = 1

		merged[key] = current

	return [merged[key] for key in order]


def _to_envolvido_child_payload(row: dict[str, Any]) -> dict[str, Any]:
	return {
		"tipo_pessoa": row.get("tipo_pessoa") or "Outro",
		"associado": row.get("associado") or "",
		"responsavel": row.get("responsavel") or "",
		"nome": row.get("nome") or "",
		"email": row.get("email") or "",
		"telefone": row.get("telefone") or "",
		"funcao": row.get("funcao") or "",
		"coordenador": 1 if cint(row.get("coordenador")) else 0,
		"padrinho_orientador": 1 if cint(row.get("padrinho_orientador")) else 0,
		"aprovador": 1 if cint(row.get("aprovador")) else 0,
		"origem_regra_aprovador": row.get("origem_regra_aprovador") or "",
		"permite_remover": 1 if cint(row.get("permite_remover")) else 0,
		"participa_avaliacao": 1 if cint(row.get("participa_avaliacao")) else 0,
	}


def _build_envolvidos_from_legacy(doc: Document) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []

	coordenador = (doc.get("coordenador") or "").strip()
	if coordenador:
		rows.append(
			{
				"tipo_pessoa": APPROVER_TYPE_ASSOCIADO,
				"associado": coordenador,
				"coordenador": 1,
				"participa_avaliacao": 1,
			}
		)

	tipo_padrinho = (doc.get("tipo_padrinho_ou_orientador") or "").strip()
	padrinho_associado = (doc.get("padrinho_associado") or "").strip()
	padrinho_responsavel = (doc.get("padrinho_responsavel") or "").strip()
	if tipo_padrinho == APPROVER_TYPE_ASSOCIADO and padrinho_associado:
		rows.append(
			{
				"tipo_pessoa": APPROVER_TYPE_ASSOCIADO,
				"associado": padrinho_associado,
				"padrinho_orientador": 1,
				"aprovador": 1,
				"origem_regra_aprovador": APPROVER_ORIGIN_PADRINHO,
				"permite_remover": 0,
				"participa_avaliacao": 1,
			}
		)
	elif tipo_padrinho == APPROVER_TYPE_RESPONSAVEL and padrinho_responsavel:
		rows.append(
			{
				"tipo_pessoa": APPROVER_TYPE_RESPONSAVEL,
				"responsavel": padrinho_responsavel,
				"padrinho_orientador": 1,
				"aprovador": 1,
				"origem_regra_aprovador": APPROVER_ORIGIN_PADRINHO,
				"permite_remover": 0,
				"participa_avaliacao": 1,
			}
		)

	normalized = [
		normalized_row
		for normalized_row in (_normalize_envolvido_row(row, strict=False) for row in rows)
		if normalized_row
	]
	return _merge_duplicate_envolvidos(normalized)


def _get_normalized_envolvidos(
	doc: Document,
	*,
	strict: bool,
	include_legacy: bool,
) -> list[dict[str, Any]]:
	rows = [
		normalized
		for normalized in (
			_normalize_envolvido_row(row, strict=strict) for row in (doc.get("envolvidos") or [])
		)
		if normalized
	]
	rows = _merge_duplicate_envolvidos(rows)
	if rows or not include_legacy:
		return rows
	return _build_envolvidos_from_legacy(doc)


def _set_doc_envolvidos(doc: Document, rows: list[dict[str, Any]]) -> None:
	if not _doc_has_field(doc, "envolvidos"):
		return

	doc.set("envolvidos", [])
	for row in rows:
		doc.append("envolvidos", _to_envolvido_child_payload(row))


def _get_coordenador_envolvido(doc: Document) -> dict[str, Any] | None:
	for row in _get_normalized_envolvidos(doc, strict=False, include_legacy=True):
		if cint(row.get("coordenador")) and (row.get("tipo_pessoa") or "") == APPROVER_TYPE_ASSOCIADO:
			if (row.get("associado") or "").strip():
				return row
	return None


def _get_padrinho_envolvido(doc: Document) -> dict[str, Any] | None:
	for row in _get_normalized_envolvidos(doc, strict=False, include_legacy=True):
		if not cint(row.get("padrinho_orientador")):
			continue
		tipo = row.get("tipo_pessoa") or ""
		if tipo == APPROVER_TYPE_ASSOCIADO and (row.get("associado") or "").strip():
			return row
		if tipo == APPROVER_TYPE_RESPONSAVEL and (row.get("responsavel") or "").strip():
			return row
	return None


def _sync_legacy_people_from_envolvidos(
	doc: Document, envolvidos: list[dict[str, Any]] | None = None
) -> None:
	rows = (
		envolvidos
		if envolvidos is not None
		else _get_normalized_envolvidos(doc, strict=False, include_legacy=True)
	)

	coordenador = next(
		(
			row
			for row in rows
			if cint(row.get("coordenador"))
			and (row.get("tipo_pessoa") or "") == APPROVER_TYPE_ASSOCIADO
			and (row.get("associado") or "").strip()
		),
		None,
	)
	if _doc_has_field(doc, "coordenador"):
		doc.set("coordenador", (coordenador or {}).get("associado") or "")

	padrinho = next(
		(
			row
			for row in rows
			if cint(row.get("padrinho_orientador"))
			and (
				(
					(row.get("tipo_pessoa") or "") == APPROVER_TYPE_ASSOCIADO
					and (row.get("associado") or "").strip()
				)
				or (
					(row.get("tipo_pessoa") or "") == APPROVER_TYPE_RESPONSAVEL
					and (row.get("responsavel") or "").strip()
				)
			)
		),
		None,
	)
	if _doc_has_field(doc, "tipo_padrinho_ou_orientador"):
		doc.set("tipo_padrinho_ou_orientador", (padrinho or {}).get("tipo_pessoa") or "")
	if _doc_has_field(doc, "padrinho_associado"):
		doc.set(
			"padrinho_associado",
			(padrinho or {}).get("associado")
			if (padrinho or {}).get("tipo_pessoa") == APPROVER_TYPE_ASSOCIADO
			else "",
		)
	if _doc_has_field(doc, "padrinho_responsavel"):
		doc.set(
			"padrinho_responsavel",
			(padrinho or {}).get("responsavel")
			if (padrinho or {}).get("tipo_pessoa") == APPROVER_TYPE_RESPONSAVEL
			else "",
		)


def _get_user_associados(user: str) -> list[dict[str, str]]:
	if not user:
		return []

	return frappe.get_all(
		"Associado",
		or_filters={"id_escoteiros": user, "email": user},
		fields=["name", "nome_completo", "secao"],
		limit_page_length=20,
	)


def _get_user_responsaveis(user: str) -> list[dict[str, str]]:
	if not user:
		return []

	rows = frappe.db.sql(
		"""
			SELECT name, nome_completo, email
			FROM `tabResponsavel`
			WHERE lower(email) = lower(%s)
		""",
		(user,),
		as_dict=True,
	)
	return rows or []


def _resolve_associado_names(associado_ids: list[str]) -> dict[str, str]:
	if not associado_ids:
		return {}

	rows = frappe.get_all(
		"Associado",
		filters={"name": ["in", associado_ids]},
		fields=["name", "nome_completo"],
		limit_page_length=len(associado_ids),
	)
	return {row.get("name"): row.get("nome_completo") or row.get("name") for row in rows}


def _resolve_responsavel_names(responsavel_ids: list[str]) -> dict[str, str]:
	if not responsavel_ids:
		return {}

	rows = frappe.get_all(
		"Responsavel",
		filters={"name": ["in", responsavel_ids]},
		fields=["name", "nome_completo"],
		limit_page_length=len(responsavel_ids),
	)
	return {row.get("name"): row.get("nome_completo") or row.get("name") for row in rows}


def _get_stage_associados_by_function(funcao: str, secao: str | None = None) -> list[str]:
	filters: dict[str, Any] = {"funcao": funcao}
	if secao:
		filters["secao"] = secao

	rows = frappe.get_all(
		"Associado",
		filters=filters,
		fields=["name"],
		order_by="modified desc",
		limit_page_length=200,
	)
	return [row.get("name") for row in rows if row.get("name")]


def _make_approver_key(tipo_pessoa: str, docname: str) -> str:
	tipo = (tipo_pessoa or "").strip()
	nome = (docname or "").strip()
	if not tipo or not nome:
		return ""
	return f"{tipo}:{nome}"


def _split_approver_key(raw_key: str) -> tuple[str, str]:
	key = (raw_key or "").strip()
	if not key:
		return "", ""
	if ":" not in key:
		return "", key
	tipo, docname = key.split(":", 1)
	return tipo.strip(), docname.strip()


def _get_associado_payload_loose(name: str) -> dict[str, str]:
	data = frappe.db.get_value(
		"Associado",
		name,
		["nome_completo", "id_escoteiros", "email", "telefone"],
		as_dict=True,
	)
	if not data:
		return {
			"nome": name,
			"email": "",
			"telefone": "",
		}

	return {
		"nome": data.get("nome_completo") or name,
		"email": data.get("id_escoteiros") or data.get("email") or "",
		"telefone": data.get("telefone") or "",
	}


def _get_responsavel_payload_loose(name: str) -> dict[str, str]:
	data = frappe.db.get_value(
		"Responsavel",
		name,
		["nome_completo", "email", "celular", "telefone_secundario"],
		as_dict=True,
	)
	if not data:
		return {
			"nome": name,
			"email": "",
			"telefone": "",
		}

	return {
		"nome": data.get("nome_completo") or name,
		"email": data.get("email") or "",
		"telefone": data.get("celular") or data.get("telefone_secundario") or "",
	}


def _get_person_payload_by_type(tipo_pessoa: str, docname: str, strict: bool) -> dict[str, str]:
	tipo = (tipo_pessoa or "").strip()
	if tipo == APPROVER_TYPE_ASSOCIADO:
		return _get_associado_payload(docname) if strict else _get_associado_payload_loose(docname)
	if tipo == APPROVER_TYPE_RESPONSAVEL:
		return _get_responsavel_payload(docname) if strict else _get_responsavel_payload_loose(docname)
	if strict:
		frappe.throw(_("Tipo de aprovador inválido."))
	return {"nome": "", "email": "", "telefone": ""}


def _normalize_aprovador_row(row: Document | dict[str, Any], strict: bool = False) -> dict[str, Any] | None:
	tipo_pessoa = (row.get("tipo_pessoa") or "").strip()
	if tipo_pessoa not in {APPROVER_TYPE_ASSOCIADO, APPROVER_TYPE_RESPONSAVEL}:
		if strict:
			frappe.throw(_("Tipo de pessoa inválido na tabela de aprovadores."))
		return None

	associado = (row.get("associado") or "").strip() if tipo_pessoa == APPROVER_TYPE_ASSOCIADO else ""
	responsavel = (row.get("responsavel") or "").strip() if tipo_pessoa == APPROVER_TYPE_RESPONSAVEL else ""
	docname = associado or responsavel
	if not docname:
		if strict:
			frappe.throw(_("Cada aprovador deve ter uma pessoa vinculada."))
		return None

	payload = _get_person_payload_by_type(tipo_pessoa, docname, strict=strict)
	origem_regra = (row.get("origem_regra") or APPROVER_ORIGIN_MANUAL).strip()
	if origem_regra not in {
		APPROVER_ORIGIN_MANUAL,
		APPROVER_ORIGIN_DIRETOR,
		APPROVER_ORIGIN_PADRINHO,
		APPROVER_ORIGIN_CHEFE_SECAO,
	}:
		origem_regra = APPROVER_ORIGIN_MANUAL

	permite_remover_raw = row.get("permite_remover")
	if origem_regra in {APPROVER_ORIGIN_PADRINHO, APPROVER_ORIGIN_CHEFE_SECAO}:
		permite_remover = 0
	elif permite_remover_raw in (None, ""):
		permite_remover = 1
	else:
		permite_remover = 1 if cint(permite_remover_raw) else 0

	return {
		"tipo_pessoa": tipo_pessoa,
		"associado": associado,
		"responsavel": responsavel,
		"nome": payload.get("nome") or (row.get("nome") or ""),
		"email": payload.get("email") or (row.get("email") or ""),
		"telefone": payload.get("telefone") or (row.get("telefone") or ""),
		"origem_regra": origem_regra,
		"permite_remover": permite_remover,
		"key": _make_approver_key(tipo_pessoa, docname),
	}


def _to_aprovador_child_payload(row: dict[str, Any]) -> dict[str, Any]:
	return {
		"tipo_pessoa": row.get("tipo_pessoa") or "",
		"associado": row.get("associado") or "",
		"responsavel": row.get("responsavel") or "",
		"nome": row.get("nome") or "",
		"email": row.get("email") or "",
		"telefone": row.get("telefone") or "",
		"origem_regra": row.get("origem_regra") or APPROVER_ORIGIN_MANUAL,
		"permite_remover": 1 if cint(row.get("permite_remover")) else 0,
	}


def _merge_duplicate_aprovadores(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	origem_priority = {
		APPROVER_ORIGIN_MANUAL: 0,
		APPROVER_ORIGIN_DIRETOR: 1,
		APPROVER_ORIGIN_CHEFE_SECAO: 2,
		APPROVER_ORIGIN_PADRINHO: 3,
	}
	merged: dict[str, dict[str, Any]] = {}
	order: list[str] = []

	for row in rows:
		key = (row.get("key") or "").strip()
		if not key:
			continue

		current = merged.get(key)
		if not current:
			merged[key] = row
			order.append(key)
			continue

		current_priority = origem_priority.get(current.get("origem_regra"), 0)
		row_priority = origem_priority.get(row.get("origem_regra"), 0)
		if row_priority > current_priority:
			merged[key] = row

	return [merged[key] for key in order]


def _get_sponsor_approver_identity(doc: Document, strict: bool = False) -> dict[str, Any] | None:
	padrinho = _get_padrinho_envolvido(doc)
	if not padrinho:
		return None

	base_row = {
		"tipo_pessoa": padrinho.get("tipo_pessoa") or "",
		"associado": padrinho.get("associado") or "",
		"responsavel": padrinho.get("responsavel") or "",
		"origem_regra": APPROVER_ORIGIN_PADRINHO,
		"permite_remover": 0,
	}
	return _normalize_aprovador_row(base_row, strict=strict)


def _get_coordinator_profile(doc: Document) -> dict[str, str]:
	coordenador_row = _get_coordenador_envolvido(doc)
	coordenador = (coordenador_row or {}).get("associado") or ""
	if not coordenador:
		return {
			"coordenador": "",
			"categoria": "",
			"secao": "",
			"ramo": "",
		}

	data = frappe.db.get_value("Associado", coordenador, ["categoria", "secao", "ramo"], as_dict=True) or {}
	return {
		"coordenador": coordenador,
		"categoria": (data.get("categoria") or "").strip(),
		"secao": (data.get("secao") or "").strip(),
		"ramo": (data.get("ramo") or "").strip(),
	}


def _get_section_chief_associados(secao: str, ramo: str = "") -> list[str]:
	candidates = frappe.get_all(
		"Associado",
		filters={"funcao": ["like", "%Chefe%"]},
		fields=["name", "funcao", "secao", "ramo"],
		order_by="modified desc",
		limit_page_length=500,
	)

	section_chiefs = [
		row for row in candidates if row.get("name") and _is_section_chief_function(row.get("funcao"))
	]
	if not section_chiefs:
		return []

	normalized_secao = _normalize_text(secao)
	if normalized_secao:
		matched_by_secao = [
			row.get("name") for row in section_chiefs if _normalize_text(row.get("secao")) == normalized_secao
		]
		matched_by_secao = [name for name in matched_by_secao if name]
		if matched_by_secao:
			return list(dict.fromkeys(matched_by_secao))

	normalized_ramo = _normalize_text(ramo)
	if normalized_ramo:
		matched_by_ramo = [
			row.get("name") for row in section_chiefs if _normalize_text(row.get("ramo")) == normalized_ramo
		]
		matched_by_ramo = [name for name in matched_by_ramo if name]
		if matched_by_ramo:
			return list(dict.fromkeys(matched_by_ramo))

	return []


def _get_section_chief_approver_identities(doc: Document, strict: bool = False) -> list[dict[str, Any]]:
	profile = _get_coordinator_profile(doc)
	if not profile.get("coordenador"):
		return []

	if not _is_beneficiario_categoria(profile.get("categoria")):
		return []

	secao = profile.get("secao") or ""
	ramo = profile.get("ramo") or ""
	if not secao and not ramo:
		if strict:
			frappe.throw(
				_(
					"O coordenador é jovem, mas não possui seção ou ramo definidos. Configure ao menos um deles para definir o chefe de seção aprovador."
				)
			)
		return []

	chefes = _get_section_chief_associados(secao, ramo=ramo)
	if not chefes:
		if strict:
			frappe.throw(
				_(
					"Não foi encontrado chefe de seção para o coordenador jovem (seção: {0}, ramo: {1}). Defina ao menos um chefe de seção para continuar."
				).format(secao or "-", ramo or "-")
			)
		return []

	rows: list[dict[str, Any]] = []
	for associado in chefes:
		normalized = _normalize_aprovador_row(
			{
				"tipo_pessoa": APPROVER_TYPE_ASSOCIADO,
				"associado": associado,
				"origem_regra": APPROVER_ORIGIN_CHEFE_SECAO,
				"permite_remover": 0,
			},
			strict=strict,
		)
		if normalized:
			rows.append(normalized)

	return _merge_duplicate_aprovadores(rows)


def _get_mandatory_aprovadores(doc: Document, strict: bool = False) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []
	sponsor = _get_sponsor_approver_identity(doc, strict=strict)
	if sponsor:
		rows.append(sponsor)

	rows.extend(_get_section_chief_approver_identities(doc, strict=strict))
	return _merge_duplicate_aprovadores(rows)


def _build_default_aprovadores(doc: Document, strict: bool = False) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = _get_mandatory_aprovadores(doc, strict=strict)
	for associado in _get_stage_associados_by_function("Diretor Presidente"):
		normalized = _normalize_aprovador_row(
			{
				"tipo_pessoa": APPROVER_TYPE_ASSOCIADO,
				"associado": associado,
				"origem_regra": APPROVER_ORIGIN_DIRETOR,
				"permite_remover": 1,
			},
			strict=strict,
		)
		if normalized:
			rows.append(normalized)
	return _merge_duplicate_aprovadores(rows)


def _get_aprovadores_from_envolvidos(doc: Document, strict: bool = False) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []
	for envolvido in _get_normalized_envolvidos(doc, strict=strict, include_legacy=True):
		if not cint(envolvido.get("aprovador")):
			continue
		normalized = _normalize_aprovador_row(
			{
				"tipo_pessoa": envolvido.get("tipo_pessoa") or "",
				"associado": envolvido.get("associado") or "",
				"responsavel": envolvido.get("responsavel") or "",
				"origem_regra": envolvido.get("origem_regra_aprovador") or APPROVER_ORIGIN_MANUAL,
				"permite_remover": envolvido.get("permite_remover"),
			},
			strict=strict,
		)
		if not normalized:
			continue
		normalized["nome"] = envolvido.get("nome") or normalized.get("nome") or ""
		normalized["email"] = envolvido.get("email") or normalized.get("email") or ""
		normalized["telefone"] = envolvido.get("telefone") or normalized.get("telefone") or ""
		rows.append(normalized)

	return _merge_duplicate_aprovadores(rows)


def _apply_approver_rows_to_envolvidos(doc: Document, approver_rows: list[dict[str, Any]]) -> None:
	base_rows = _get_normalized_envolvidos(doc, strict=False, include_legacy=True)
	by_key: dict[str, dict[str, Any]] = {
		row.get("key") or "": row.copy() for row in base_rows if row.get("key")
	}
	target_order: list[str] = []

	for approver in approver_rows:
		key = (approver.get("key") or "").strip()
		if not key:
			continue
		if key not in target_order:
			target_order.append(key)

		current = by_key.get(key)
		if not current:
			current = _normalize_envolvido_row(
				{
					"tipo_pessoa": approver.get("tipo_pessoa") or "",
					"associado": approver.get("associado") or "",
					"responsavel": approver.get("responsavel") or "",
					"nome": approver.get("nome") or "",
					"email": approver.get("email") or "",
					"telefone": approver.get("telefone") or "",
					"funcao": "",
					"participa_avaliacao": 1,
				},
				strict=False,
			)
			if not current:
				continue

		current["tipo_pessoa"] = approver.get("tipo_pessoa") or current.get("tipo_pessoa") or "Outro"
		current["associado"] = approver.get("associado") or ""
		current["responsavel"] = approver.get("responsavel") or ""
		current["nome"] = approver.get("nome") or current.get("nome") or ""
		current["email"] = approver.get("email") or current.get("email") or ""
		current["telefone"] = approver.get("telefone") or current.get("telefone") or ""
		current["aprovador"] = 1
		current["origem_regra_aprovador"] = approver.get("origem_regra") or APPROVER_ORIGIN_MANUAL
		current["permite_remover"] = 1 if cint(approver.get("permite_remover")) else 0
		if current["origem_regra_aprovador"] == APPROVER_ORIGIN_PADRINHO:
			current["padrinho_orientador"] = 1

		by_key[key] = current

	target_keys = set(target_order)
	for key, row in by_key.items():
		if not key:
			continue
		if not cint(row.get("aprovador")):
			continue
		if key in target_keys:
			continue
		row["aprovador"] = 0
		row["origem_regra_aprovador"] = ""
		row["permite_remover"] = 1

	ordered_keys = [key for key in (row.get("key") or "" for row in base_rows) if key in by_key]
	for key in target_order:
		if key not in ordered_keys:
			ordered_keys.append(key)

	merged_rows = _merge_duplicate_envolvidos([by_key[key] for key in ordered_keys if key in by_key])
	_set_doc_envolvidos(doc, merged_rows)
	_sync_legacy_people_from_envolvidos(doc, merged_rows)


def _bootstrap_aprovadores_if_empty(doc: Document) -> None:
	current_aprovadores = _get_aprovadores_from_envolvidos(doc, strict=False)
	if current_aprovadores:
		_apply_approver_rows_to_envolvidos(doc, current_aprovadores)
		return

	defaults = _build_default_aprovadores(doc, strict=False)
	if not defaults:
		return

	_apply_approver_rows_to_envolvidos(doc, defaults)


def _sync_sponsor_approver(doc: Document) -> None:
	mandatory_origins = {APPROVER_ORIGIN_PADRINHO, APPROVER_ORIGIN_CHEFE_SECAO}
	current_rows = _get_aprovadores_from_envolvidos(doc, strict=False)

	current_rows = [row for row in current_rows if row.get("origem_regra") not in mandatory_origins]
	mandatory_rows = _get_mandatory_aprovadores(doc, strict=False)
	mandatory_keys = {(row.get("key") or "") for row in mandatory_rows if (row.get("key") or "")}

	merged_rows: list[dict[str, Any]] = list(mandatory_rows)

	for row in current_rows:
		if (row.get("key") or "") in mandatory_keys:
			continue
		merged_rows.append(row)

	merged_rows = _merge_duplicate_aprovadores(merged_rows)
	_apply_approver_rows_to_envolvidos(doc, merged_rows)


def _get_effective_aprovadores(doc: Document, strict: bool = False) -> list[dict[str, Any]]:
	mandatory_origins = {APPROVER_ORIGIN_PADRINHO, APPROVER_ORIGIN_CHEFE_SECAO}
	rows = _get_aprovadores_from_envolvidos(doc, strict=strict)

	if not rows:
		rows = _build_default_aprovadores(doc, strict=strict)

	mandatory_rows = _get_mandatory_aprovadores(doc, strict=strict)
	if mandatory_rows:
		without_mandatory_origins = [row for row in rows if row.get("origem_regra") not in mandatory_origins]
		mandatory_keys = {(row.get("key") or "") for row in mandatory_rows if (row.get("key") or "")}
		rows = list(mandatory_rows)
		for row in without_mandatory_origins:
			if (row.get("key") or "") in mandatory_keys:
				continue
			rows.append(row)
		rows = _merge_duplicate_aprovadores(rows)

	return rows


def _build_approval_pipeline(doc: Document) -> list[dict[str, Any]]:
	approvers = _get_effective_aprovadores(doc, strict=False)
	aprovadores_iniciais = [
		row
		for row in approvers
		if row.get("origem_regra") in {APPROVER_ORIGIN_PADRINHO, APPROVER_ORIGIN_MANUAL}
	]
	chefes_secao = [row for row in approvers if row.get("origem_regra") == APPROVER_ORIGIN_CHEFE_SECAO]
	diretores = [row for row in approvers if row.get("origem_regra") == APPROVER_ORIGIN_DIRETOR]

	pipeline: list[dict[str, Any]] = []
	if aprovadores_iniciais:
		pipeline.append(
			{
				"key": STAGE_APROVADORES_INICIAIS,
				"label": APPROVAL_STAGE_LABELS[STAGE_APROVADORES_INICIAIS],
				"approvers": aprovadores_iniciais,
			}
		)
	if chefes_secao:
		pipeline.append(
			{
				"key": STAGE_CHEFE_SECAO,
				"label": APPROVAL_STAGE_LABELS[STAGE_CHEFE_SECAO],
				"approvers": chefes_secao,
			}
		)
	if diretores:
		pipeline.append(
			{
				"key": STAGE_DIRETOR,
				"label": APPROVAL_STAGE_LABELS[STAGE_DIRETOR],
				"approvers": diretores,
			}
		)

	return pipeline


def _assert_approval_pipeline_ready(doc: Document) -> None:
	pipeline = _build_approval_pipeline(doc)
	if not pipeline:
		frappe.throw(
			_(
				"Não foi encontrado aprovador elegível para o fluxo de aprovação. Defina padrinho/orientador e ao menos um aprovador adicional."
			)
		)

	first_stage = pipeline[0]
	if not first_stage.get("approvers"):
		frappe.throw(
			_(
				"Não foi encontrado aprovador elegível para a etapa inicial de aprovação. Verifique os aprovadores configurados."
			)
		)


def _get_pending_review_comments(doc: Document) -> list[Document]:
	pending: list[Document] = []
	for row in doc.get("comentarios_revisao_aprovacao") or []:
		if (row.get("tipo_revisao") or "") != REVIEW_TYPE_AJUSTE:
			continue
		if cint(row.get("resolvido")) == 1:
			continue
		pending.append(row)
	return pending


def _assert_no_pending_review_comments(doc: Document) -> None:
	pending = _get_pending_review_comments(doc)
	if not pending:
		return
	frappe.throw(
		_(
			"Existem comentários de revisão pendentes de resolução. Resolva todos os comentários para submeter novamente."
		)
	)


def _get_review_row_approver_identity(row: Document) -> dict[str, str]:
	tipo = (row.get("aprovador_tipo") or "").strip()
	associado = (row.get("aprovador_associado") or "").strip()
	responsavel = (row.get("aprovador_responsavel") or "").strip()
	raw_aprovador = (row.get("aprovador") or "").strip()

	if raw_aprovador and ":" in raw_aprovador:
		key_tipo, key_name = _split_approver_key(raw_aprovador)
		if not tipo:
			tipo = key_tipo
		if tipo == APPROVER_TYPE_ASSOCIADO and not associado:
			associado = key_name
		if tipo == APPROVER_TYPE_RESPONSAVEL and not responsavel:
			responsavel = key_name

	if not tipo:
		if associado:
			tipo = APPROVER_TYPE_ASSOCIADO
		elif responsavel:
			tipo = APPROVER_TYPE_RESPONSAVEL
		elif raw_aprovador:
			tipo = APPROVER_TYPE_ASSOCIADO
			associado = raw_aprovador

	if tipo == APPROVER_TYPE_ASSOCIADO and not associado and raw_aprovador and ":" not in raw_aprovador:
		associado = raw_aprovador
	if tipo == APPROVER_TYPE_RESPONSAVEL and not responsavel and raw_aprovador and ":" not in raw_aprovador:
		responsavel = raw_aprovador

	docname = associado if tipo == APPROVER_TYPE_ASSOCIADO else responsavel
	return {
		"tipo_pessoa": tipo,
		"associado": associado,
		"responsavel": responsavel,
		"key": _make_approver_key(tipo, docname),
	}


def _get_approved_keys_by_stage(doc: Document) -> dict[str, set[str]]:
	approved: dict[str, set[str]] = {}
	for row in doc.get("comentarios_revisao_aprovacao") or []:
		if (row.get("tipo_revisao") or "") != REVIEW_TYPE_APROVACAO:
			continue

		stage_key = (row.get("etapa_aprovacao") or "").strip()
		if not stage_key:
			continue

		identity = _get_review_row_approver_identity(row)
		key = identity.get("key")
		if not key:
			continue

		approved.setdefault(stage_key, set()).add(key)

	return approved


def _is_stage_completed(stage: dict[str, Any], approved_map: dict[str, set[str]]) -> bool:
	required_keys = {
		(approver.get("key") or "").strip() for approver in (stage.get("approvers") or []) if approver
	}
	required_keys.discard("")
	if not required_keys:
		return True

	stage_approved = approved_map.get(stage.get("key") or "", set())
	return required_keys.issubset(stage_approved)


def _get_current_approval_stage(doc: Document, pipeline: list[dict[str, Any]]) -> dict[str, Any] | None:
	approved_map = _get_approved_keys_by_stage(doc)
	for stage in pipeline:
		if not _is_stage_completed(stage, approved_map):
			return stage
	return None


def _is_user_coordinator(user: str, doc: Document) -> bool:
	coordenador_row = _get_coordenador_envolvido(doc)
	coordenador = (coordenador_row or {}).get("associado") or ""
	if not coordenador or not user:
		return False

	user_associados = {row.get("name") for row in _get_user_associados(user) if row.get("name")}
	return coordenador in user_associados


def _append_review_row(
	doc: Document,
	*,
	aprovador: dict[str, Any],
	tipo_revisao: str,
	etapa_key: str,
	comentarios: str,
	resolvido: int,
) -> None:
	aprovador_tipo = (aprovador.get("tipo_pessoa") or "").strip()
	aprovador_associado = (aprovador.get("associado") or "").strip()
	aprovador_responsavel = (aprovador.get("responsavel") or "").strip()
	aprovador_docname = aprovador_associado or aprovador_responsavel
	aprovador_key = _make_approver_key(aprovador_tipo, aprovador_docname)

	doc.append(
		"comentarios_revisao_aprovacao",
		{
			"aprovador": aprovador_key or aprovador_docname,
			"aprovador_tipo": aprovador_tipo,
			"aprovador_associado": aprovador_associado,
			"aprovador_responsavel": aprovador_responsavel,
			"aprovador_label": aprovador.get("nome") or aprovador_docname,
			"aprovador_email": aprovador.get("email") or "",
			"aprovador_telefone": aprovador.get("telefone") or "",
			"data_da_revisao": now_datetime(),
			"etapa_aprovacao": etapa_key,
			"tipo_revisao": tipo_revisao,
			"comentarios": (comentarios or "").strip(),
			"resolvido": 1 if resolvido else 0,
		},
	)


def _clear_approval_rows(doc: Document) -> None:
	review_rows = doc.get("comentarios_revisao_aprovacao") or []
	if not review_rows:
		return

	kept_rows: list[dict[str, Any]] = []
	for row in review_rows:
		if (row.get("tipo_revisao") or "") == REVIEW_TYPE_APROVACAO:
			continue
		kept_rows.append(
			{
				"aprovador": row.get("aprovador"),
				"aprovador_tipo": row.get("aprovador_tipo"),
				"aprovador_associado": row.get("aprovador_associado"),
				"aprovador_responsavel": row.get("aprovador_responsavel"),
				"aprovador_label": row.get("aprovador_label"),
				"aprovador_email": row.get("aprovador_email"),
				"aprovador_telefone": row.get("aprovador_telefone"),
				"data_da_revisao": row.get("data_da_revisao"),
				"etapa_aprovacao": row.get("etapa_aprovacao"),
				"tipo_revisao": row.get("tipo_revisao"),
				"comentarios": row.get("comentarios"),
				"resolvido": row.get("resolvido"),
			}
		)

	doc.set("comentarios_revisao_aprovacao", [])
	for row in kept_rows:
		doc.append("comentarios_revisao_aprovacao", row)


def _get_user_approver_keys(user: str) -> set[str]:
	keys: set[str] = set()

	for associado in _get_user_associados(user):
		nome = (associado.get("name") or "").strip()
		if nome:
			keys.add(_make_approver_key(APPROVER_TYPE_ASSOCIADO, nome))

	for responsavel in _get_user_responsaveis(user):
		nome = (responsavel.get("name") or "").strip()
		if nome:
			keys.add(_make_approver_key(APPROVER_TYPE_RESPONSAVEL, nome))

	return keys


def _get_stage_user_approver(user: str, stage: dict[str, Any]) -> dict[str, Any] | None:
	stage_approvers = stage.get("approvers") or []
	if not stage_approvers:
		return None

	user_keys = _get_user_approver_keys(user)
	if not user_keys:
		return None

	for approver in stage_approvers:
		if (approver.get("key") or "") in user_keys:
			return approver

	return None


def _serialize_review_rows(rows: list[Document]) -> list[dict[str, Any]]:
	if not rows:
		return []

	associado_ids: list[str] = []
	responsavel_ids: list[str] = []
	for row in rows:
		identity = _get_review_row_approver_identity(row)
		if identity.get("associado"):
			associado_ids.append(identity.get("associado") or "")
		if identity.get("responsavel"):
			responsavel_ids.append(identity.get("responsavel") or "")

	associado_labels = _resolve_associado_names(list({row for row in associado_ids if row}))
	responsavel_labels = _resolve_responsavel_names(list({row for row in responsavel_ids if row}))

	serialized: list[dict[str, Any]] = []
	for row in rows:
		identity = _get_review_row_approver_identity(row)
		tipo_pessoa = identity.get("tipo_pessoa")
		associado = identity.get("associado")
		responsavel = identity.get("responsavel")
		default_label = ""
		if tipo_pessoa == APPROVER_TYPE_ASSOCIADO and associado:
			default_label = associado_labels.get(associado, associado)
		elif tipo_pessoa == APPROVER_TYPE_RESPONSAVEL and responsavel:
			default_label = responsavel_labels.get(responsavel, responsavel)

		aprovador_raw = (row.get("aprovador") or "").strip()
		aprovador_value = identity.get("key") or aprovador_raw
		stage_key = (row.get("etapa_aprovacao") or "").strip()
		serialized.append(
			{
				"name": row.get("name"),
				"idx": row.get("idx"),
				"aprovador": aprovador_value,
				"aprovador_tipo": tipo_pessoa,
				"aprovador_associado": associado,
				"aprovador_responsavel": responsavel,
				"aprovador_label": row.get("aprovador_label") or default_label or aprovador_value,
				"aprovador_email": row.get("aprovador_email") or "",
				"aprovador_telefone": row.get("aprovador_telefone") or "",
				"data_da_revisao": row.get("data_da_revisao"),
				"tipo_revisao": row.get("tipo_revisao"),
				"etapa_aprovacao": stage_key,
				"etapa_label": APPROVAL_STAGE_LABELS.get(stage_key, stage_key),
				"comentarios": row.get("comentarios"),
				"resolvido": cint(row.get("resolvido")),
			}
		)
	return serialized


def _serialize_pipeline(doc: Document, user: str) -> dict[str, Any]:
	pipeline = _build_approval_pipeline(doc)
	approved_map = _get_approved_keys_by_stage(doc)
	current_stage = _get_current_approval_stage(doc, pipeline)

	stages: list[dict[str, Any]] = []
	for stage in pipeline:
		approvers = stage.get("approvers") or []
		required_keys = {(approver.get("key") or "") for approver in approvers if (approver.get("key") or "")}
		approved_for_stage = approved_map.get(stage.get("key") or "", set())
		is_completed = _is_stage_completed(stage, approved_map)
		stages.append(
			{
				"key": stage.get("key"),
				"label": stage.get("label"),
				"completed": is_completed,
				"is_current": bool(current_stage and stage.get("key") == current_stage.get("key")),
				"required_count": len(required_keys),
				"approved_count": len(required_keys & approved_for_stage),
				"approvers": [
					{
						"key": approver.get("key"),
						"tipo_pessoa": approver.get("tipo_pessoa"),
						"name": approver.get("associado") or approver.get("responsavel"),
						"label": approver.get("nome")
						or approver.get("associado")
						or approver.get("responsavel"),
					}
					for approver in approvers
				],
			}
		)

	can_decide = False
	if current_stage:
		can_decide = bool(_get_stage_user_approver(user, current_stage))

	return {
		"stages": stages,
		"current_stage_key": current_stage.get("key") if current_stage else "",
		"current_stage_label": current_stage.get("label") if current_stage else "",
		"can_decide": can_decide,
	}


def _build_project_portal_link(path: str, projeto_name: str) -> str:
	encoded_name = quote((projeto_name or "").strip())
	return frappe.utils.get_url(f"{path}?projeto={encoded_name}")


def _send_whatsapp_notification(
	numero: str,
	mensagem: str,
	*,
	contexto: str,
	enqueue: bool = True,
) -> bool:
	telefone = (numero or "").strip()
	if not telefone or not mensagem:
		return False

	try:
		enviar_texto(telefone, mensagem, enqueue=enqueue)
		return True
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Falha ao enviar WhatsApp ({contexto})",
		)
		return False


def _send_whatsapp_project_button_notification(
	numero: str,
	*,
	titulo: str,
	descricao: str,
	link: str,
	contexto: str,
) -> bool:
	telefone = (numero or "").strip()
	if not telefone or not titulo or not descricao or not link:
		return False

	button_label = "Clique para abrir projeto"
	botoes = [
		{
			"type": "url",
			"displayText": button_label,
			"url": link,
		}
	]

	try:
		enviar_mensagem_formatada(
			telefone,
			titulo=titulo,
			descricao=descricao,
			footer="GRIS",
			botoes=botoes,
			enqueue=False,
		)
		return True
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Falha ao enviar WhatsApp com botão ({contexto})",
		)

	fallback_message = f"{titulo}\n\n{descricao}\n\n{button_label}: {link}"
	return _send_whatsapp_notification(
		telefone,
		fallback_message,
		contexto=f"{contexto}:fallback",
		enqueue=False,
	)


def _enqueue_project_whatsapp_job(method: str, **kwargs) -> None:
	try:
		frappe.enqueue(
			method=method,
			queue="short",
			timeout=180,
			enqueue_after_commit=True,
			**kwargs,
		)
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Falha ao enfileirar job de WhatsApp ({method})",
		)


def _enqueue_project_drive_folder_creation(projeto_name: str) -> None:
	if not projeto_name:
		return

	try:
		frappe.enqueue(
			method="gris.api.google_workspace.project_drive.create_project_folder_async",
			queue="long",
			timeout=300,
			enqueue_after_commit=True,
			projeto_name=projeto_name,
		)
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title="Falha ao enfileirar criacao de pasta do projeto no Google Drive",
		)


def _enqueue_project_drive_folder_cleanup(projeto_name: str) -> None:
	if not projeto_name:
		return

	try:
		frappe.enqueue(
			method="gris.api.google_workspace.project_drive.cleanup_project_folder_if_empty_async",
			queue="long",
			timeout=300,
			enqueue_after_commit=True,
			projeto_name=projeto_name,
		)
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title="Falha ao enfileirar limpeza de pasta do projeto no Google Drive",
		)


def _get_current_stage_pending_approvers(
	doc: Document, pipeline: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
	current_stage = _get_current_approval_stage(doc, pipeline)
	if not current_stage:
		return None, []

	approved_map = _get_approved_keys_by_stage(doc)
	stage_key = current_stage.get("key") or ""
	approved_keys = approved_map.get(stage_key, set())

	pending: list[dict[str, Any]] = []
	for approver in current_stage.get("approvers") or []:
		approver_key = (approver.get("key") or "").strip()
		if approver_key and approver_key in approved_keys:
			continue
		pending.append(approver)

	return current_stage, pending


def _get_coordinator_notification_contact(doc: Document) -> dict[str, str] | None:
	coordenador_row = _get_coordenador_envolvido(doc)
	coordenador = (coordenador_row or {}).get("associado") or ""
	if not coordenador:
		return None

	payload = _get_associado_payload_loose(coordenador)
	telefone = (payload.get("telefone") or "").strip()
	if not telefone:
		return None
	nome = (payload.get("nome") or coordenador).strip()
	primeiro_nome = _get_first_name(nome, fallback=coordenador)

	return {
		"nome": primeiro_nome,
		"telefone": telefone,
	}


def _build_reviewers_phone_map(reviewers: list[dict[str, str]] | None) -> dict[tuple[str, str], str]:
	phone_map: dict[tuple[str, str], str] = {}

	for reviewer in reviewers or []:
		nome = (reviewer.get("nome") or "").strip().lower()
		email = (reviewer.get("email") or "").strip().lower()
		telefone = (reviewer.get("telefone") or "").strip()
		if not telefone:
			continue

		if email:
			phone_map[("email", email)] = telefone
		if nome and ("nome", nome) not in phone_map:
			phone_map[("nome", nome)] = telefone

	return phone_map


def _get_first_name(nome_completo: str, fallback: str = "") -> str:
	nome = (nome_completo or "").strip()
	if not nome:
		return (fallback or "").strip()
	return nome.split()[0]


def _build_approval_request_description(primeiro_nome: str, projeto_titulo: str, etapa_label: str) -> str:
	return (
		f"Oi, {primeiro_nome}!\n\n"
		"Um novo projeto foi enviado para aprovação e sua aprovação foi solicitada.\n\n"
		f"*Projeto*: {projeto_titulo}\n"
		f"*Etapa*: {etapa_label}"
	)


def enviar_notificacao_whatsapp_entrada_aprovacao(projeto_name: str) -> None:
	if not projeto_name:
		return

	doc = frappe.get_doc("Projeto", projeto_name)
	if doc.get("status") != STATUS_EM_APROVACAO:
		return

	pipeline = _build_approval_pipeline(doc)
	current_stage, pending_approvers = _get_current_stage_pending_approvers(doc, pipeline)
	if not current_stage or not pending_approvers:
		return

	projeto_titulo = (doc.get("nome_do_projeto") or "").strip() or doc.name
	link = _build_project_portal_link("/projetos/aprovacao_projeto", doc.name)
	etapa_label = (current_stage.get("label") or "").strip() or _("Etapa atual")

	for approver in pending_approvers:
		numero = (approver.get("telefone") or "").strip()
		if not numero:
			continue

		nome = (
			approver.get("nome") or approver.get("associado") or approver.get("responsavel") or ""
		).strip() or _("Aprovador")
		primeiro_nome = _get_first_name(nome, fallback=str(_("Aprovador")))
		descricao = _build_approval_request_description(primeiro_nome, projeto_titulo, etapa_label)
		_send_whatsapp_project_button_notification(
			numero,
			titulo="*Aprovacao de Projeto*",
			descricao=descricao,
			link=link,
			contexto=f"entrada_aprovacao:{doc.name}",
		)


def enviar_notificacao_whatsapp_avanco_etapa_aprovacao(projeto_name: str) -> None:
	if not projeto_name:
		return

	doc = frappe.get_doc("Projeto", projeto_name)
	if doc.get("status") != STATUS_EM_APROVACAO:
		return

	pipeline = _build_approval_pipeline(doc)
	current_stage, pending_approvers = _get_current_stage_pending_approvers(doc, pipeline)
	if not current_stage or not pending_approvers:
		return

	projeto_titulo = (doc.get("nome_do_projeto") or "").strip() or doc.name
	link = _build_project_portal_link("/projetos/aprovacao_projeto", doc.name)
	etapa_label = (current_stage.get("label") or "").strip() or _("Etapa atual")

	for approver in pending_approvers:
		numero = (approver.get("telefone") or "").strip()
		if not numero:
			continue

		nome = (
			approver.get("nome") or approver.get("associado") or approver.get("responsavel") or ""
		).strip() or _("Aprovador")
		primeiro_nome = _get_first_name(nome, fallback=str(_("Aprovador")))
		descricao = _build_approval_request_description(primeiro_nome, projeto_titulo, etapa_label)
		_send_whatsapp_project_button_notification(
			numero,
			titulo="*Sua aprovação foi solicitada*",
			descricao=descricao,
			link=link,
			contexto=f"avanco_etapa_aprovacao:{doc.name}",
		)


def enviar_notificacao_whatsapp_projeto_aprovado(projeto_name: str) -> None:
	if not projeto_name:
		return

	doc = frappe.get_doc("Projeto", projeto_name)
	contact = _get_coordinator_notification_contact(doc)
	if not contact:
		return

	projeto_titulo = (doc.get("nome_do_projeto") or "").strip() or doc.name
	link = _build_project_portal_link("/projetos/projeto_aprovado", doc.name)
	mensagem = (
		f"Oi, {contact['nome']}!\n\nO projeto *{projeto_titulo}* foi aprovado.\n\nAcesse os detalhes: {link}"
	)
	_send_whatsapp_notification(contact["telefone"], mensagem, contexto=f"projeto_aprovado:{doc.name}")


def enviar_notificacao_whatsapp_alteracoes_solicitadas(projeto_name: str, comentarios: str = "") -> None:
	if not projeto_name:
		return

	doc = frappe.get_doc("Projeto", projeto_name)
	contact = _get_coordinator_notification_contact(doc)
	if not contact:
		return

	projeto_titulo = (doc.get("nome_do_projeto") or "").strip() or doc.name
	comentarios_resumo = " ".join((comentarios or "").strip().split())
	if len(comentarios_resumo) > 180:
		comentarios_resumo = f"{comentarios_resumo[:177]}..."

	link = _build_project_portal_link("/projetos/cadastrar_novo_projeto", doc.name)
	mensagem = (
		f"Ola, {contact['nome']}!\n\n"
		f'Foram solicitadas alteracoes no projeto "{projeto_titulo}".\n'
		f"Comentario: {comentarios_resumo or '-'}\n\n"
		f"Acesse o projeto: {link}"
	)
	_send_whatsapp_notification(
		contact["telefone"],
		mensagem,
		contexto=f"alteracoes_solicitadas:{doc.name}",
	)


def enviar_lembretes_whatsapp_aprovacao_projetos() -> None:
	logger = frappe.logger("projetos_whatsapp", allow_site=True)
	projetos = frappe.get_all(
		"Projeto",
		filters={"status": STATUS_EM_APROVACAO},
		fields=["name"],
		limit_page_length=500,
	)
	if not projetos:
		return

	total_enviadas = 0
	for row in projetos:
		projeto_name = (row.get("name") or "").strip()
		if not projeto_name:
			continue

		try:
			doc = frappe.get_doc("Projeto", projeto_name)
			pipeline = _build_approval_pipeline(doc)
			current_stage, pending_approvers = _get_current_stage_pending_approvers(doc, pipeline)
			if not current_stage or not pending_approvers:
				continue

			projeto_titulo = (doc.get("nome_do_projeto") or "").strip() or doc.name
			etapa_label = (current_stage.get("label") or "").strip() or _("Etapa atual")
			link = _build_project_portal_link("/projetos/aprovacao_projeto", doc.name)

			for approver in pending_approvers:
				numero = (approver.get("telefone") or "").strip()
				if not numero:
					continue

				nome = (
					approver.get("nome") or approver.get("associado") or approver.get("responsavel") or ""
				).strip() or _("Aprovador")
				primeiro_nome = _get_first_name(nome, fallback=str(_("Aprovador")))
				descricao = (
					f"Oi, {primeiro_nome}!\n\n"
					f"Lembrete diário de aprovação pendente.\n"
					f"Projeto: {projeto_titulo}\n"
					f"Etapa atual: {etapa_label}"
				)
				if _send_whatsapp_project_button_notification(
					numero,
					titulo="*Lembrete de Aprovação*",
					descricao=descricao,
					link=link,
					contexto=f"lembrete_aprovacao:{doc.name}",
				):
					total_enviadas += 1
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Falha no lembrete de aprovacao via WhatsApp ({projeto_name})",
			)

	logger.info(f"Lembretes de aprovacao enviados via WhatsApp: {total_enviadas}")


def _require_authenticated_user() -> str:
	if frappe.session.user == "Guest":
		frappe.throw(_("Você precisa estar logado para executar esta ação."), frappe.PermissionError)
	return frappe.session.user


def _has_any_project_role(user: str) -> bool:
	roles = set(frappe.get_roles(user))
	return bool({"Editor de projetos", "Visualizador de projetos", "System Manager"} & roles)


def _require_project_read_access() -> str:
	user = _require_authenticated_user()
	if not _has_any_project_role(user):
		frappe.throw(_("Você não possui acesso ao módulo de projetos."), frappe.PermissionError)
	return user


def _require_project_editor_access() -> str:
	user = _require_project_read_access()
	roles = set(frappe.get_roles(user))
	if "System Manager" in roles:
		return user
	if "Editor de projetos" not in roles:
		frappe.throw(
			_("Somente usuários com perfil Editor de projetos podem alterar projetos."),
			frappe.PermissionError,
		)
	return user


def _is_user_active_in_gris(user: str) -> bool:
	if not user or user == "Guest":
		return False

	enabled = frappe.db.get_value("User", user, "enabled")
	return cint(enabled) == 1


def _is_user_involved_in_project(user: str, doc: Document) -> bool:
	user_key = (user or "").strip().lower()
	if not user_key:
		return False

	associado_names = {
		(row.get("name") or "").strip()
		for row in _get_user_associados(user)
		if (row.get("name") or "").strip()
	}
	responsavel_names = {
		(row.get("name") or "").strip()
		for row in _get_user_responsaveis(user)
		if (row.get("name") or "").strip()
	}

	for row in _get_normalized_envolvidos(doc, strict=False, include_legacy=True):
		tipo = (row.get("tipo_pessoa") or "").strip()
		if tipo == APPROVER_TYPE_ASSOCIADO and (row.get("associado") or "").strip() in associado_names:
			return True
		if tipo == APPROVER_TYPE_RESPONSAVEL and (row.get("responsavel") or "").strip() in responsavel_names:
			return True

		row_email = (row.get("email") or "").strip().lower()
		if row_email and row_email == user_key:
			return True

	return False


def _can_user_edit_project_execution_context(user: str, doc: Document) -> bool:
	roles = set(frappe.get_roles(user))
	if "Editor de projetos" not in roles and "System Manager" not in roles:
		return False

	if not _is_user_active_in_gris(user):
		return False

	return _is_user_involved_in_project(user, doc)


def _require_project_execution_edit_access(doc: Document, *, user: str | None = None) -> str:
	user = user or _require_project_editor_access()

	if not _is_user_active_in_gris(user):
		frappe.throw(
			_("Somente usuários ativos no GRIS podem editar projetos."),
			frappe.PermissionError,
		)

	if not _is_user_involved_in_project(user, doc):
		frappe.throw(
			_("Somente envolvidos neste projeto podem editar os dados desta página."),
			frappe.PermissionError,
		)

	return user


def _parse_payload(payload: str | dict[str, Any] | None) -> dict[str, Any]:
	if payload is None:
		return {}
	if isinstance(payload, dict):
		return payload
	if isinstance(payload, str):
		if not payload.strip():
			return {}
		try:
			parsed = json.loads(payload)
		except json.JSONDecodeError as exc:
			frappe.throw(_("Payload inválido para cadastro de projeto."))
			raise exc
		if not isinstance(parsed, dict):
			frappe.throw(_("Payload inválido para cadastro de projeto."))
		return parsed
	frappe.throw(_("Payload inválido para cadastro de projeto."))
	return {}


def _clean_value(value: Any) -> Any:
	if isinstance(value, str):
		return value.strip()
	return value


def _sanitize_rows(rows: Any, allowed_fields: list[str]) -> list[dict[str, Any]]:
	if not isinstance(rows, list):
		return []

	cleaned: list[dict[str, Any]] = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		candidate = {key: _clean_value(row.get(key)) for key in allowed_fields}
		if any(candidate.get(key) not in (None, "", []) for key in allowed_fields):
			cleaned.append(candidate)
	return cleaned


def _normalize_equipe_tipo_pessoa(value: Any) -> str:
	raw = (value or "").strip() if isinstance(value, str) else ""
	if raw in {"Associado", "Responsavel", "Outro"}:
		return raw
	if raw.lower() == "nome livre":
		return "Outro"
	return raw or "Outro"


def _apply_portal_payload(doc: Document, data: dict[str, Any]) -> None:
	for fieldname in SIMPLE_FORM_FIELDS:
		if fieldname in data and _doc_has_field(doc, fieldname):
			doc.set(fieldname, _clean_value(data.get(fieldname)))

	for table_field, row_fields in TABLE_FIELD_MAP.items():
		if table_field == "envolvidos":
			continue
		if table_field not in data:
			continue
		if not _doc_has_field(doc, table_field):
			continue
		rows = _sanitize_rows(data.get(table_field), row_fields)
		doc.set(table_field, [])
		for row in rows:
			doc.append(table_field, row)

	normalized_envolvidos: list[dict[str, Any]] = []
	if "envolvidos" in data:
		raw_rows = _sanitize_rows(data.get("envolvidos"), TABLE_FIELD_MAP["envolvidos"])
		normalized_envolvidos = [
			normalized
			for normalized in (_normalize_envolvido_row(row, strict=False) for row in raw_rows)
			if normalized
		]
		normalized_envolvidos = _merge_duplicate_envolvidos(normalized_envolvidos)
	else:
		normalized_envolvidos = _build_envolvidos_from_legacy(doc)

	_set_doc_envolvidos(doc, normalized_envolvidos)
	_sync_legacy_people_from_envolvidos(doc, normalized_envolvidos)


def _assert_required_simple_fields(doc: Document) -> None:
	_sync_legacy_people_from_envolvidos(
		doc,
		_get_normalized_envolvidos(doc, strict=False, include_legacy=True),
	)

	required_fields = {
		"nome_do_projeto": _("Título do projeto"),
		"coordenador": _("Coordenador"),
		"tipo_padrinho_ou_orientador": _("Tipo do padrinho ou orientador"),
		"justificativa": _("Justificativa"),
		"alinhamento_com_escotismo": _("Alinhamento com o escotismo"),
	}

	for fieldname, label in required_fields.items():
		if not doc.get(fieldname):
			frappe.throw(_("O campo {0} é obrigatório para submeter o projeto.").format(label))

	tipo = (doc.get("tipo_padrinho_ou_orientador") or "").strip()
	if tipo == "Associado" and not doc.get("padrinho_associado"):
		frappe.throw(_("Selecione o padrinho associado para submeter o projeto."))
	if tipo == "Responsavel" and not doc.get("padrinho_responsavel"):
		frappe.throw(_("Selecione o padrinho responsável para submeter o projeto."))


def _assert_required_tables(doc: Document) -> None:
	envolvidos = _get_normalized_envolvidos(doc, strict=False, include_legacy=True)
	_sync_legacy_people_from_envolvidos(doc, envolvidos)

	table_required = {
		"objetivos": _("Objetivos"),
		"ods": _("ODS"),
		"cronograma": _("Cronograma"),
		"recursos": _("Recursos"),
		"riscos": _("Riscos"),
	}

	participantes = [
		row for row in envolvidos if not cint(row.get("aprovador")) and not cint(row.get("coordenador"))
	]
	if not participantes:
		frappe.throw(
			_("Preencha ao menos uma linha em {0} para submeter o projeto.").format(_("Equipe de interesse"))
		)

	for fieldname, label in table_required.items():
		if not doc.get(fieldname):
			frappe.throw(_("Preencha ao menos uma linha em {0} para submeter o projeto.").format(label))

	for idx, row in enumerate(participantes, start=1):
		tipo = (row.get("tipo_pessoa") or "").strip()
		if not tipo:
			frappe.throw(_("Informe o tipo de pessoa na equipe de interesse (linha {0}).").format(idx))
		if tipo == "Associado" and not row.get("associado"):
			frappe.throw(_("Selecione o associado na equipe de interesse (linha {0}).").format(idx))
		if tipo == "Responsavel" and not row.get("responsavel"):
			frappe.throw(_("Selecione o responsável na equipe de interesse (linha {0}).").format(idx))
		if tipo == "Outro":
			if not row.get("nome") or not row.get("email") or not row.get("telefone"):
				frappe.throw(
					_(
						"Para Outro na equipe de interesse (linha {0}), preencha nome, email e telefone."
					).format(idx)
				)

	for idx, row in enumerate(doc.get("objetivos") or [], start=1):
		if not row.get("objetivo") or not row.get("metrica_de_sucesso"):
			frappe.throw(_("Cada objetivo deve ter objetivo e métrica de sucesso (linha {0}).").format(idx))

	for idx, row in enumerate(doc.get("ods") or [], start=1):
		if not row.get("ods"):
			frappe.throw(_("Cada linha de ODS deve informar o ODS selecionado (linha {0}).").format(idx))

	for idx, row in enumerate(doc.get("cronograma") or [], start=1):
		if not row.get("data_inicio") or not row.get("data_termino") or not row.get("tarefa"):
			frappe.throw(
				_("Cada linha do cronograma deve ter data inicial, data final e tarefa (linha {0}).").format(
					idx
				)
			)

	for idx, row in enumerate(doc.get("recursos") or [], start=1):
		if not row.get("recurso"):
			frappe.throw(_("Cada linha de recursos deve ter conteúdo (linha {0}).").format(idx))

	for idx, row in enumerate(doc.get("riscos") or [], start=1):
		if not row.get("risco") or not row.get("mitigacao"):
			frappe.throw(_("Cada linha de riscos deve ter risco e mitigação (linha {0}).").format(idx))


def _assert_aprovadores_rules(doc: Document) -> None:
	aprovadores = _get_effective_aprovadores(doc, strict=True)
	if not aprovadores:
		frappe.throw(_("Configure ao menos um aprovador para submeter o projeto."))

	keys = [row.get("key") for row in aprovadores if row.get("key")]
	keys_set = set(keys)
	if len(keys) != len(keys_set):
		frappe.throw(_("Existem aprovadores duplicados. Ajuste a lista de aprovadores antes de submeter."))

	sponsor = _get_sponsor_approver_identity(doc, strict=True)
	if sponsor and sponsor.get("key") not in keys_set:
		frappe.throw(
			_(
				"O padrinho/orientador selecionado precisa constar na lista de aprovadores e não pode ser removido."
			)
		)

	section_chief_rows = _get_section_chief_approver_identities(doc, strict=True)
	missing_section_chief = [row for row in section_chief_rows if (row.get("key") or "") not in keys_set]
	if missing_section_chief:
		frappe.throw(
			_("O chefe de seção do coordenador jovem é aprovador obrigatório e não pode ser removido.")
		)

	aprovadores_iniciais = [
		row
		for row in aprovadores
		if row.get("origem_regra") in {APPROVER_ORIGIN_PADRINHO, APPROVER_ORIGIN_MANUAL}
	]
	if not aprovadores_iniciais:
		frappe.throw(
			_("A etapa inicial precisa ter ao menos um aprovador (padrinho/orientador ou outro aprovador).")
		)


def _assert_submit_rules(doc: Document) -> None:
	_assert_required_simple_fields(doc)
	_assert_required_tables(doc)
	_assert_aprovadores_rules(doc)
	_assert_no_pending_review_comments(doc)
	_assert_approval_pipeline_ready(doc)


def _serialize_table_rows(rows: list[Document], fields: list[str]) -> list[dict[str, Any]]:
	serialized: list[dict[str, Any]] = []
	for row in rows or []:
		serialized.append({fieldname: row.get(fieldname) for fieldname in fields})
	return serialized


def _serialize_tarefas(rows: list[Document]) -> list[dict[str, Any]]:
	serialized: list[dict[str, Any]] = []
	for row in rows or []:
		payload = {
			"name": row.get("name"),
			"idx": row.get("idx"),
		}
		for fieldname in TASK_FIELDS:
			payload[fieldname] = row.get(fieldname)
		serialized.append(payload)
	return serialized


def _serialize_reunioes(rows: list[Document]) -> list[dict[str, Any]]:
	serialized: list[dict[str, Any]] = []
	for row in rows or []:
		payload = {
			"name": row.get("name"),
			"idx": row.get("idx"),
		}
		for fieldname in MEETING_FIELDS:
			payload[fieldname] = row.get(fieldname)
		serialized.append(payload)
	return serialized


def _get_responsavel_options(doc: Document) -> list[str]:
	options = {
		(row.get("nome") or "").strip()
		for row in _get_normalized_envolvidos(doc, strict=False, include_legacy=True)
		if (row.get("nome") or "").strip()
	}
	return sorted(options)


def _assert_project_in_execution(doc: Document) -> None:
	if doc.get("status") != STATUS_EM_EXECUCAO:
		frappe.throw(_("Somente projetos em execução podem ser alterados nesta página."))


def _assert_project_visible_on_execution_page(doc: Document) -> None:
	if doc.get("status") not in STATUS_EXECUCAO_PAGE_ALLOWED:
		frappe.throw(
			_("Somente projetos em execução, concluídos ou cancelados podem ser exibidos nesta página.")
		)


def _assert_project_can_be_cancelled(doc: Document) -> None:
	if doc.get("status") not in {STATUS_EM_APROVACAO, STATUS_APROVADO, STATUS_EM_EXECUCAO}:
		frappe.throw(_("Somente projetos em aprovação, aprovados ou em execução podem ser cancelados."))


def _find_child_row(rows: list[Document], row_name: str) -> Document | None:
	for row in rows or []:
		if row.get("name") == row_name:
			return row
	return None


def _get_task_row_from_project(doc: Document, tarefa_name: str) -> Document:
	tarefa_name = (tarefa_name or "").strip()
	if not tarefa_name:
		frappe.throw(_("Tarefa não informada."))

	target_row = _find_child_row(doc.get("tarefas") or [], tarefa_name)
	if not target_row:
		frappe.throw(_("Tarefa não encontrada no projeto."))

	return target_row


def _get_task_comment_from_row(tarefa_row: Document, comentario_name: str) -> Document:
	comentario_name = (comentario_name or "").strip()
	if not comentario_name:
		frappe.throw(_("Comentário não informado."))

	comment_doc = frappe.get_doc("Comment", comentario_name)
	if (
		(comment_doc.get("comment_type") or "") != "Comment"
		or (comment_doc.get("reference_doctype") or "") != "Gestao de Tarefas"
		or (comment_doc.get("reference_name") or "") != (tarefa_row.get("name") or "")
	):
		frappe.throw(_("Comentário não encontrado para a tarefa informada."))

	return comment_doc


def _assert_comment_author(comment_doc: Document, user: str) -> None:
	comment_owner = (comment_doc.get("owner") or comment_doc.get("comment_email") or "").strip()
	if not comment_owner or comment_owner.lower() != (user or "").strip().lower():
		frappe.throw(
			_("Somente o autor do comentário pode editar ou apagar este comentário."),
			frappe.PermissionError,
		)


def _serialize_tarefa_comentarios(tarefa_name: str) -> list[dict[str, Any]]:
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
		comment_owner = (row.get("owner") or owner_email).strip()
		author = (row.get("comment_by") or "").strip() or (get_fullname(owner_email) if owner_email else "")
		serialized.append(
			{
				"name": row.get("name"),
				"content": row.get("content") or "",
				"content_text": strip_html(
					(row.get("content") or "").replace("</p>", "\n").replace("<br>", "\n")
				),
				"author": author or owner_email or _("Usuário"),
				"author_email": owner_email,
				"owner": comment_owner,
				"creation": row.get("creation"),
			}
		)

	return serialized


def _assert_task_payload(payload: dict[str, Any], team_names: set[str]) -> dict[str, Any]:
	if not payload.get("descricao"):
		frappe.throw(_("Informe a descrição da tarefa."))
	if not payload.get("prazo"):
		frappe.throw(_("Informe o prazo da tarefa."))

	payload["status"] = payload.get("status") or "Nao iniciado"
	if payload["status"] not in TASK_STATUS_OPTIONS:
		frappe.throw(_("Status da tarefa inválido."))

	responsavel = (payload.get("responsavel") or "").strip()
	if responsavel and responsavel not in team_names:
		frappe.throw(_("Responsável da tarefa deve existir entre os envolvidos do projeto."))

	if payload.get("data_inicio") and payload.get("prazo"):
		if getdate(payload["data_inicio"]) > getdate(payload["prazo"]):
			frappe.throw(_("Data de início da tarefa não pode ser maior que o prazo."))

	return payload


def _normalize_task_delivery_date(payload: dict[str, Any]) -> dict[str, Any]:
	status = (payload.get("status") or "").strip()
	raw_data_entrega = payload.get("data_entrega")
	data_entrega = raw_data_entrega.strip() if isinstance(raw_data_entrega, str) else raw_data_entrega

	if status == "Concluido":
		payload["data_entrega"] = data_entrega or nowdate()
		return payload

	payload["data_entrega"] = ""
	return payload


def _normalize_task_start_date(payload: dict[str, Any], previous_status: str | None = None) -> dict[str, Any]:
	status = (payload.get("status") or "").strip()
	last_status = (previous_status or "").strip()
	raw_data_inicio = payload.get("data_inicio")
	data_inicio = raw_data_inicio.strip() if isinstance(raw_data_inicio, str) else raw_data_inicio

	if status != "Nao iniciado" and not data_inicio and (not last_status or last_status == "Nao iniciado"):
		payload["data_inicio"] = nowdate()
		return payload

	payload["data_inicio"] = data_inicio
	return payload


def _assert_meeting_payload(payload: dict[str, Any]) -> dict[str, Any]:
	if not payload.get("data_hora"):
		frappe.throw(_("Informe a data e hora da reunião."))
	if not payload.get("descricao"):
		frappe.throw(_("Informe a descrição da reunião."))

	try:
		get_datetime(payload["data_hora"])
	except Exception:
		frappe.throw(_("Data e hora da reunião inválida."))

	return payload


def _get_doc_display_name(doctype_name: str, docname: str | None, fieldname: str = "nome_completo") -> str:
	if not docname:
		return ""
	value = frappe.db.get_value(doctype_name, docname, fieldname)
	return str(value or docname)


def _serialize_envolvidos(doc: Document) -> list[dict[str, Any]]:
	rows = _get_normalized_envolvidos(doc, strict=False, include_legacy=True)
	return [
		{
			"tipo_pessoa": row.get("tipo_pessoa") or "Outro",
			"associado": row.get("associado") or "",
			"responsavel": row.get("responsavel") or "",
			"nome": row.get("nome") or "",
			"email": row.get("email") or "",
			"telefone": row.get("telefone") or "",
			"funcao": row.get("funcao") or "",
			"coordenador": 1 if cint(row.get("coordenador")) else 0,
			"padrinho_orientador": 1 if cint(row.get("padrinho_orientador")) else 0,
			"aprovador": 1 if cint(row.get("aprovador")) else 0,
			"origem_regra_aprovador": row.get("origem_regra_aprovador") or "",
			"permite_remover": 1 if cint(row.get("permite_remover")) else 0,
			"participa_avaliacao": 1 if cint(row.get("participa_avaliacao")) else 0,
		}
		for row in rows
	]


def _serialize_projeto(doc: Document) -> dict[str, Any]:
	envolvidos = _serialize_envolvidos(doc)
	coordenador_row = next((row for row in envolvidos if cint(row.get("coordenador"))), None)
	padrinho_row = next((row for row in envolvidos if cint(row.get("padrinho_orientador"))), None)

	coordenador = (coordenador_row or {}).get("associado") or (doc.get("coordenador") or "")
	coordenador_label = (coordenador_row or {}).get("nome") or _get_doc_display_name("Associado", coordenador)

	padrinho_tipo = (padrinho_row or {}).get("tipo_pessoa") or (doc.get("tipo_padrinho_ou_orientador") or "")
	padrinho_associado = (padrinho_row or {}).get("associado") or (doc.get("padrinho_associado") or "")
	padrinho_responsavel = (padrinho_row or {}).get("responsavel") or (doc.get("padrinho_responsavel") or "")
	padrinho_nome = (padrinho_row or {}).get("nome") or ""
	if not padrinho_nome and padrinho_associado:
		padrinho_nome = _get_doc_display_name("Associado", padrinho_associado)
	if not padrinho_nome and padrinho_responsavel:
		padrinho_nome = _get_doc_display_name("Responsavel", padrinho_responsavel)

	equipe_de_interesse = [row for row in envolvidos if not cint(row.get("aprovador"))]

	return {
		"name": doc.name,
		"status": doc.status,
		"nome_do_projeto": doc.nome_do_projeto,
		"link_pasta_google_drive": doc.get("link_pasta_google_drive") or "",
		"coordenador": coordenador,
		"coordenador_label": coordenador_label,
		"data_de_inicio": doc.data_de_inicio,
		"data_de_termino": doc.data_de_termino,
		"tipo_padrinho_ou_orientador": padrinho_tipo,
		"padrinho_associado": padrinho_associado,
		"padrinho_responsavel": padrinho_responsavel,
		"padrinho_nome": padrinho_nome,
		"justificativa": doc.justificativa,
		"alinhamento_com_escotismo": doc.alinhamento_com_escotismo,
		"competencias": doc.competencias,
		"especialidade": doc.especialidade,
		"observacoes_e_comentarios": doc.observacoes_e_comentarios,
		"avaliacao_tap": doc.avaliacao_tap,
		"comentarios_revisao_aprovacao": _serialize_review_rows(
			doc.get("comentarios_revisao_aprovacao") or []
		),
		"pendencias_revisao": len(_get_pending_review_comments(doc)),
		"envolvidos": envolvidos,
		"equipe_de_interesse": equipe_de_interesse,
		"aprovadores": [
			_to_aprovador_child_payload(row) for row in _get_effective_aprovadores(doc, strict=False)
		],
		"objetivos": _serialize_table_rows(doc.get("objetivos"), TABLE_FIELD_MAP["objetivos"]),
		"ods": _serialize_table_rows(doc.get("ods"), TABLE_FIELD_MAP["ods"]),
		"cronograma": _serialize_table_rows(doc.get("cronograma"), TABLE_FIELD_MAP["cronograma"]),
		"tarefas": _serialize_tarefas(doc.get("tarefas") or []),
		"reunioes": _serialize_reunioes(doc.get("reunioes") or []),
		"recursos": _serialize_table_rows(doc.get("recursos"), TABLE_FIELD_MAP["recursos"]),
		"riscos": _serialize_table_rows(doc.get("riscos"), TABLE_FIELD_MAP["riscos"]),
	}


def _get_selection_options() -> dict[str, list[dict[str, str]]]:
	associados = frappe.get_all(
		"Associado",
		fields=["name", "nome_completo", "categoria"],
		order_by="nome_completo asc",
		limit_page_length=500,
	)
	associados_padrinho = [row for row in associados if not _is_beneficiario_categoria(row.get("categoria"))]
	responsaveis = frappe.get_all(
		"Responsavel",
		fields=["name", "nome_completo"],
		order_by="nome_completo asc",
		limit_page_length=500,
	)
	ods = frappe.get_all(
		"ODS Projeto",
		fields=["name", "codigo", "titulo"],
		order_by="codigo asc",
		limit_page_length=200,
	)

	return {
		"associados": [
			{"value": row.get("name"), "label": row.get("nome_completo") or row.get("name")}
			for row in associados
		],
		"associados_padrinho": [
			{"value": row.get("name"), "label": row.get("nome_completo") or row.get("name")}
			for row in associados_padrinho
		],
		"responsaveis": [
			{"value": row.get("name"), "label": row.get("nome_completo") or row.get("name")}
			for row in responsaveis
		],
		"ods": [
			{
				"value": row.get("name"),
				"label": f"{row.get('codigo') or row.get('name')} - {row.get('titulo') or ''}".strip(" -"),
			}
			for row in ods
		],
	}


@frappe.whitelist()
def get_projeto_form_data(projeto_name: str | None = None) -> dict[str, Any]:
	user = _require_project_read_access()
	project_data = None
	default_aprovadores: list[dict[str, Any]] = []
	is_coordinator = False

	if projeto_name:
		doc = frappe.get_doc("Projeto", projeto_name)
		if not doc.has_permission("read"):
			frappe.throw(_("Você não tem permissão para visualizar este projeto."), frappe.PermissionError)
		_bootstrap_aprovadores_if_empty(doc)
		_sync_sponsor_approver(doc)
		project_data = _serialize_projeto(doc)
		is_coordinator = _is_user_coordinator(user, doc)
	else:
		temp_doc = frappe.new_doc("Projeto")
		default_aprovadores = [
			_to_aprovador_child_payload(row) for row in _build_default_aprovadores(temp_doc, strict=False)
		]

	return {
		"choices": _get_selection_options(),
		"projeto": project_data,
		"default_aprovadores": default_aprovadores,
		"is_coordinator": is_coordinator,
	}


@frappe.whitelist()
def get_aprovadores_obrigatorios_preview(payload: str | dict[str, Any] | None = None) -> dict[str, Any]:
	_require_project_read_access()
	data = _parse_payload(payload)

	temp_doc = frappe.new_doc("Projeto")
	for fieldname in (
		"coordenador",
		"tipo_padrinho_ou_orientador",
		"padrinho_associado",
		"padrinho_responsavel",
	):
		temp_doc.set(fieldname, _clean_value(data.get(fieldname)))

	mandatory_aprovadores = [
		_to_aprovador_child_payload(row) for row in _get_mandatory_aprovadores(temp_doc, strict=False)
	]

	return {
		"mandatory_aprovadores": mandatory_aprovadores,
	}


@frappe.whitelist()
def salvar_rascunho_projeto(payload: str | dict[str, Any], projeto_name: str | None = None) -> dict[str, Any]:
	_require_project_editor_access()
	data = _parse_payload(payload)

	if projeto_name:
		doc = frappe.get_doc("Projeto", projeto_name)
		if not doc.has_permission("write"):
			frappe.throw(_("Você não tem permissão para editar este projeto."), frappe.PermissionError)
	else:
		if not frappe.has_permission("Projeto", "create"):
			frappe.throw(_("Você não tem permissão para criar projetos."), frappe.PermissionError)
		doc = frappe.new_doc("Projeto")

	_apply_portal_payload(doc, data)
	_bootstrap_aprovadores_if_empty(doc)
	_sync_sponsor_approver(doc)

	if not doc.get("nome_do_projeto"):
		frappe.throw(_("Informe o título do projeto para salvar o rascunho."))
	if not doc.get("coordenador"):
		frappe.throw(_("Informe o coordenador para salvar o rascunho."))

	doc.status = "Rascunho"
	doc.flags.portal_draft_save = True
	doc.save()

	return {
		"ok": True,
		"name": doc.name,
		"status": doc.status,
	}


@frappe.whitelist()
def submeter_projeto(payload: str | dict[str, Any], projeto_name: str | None = None) -> dict[str, Any]:
	_require_project_editor_access()
	data = _parse_payload(payload)

	if projeto_name:
		doc = frappe.get_doc("Projeto", projeto_name)
		if not doc.has_permission("write"):
			frappe.throw(_("Você não tem permissão para editar este projeto."), frappe.PermissionError)
	else:
		if not frappe.has_permission("Projeto", "create"):
			frappe.throw(_("Você não tem permissão para criar projetos."), frappe.PermissionError)
		doc = frappe.new_doc("Projeto")

	_apply_portal_payload(doc, data)
	_bootstrap_aprovadores_if_empty(doc)
	_sync_sponsor_approver(doc)
	_assert_submit_rules(doc)
	_clear_approval_rows(doc)

	doc.status = STATUS_EM_APROVACAO
	doc.flags.portal_draft_save = False
	doc.save()
	_enqueue_project_whatsapp_job(
		"gris.gestao_de_projetos.doctype.projeto.projeto.enviar_notificacao_whatsapp_entrada_aprovacao",
		projeto_name=doc.name,
	)

	return {
		"ok": True,
		"name": doc.name,
		"status": doc.status,
	}


@frappe.whitelist()
def get_projeto_aprovacao_data(projeto_name: str) -> dict[str, Any]:
	user = _require_project_read_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado para aprovação."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("read"):
		frappe.throw(_("Você não tem permissão para visualizar este projeto."), frappe.PermissionError)

	return {
		"projeto": _serialize_projeto(doc),
		"approval": _serialize_pipeline(doc, user),
	}


@frappe.whitelist()
def aprovar_projeto_etapa(projeto_name: str) -> dict[str, Any]:
	user = _require_project_read_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado para aprovação."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("read"):
		frappe.throw(_("Você não tem permissão para aprovar este projeto."), frappe.PermissionError)
	if doc.get("status") != STATUS_EM_APROVACAO:
		frappe.throw(_("Somente projetos em aprovação podem receber decisão de aprovação."))

	pipeline = _build_approval_pipeline(doc)
	current_stage = _get_current_approval_stage(doc, pipeline)
	if not current_stage:
		frappe.throw(_("Este projeto já concluiu todas as etapas de aprovação."))

	stage_approver = _get_stage_user_approver(user, current_stage)
	if not stage_approver:
		frappe.throw(_("Você não é aprovador elegível para a etapa atual."), frappe.PermissionError)

	approved_map = _get_approved_keys_by_stage(doc)
	stage_key = current_stage.get("key") or ""
	if (stage_approver.get("key") or "") in approved_map.get(stage_key, set()):
		frappe.throw(_("Você já aprovou esta etapa."))

	_append_review_row(
		doc,
		aprovador=stage_approver,
		tipo_revisao=REVIEW_TYPE_APROVACAO,
		etapa_key=stage_key,
		comentarios=_("Etapa aprovada."),
		resolvido=1,
	)

	next_stage = _get_current_approval_stage(doc, pipeline)
	has_stage_advanced = bool(next_stage and (next_stage.get("key") or "") != stage_key)
	is_final_approval = not next_stage
	if not next_stage:
		doc.status = STATUS_APROVADO

	# A autorização é determinada pela elegibilidade da etapa atual, não por permissão de write do DocType.
	doc.save(ignore_permissions=True)
	if is_final_approval:
		_enqueue_project_whatsapp_job(
			"gris.gestao_de_projetos.doctype.projeto.projeto.enviar_notificacao_whatsapp_projeto_aprovado",
			projeto_name=doc.name,
		)
	elif has_stage_advanced:
		_enqueue_project_whatsapp_job(
			"gris.gestao_de_projetos.doctype.projeto.projeto.enviar_notificacao_whatsapp_avanco_etapa_aprovacao",
			projeto_name=doc.name,
		)

	return {
		"ok": True,
		"status": doc.status,
		"proximo_passo": next_stage.get("label") if next_stage else _("Projeto aprovado"),
	}


@frappe.whitelist()
def solicitar_alteracoes_projeto(projeto_name: str, comentarios: str) -> dict[str, Any]:
	user = _require_project_read_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado para revisão."))

	comentarios = (comentarios or "").strip()
	if not comentarios:
		frappe.throw(_("Informe os comentários para solicitar alterações."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("read"):
		frappe.throw(_("Você não tem permissão para revisar este projeto."), frappe.PermissionError)
	if doc.get("status") != STATUS_EM_APROVACAO:
		frappe.throw(_("Somente projetos em aprovação podem receber solicitação de alterações."))

	pipeline = _build_approval_pipeline(doc)
	current_stage = _get_current_approval_stage(doc, pipeline)
	if not current_stage:
		frappe.throw(_("Este projeto já concluiu todas as etapas de aprovação."))

	stage_approver = _get_stage_user_approver(user, current_stage)
	if not stage_approver:
		frappe.throw(_("Você não é aprovador elegível para a etapa atual."), frappe.PermissionError)

	_append_review_row(
		doc,
		aprovador=stage_approver,
		tipo_revisao=REVIEW_TYPE_AJUSTE,
		etapa_key=current_stage.get("key") or "",
		comentarios=comentarios,
		resolvido=0,
	)
	doc.status = "Rascunho"
	doc.flags.portal_draft_save = True
	# A autorização é determinada pela elegibilidade da etapa atual, não por permissão de write do DocType.
	doc.save(ignore_permissions=True)
	_enqueue_project_whatsapp_job(
		"gris.gestao_de_projetos.doctype.projeto.projeto.enviar_notificacao_whatsapp_alteracoes_solicitadas",
		projeto_name=doc.name,
		comentarios=comentarios,
	)

	return {
		"ok": True,
		"status": doc.status,
	}


@frappe.whitelist()
def iniciar_execucao_projeto(projeto_name: str) -> dict[str, Any]:
	_require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado para iniciar execução."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para iniciar este projeto."), frappe.PermissionError)

	if doc.get("status") != STATUS_APROVADO:
		frappe.throw(_("Somente projetos com status Aprovado podem ser iniciados."))

	doc.status = "Em execucao"
	doc.flags.portal_draft_save = False
	doc.save()

	return {
		"ok": True,
		"status": doc.status,
	}


@frappe.whitelist()
def concluir_projeto_execucao(projeto_name: str) -> dict[str, Any]:
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado para concluir."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para concluir este projeto."), frappe.PermissionError)

	_assert_project_in_execution(doc)

	doc.status = "Concluido"
	doc.flags.portal_draft_save = False
	doc.save()
	if (doc.get("link_pasta_google_drive") or "").strip():
		_enqueue_project_drive_folder_cleanup(doc.name)

	return {
		"ok": True,
		"status": doc.status,
	}


@frappe.whitelist()
def cancelar_projeto(projeto_name: str) -> dict[str, Any]:
	_require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado para cancelar."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para cancelar este projeto."), frappe.PermissionError)

	_assert_project_can_be_cancelled(doc)

	doc.status = "Cancelado"
	doc.flags.portal_draft_save = False
	doc.save()

	return {
		"ok": True,
		"status": doc.status,
	}


@frappe.whitelist()
def cancelar_projeto_execucao(projeto_name: str) -> dict[str, Any]:
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado para cancelar."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para cancelar este projeto."), frappe.PermissionError)

	_assert_project_can_be_cancelled(doc)

	doc.status = "Cancelado"
	doc.flags.portal_draft_save = False
	doc.save()

	return {
		"ok": True,
		"status": doc.status,
	}


@frappe.whitelist()
def resolver_comentario_revisao(projeto_name: str, comentario_name: str) -> dict[str, Any]:
	user = _require_project_editor_access()
	if not projeto_name or not comentario_name:
		frappe.throw(_("Projeto ou comentário não informado para resolução."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not _is_user_coordinator(user, doc):
		frappe.throw(_("Somente o coordenador do projeto pode resolver comentários."), frappe.PermissionError)

	target_row = None
	for row in doc.get("comentarios_revisao_aprovacao") or []:
		if row.get("name") == comentario_name:
			target_row = row
			break

	if not target_row:
		frappe.throw(_("Comentário de revisão não encontrado."))

	if (target_row.get("tipo_revisao") or "") != REVIEW_TYPE_AJUSTE:
		frappe.throw(_("Somente comentários de solicitação de alterações podem ser resolvidos."))

	target_row.resolvido = 1
	doc.save()

	return {
		"ok": True,
		"comentario_name": comentario_name,
	}


@frappe.whitelist()
def solicitar_avaliacao_tap_llm(projeto_name: str) -> dict[str, Any]:
	_require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado para avaliação por IA."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para avaliar este projeto."), frappe.PermissionError)

	frappe.db.set_value(
		"Projeto",
		projeto_name,
		"avaliacao_tap",
		AVALIACAO_EM_PROCESSAMENTO,
		update_modified=True,
	)

	frappe.enqueue(
		method="gris.api.gestao_de_projetos.avaliacao_tap_tasks.processar_avaliacao_tap",
		queue="long",
		timeout=600,
		enqueue_after_commit=True,
		projeto_name=projeto_name,
	)

	return {
		"ok": True,
		"pending": True,
		"avaliacao_tap": AVALIACAO_EM_PROCESSAMENTO,
	}


@frappe.whitelist()
def consultar_avaliacao_tap(projeto_name: str) -> dict[str, Any]:
	_require_project_read_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado para consulta da avaliação."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("read"):
		frappe.throw(_("Você não tem permissão para visualizar este projeto."), frappe.PermissionError)

	avaliacao_tap = doc.get("avaliacao_tap") or ""
	return {
		"ok": True,
		"avaliacao_tap": avaliacao_tap,
		"pending": avaliacao_tap == AVALIACAO_EM_PROCESSAMENTO,
	}


@frappe.whitelist()
def get_projeto_execucao_data(projeto_name: str) -> dict[str, Any]:
	user = _require_project_read_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("read"):
		frappe.throw(_("Você não tem permissão para visualizar este projeto."), frappe.PermissionError)

	_assert_project_visible_on_execution_page(doc)
	status = doc.get("status")
	choices = _get_selection_options()

	can_edit = _can_user_edit_project_execution_context(user, doc) and status == STATUS_EM_EXECUCAO

	return {
		"ok": True,
		"projeto": _serialize_projeto(doc),
		"responsavel_options": _get_responsavel_options(doc),
		"choices": {
			"associados": choices.get("associados") or [],
			"responsaveis": choices.get("responsaveis") or [],
		},
		"can_edit": can_edit,
	}


def _parse_envolvidos_rows_payload(
	payload: str | dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
	parsed: Any = payload
	if isinstance(payload, str):
		try:
			parsed = json.loads(payload) if payload.strip() else []
		except json.JSONDecodeError as exc:
			frappe.throw(_("Payload inválido para envolvidos do projeto."))
			raise exc

	if isinstance(parsed, dict):
		parsed = parsed.get("envolvidos")

	if not isinstance(parsed, list):
		frappe.throw(_("Payload de envolvidos deve ser uma lista de linhas."))

	return [row for row in parsed if isinstance(row, dict)]


def _make_approver_key_from_envolvido_row(row: dict[str, Any]) -> str:
	tipo = (row.get("tipo_pessoa") or "").strip()
	if tipo == APPROVER_TYPE_ASSOCIADO:
		return _make_approver_key(tipo, row.get("associado") or "")
	if tipo == APPROVER_TYPE_RESPONSAVEL:
		return _make_approver_key(tipo, row.get("responsavel") or "")
	return ""


@frappe.whitelist()
def salvar_envolvidos_projeto_execucao(
	projeto_name: str,
	envolvidos: str | dict[str, Any] | list[dict[str, Any]],
) -> dict[str, Any]:
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para editar este projeto."), frappe.PermissionError)

	_assert_project_in_execution(doc)

	raw_rows = _parse_envolvidos_rows_payload(envolvidos)
	sanitized_rows = _sanitize_rows(raw_rows, TABLE_FIELD_MAP["envolvidos"])
	incoming_rows = [
		normalized
		for normalized in (_normalize_envolvido_row(row, strict=True) for row in sanitized_rows)
		if normalized
	]
	incoming_rows = _merge_duplicate_envolvidos(incoming_rows)

	if not incoming_rows:
		frappe.throw(_("Informe ao menos um envolvido para o projeto."))

	coordenadores = [row for row in incoming_rows if cint(row.get("coordenador"))]
	if len(coordenadores) != 1:
		frappe.throw(_("Defina exatamente um coordenador para o projeto."))
	if (coordenadores[0].get("tipo_pessoa") or "") != APPROVER_TYPE_ASSOCIADO:
		frappe.throw(_("O coordenador precisa ser um envolvido do tipo Associado."))

	padrinhos = [row for row in incoming_rows if cint(row.get("padrinho_orientador"))]
	if len(padrinhos) > 1:
		frappe.throw(_("Defina no máximo um padrinho/orientador no projeto."))

	existing_rows = _get_normalized_envolvidos(doc, strict=False, include_legacy=True)
	existing_approvers: dict[str, dict[str, Any]] = {}
	for row in existing_rows:
		if not cint(row.get("aprovador")):
			continue
		key = _make_approver_key_from_envolvido_row(row)
		if key:
			existing_approvers[key] = row

	incoming_approver_keys = {
		_make_approver_key_from_envolvido_row(row)
		for row in incoming_rows
		if cint(row.get("aprovador")) and _make_approver_key_from_envolvido_row(row)
	}
	if incoming_approver_keys != set(existing_approvers.keys()):
		frappe.throw(_("Aprovadores não podem ser adicionados ou removidos pela aba Participantes."))

	for row in incoming_rows:
		key = _make_approver_key_from_envolvido_row(row)
		existing = existing_approvers.get(key)
		if existing:
			row["aprovador"] = 1
			row["origem_regra_aprovador"] = existing.get("origem_regra_aprovador") or APPROVER_ORIGIN_MANUAL
			row["permite_remover"] = 1 if cint(existing.get("permite_remover")) else 0
		else:
			row["aprovador"] = 0
			row["origem_regra_aprovador"] = ""
			row["permite_remover"] = 1

	_set_doc_envolvidos(doc, incoming_rows)
	_sync_legacy_people_from_envolvidos(doc, incoming_rows)
	doc.flags.portal_draft_save = False
	doc.save()

	return {
		"ok": True,
		"projeto": _serialize_projeto(doc),
		"envolvidos": _serialize_envolvidos(doc),
	}


@frappe.whitelist()
def salvar_tarefa_projeto_execucao(projeto_name: str, tarefa: str | dict[str, Any]) -> dict[str, Any]:
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para editar este projeto."), frappe.PermissionError)

	_assert_project_in_execution(doc)

	payload = _parse_payload(tarefa)
	tarefa_name = (payload.get("name") or "").strip()
	target_row = _find_child_row(doc.get("tarefas") or [], tarefa_name) if tarefa_name else None
	previous_status = (target_row.get("status") or "").strip() if target_row else ""

	if tarefa_name and not target_row:
		frappe.throw(_("Tarefa não encontrada no projeto."))

	if target_row:
		task_payload = {
			fieldname: _clean_value(payload.get(fieldname, target_row.get(fieldname)))
			for fieldname in TASK_FIELDS
		}
	else:
		task_payload = {fieldname: _clean_value(payload.get(fieldname)) for fieldname in TASK_FIELDS}

	team_names = set(_get_responsavel_options(doc))
	task_payload = _normalize_task_start_date(task_payload, previous_status=previous_status)
	task_payload = _normalize_task_delivery_date(task_payload)
	task_payload = _assert_task_payload(task_payload, team_names)

	if target_row:
		for fieldname in TASK_FIELDS:
			target_row.set(fieldname, task_payload.get(fieldname))
	else:
		doc.append("tarefas", task_payload)

	doc.flags.portal_draft_save = False
	doc.save()

	return {
		"ok": True,
		"tarefas": _serialize_tarefas(doc.get("tarefas") or []),
	}


@frappe.whitelist()
def atualizar_status_tarefa_projeto_execucao(
	projeto_name: str, tarefa_name: str, status: str
) -> dict[str, Any]:
	user = _require_project_editor_access()
	if not projeto_name or not tarefa_name:
		frappe.throw(_("Projeto ou tarefa não informados."))

	status = (status or "").strip()
	if status not in TASK_STATUS_OPTIONS:
		frappe.throw(_("Status da tarefa inválido."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para editar este projeto."), frappe.PermissionError)

	_assert_project_in_execution(doc)

	target_row = _find_child_row(doc.get("tarefas") or [], tarefa_name)
	if not target_row:
		frappe.throw(_("Tarefa não encontrada no projeto."))

	previous_status = (target_row.status or "").strip()
	target_row.status = status
	if status != "Nao iniciado" and previous_status == "Nao iniciado" and not target_row.data_inicio:
		target_row.data_inicio = nowdate()
	target_row.data_entrega = nowdate() if status == "Concluido" else ""
	doc.flags.portal_draft_save = False
	doc.save()

	return {
		"ok": True,
		"tarefas": _serialize_tarefas(doc.get("tarefas") or []),
	}


def validar_tarefas_atrasadas_madrugada() -> None:
	hoje = getdate(nowdate())
	projetos_execucao = frappe.get_all(
		"Projeto",
		filters={"status": STATUS_EM_EXECUCAO},
		fields=["name"],
		limit_page_length=0,
	)

	for projeto in projetos_execucao:
		projeto_name = projeto.get("name")
		if not projeto_name:
			continue

		try:
			doc = frappe.get_doc("Projeto", projeto_name)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=_("Falha ao carregar projeto para validação de atraso"),
			)
			continue

		alterou_tarefa = False
		for tarefa in doc.get("tarefas") or []:
			status = (tarefa.get("status") or "").strip()
			if status in {"Concluido", "Cancelado", "Atrasado"}:
				continue

			prazo = tarefa.get("prazo")
			if not prazo:
				continue

			try:
				prazo_date = getdate(prazo)
			except Exception:
				continue

			if prazo_date < hoje:
				tarefa.status = "Atrasado"
				alterou_tarefa = True

		if not alterou_tarefa:
			continue

		doc.flags.portal_draft_save = False
		doc.save(ignore_permissions=True)


@frappe.whitelist()
def get_tarefa_projeto_execucao_comentarios(projeto_name: str, tarefa_name: str) -> dict[str, Any]:
	_require_project_read_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("read"):
		frappe.throw(_("Você não tem permissão para visualizar este projeto."), frappe.PermissionError)

	_assert_project_visible_on_execution_page(doc)
	task_row = _get_task_row_from_project(doc, tarefa_name)

	return {
		"ok": True,
		"comentarios": _serialize_tarefa_comentarios(task_row.name),
	}


@frappe.whitelist()
def adicionar_comentario_tarefa_projeto_execucao(
	projeto_name: str, tarefa_name: str, conteudo: str
) -> dict[str, Any]:
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	texto = (conteudo or "").strip()
	if not texto:
		frappe.throw(_("Informe o comentário antes de enviar."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para editar este projeto."), frappe.PermissionError)

	_assert_project_in_execution(doc)
	task_row = _get_task_row_from_project(doc, tarefa_name)

	task_doc = frappe.get_doc("Gestao de Tarefas", task_row.name)
	task_doc.add_comment(
		"Comment",
		text=texto.replace("\n", "<br>"),
		comment_email=frappe.session.user,
		comment_by=get_fullname(frappe.session.user),
	)

	return {
		"ok": True,
		"comentarios": _serialize_tarefa_comentarios(task_row.name),
	}


@frappe.whitelist()
def editar_comentario_tarefa_projeto_execucao(
	projeto_name: str, tarefa_name: str, comentario_name: str, conteudo: str
) -> dict[str, Any]:
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	texto = (conteudo or "").strip()
	if not texto:
		frappe.throw(_("Informe o comentário antes de salvar."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para editar este projeto."), frappe.PermissionError)

	_assert_project_in_execution(doc)
	task_row = _get_task_row_from_project(doc, tarefa_name)
	comment_doc = _get_task_comment_from_row(task_row, comentario_name)
	_assert_comment_author(comment_doc, user)

	comment_doc.content = texto.replace("\n", "<br>")
	comment_doc.comment_by = get_fullname(user)
	comment_doc.comment_email = user
	comment_doc.save(ignore_permissions=True)

	return {
		"ok": True,
		"comentarios": _serialize_tarefa_comentarios(task_row.name),
	}


@frappe.whitelist()
def apagar_comentario_tarefa_projeto_execucao(
	projeto_name: str, tarefa_name: str, comentario_name: str
) -> dict[str, Any]:
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para editar este projeto."), frappe.PermissionError)

	_assert_project_in_execution(doc)
	task_row = _get_task_row_from_project(doc, tarefa_name)
	comment_doc = _get_task_comment_from_row(task_row, comentario_name)
	_assert_comment_author(comment_doc, user)

	frappe.delete_doc("Comment", comment_doc.name, ignore_permissions=True)

	return {
		"ok": True,
		"comentarios": _serialize_tarefa_comentarios(task_row.name),
	}


@frappe.whitelist()
def salvar_reuniao_projeto_execucao(projeto_name: str, reuniao: str | dict[str, Any]) -> dict[str, Any]:
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para editar este projeto."), frappe.PermissionError)

	_assert_project_in_execution(doc)

	payload = _parse_payload(reuniao)
	reuniao_name = (payload.get("name") or "").strip()
	target_row = _find_child_row(doc.get("reunioes") or [], reuniao_name) if reuniao_name else None

	if reuniao_name and not target_row:
		frappe.throw(_("Reunião não encontrada no projeto."))

	if target_row:
		meeting_payload = {
			fieldname: _clean_value(payload.get(fieldname, target_row.get(fieldname)))
			for fieldname in MEETING_FIELDS
		}
	else:
		meeting_payload = {fieldname: _clean_value(payload.get(fieldname)) for fieldname in MEETING_FIELDS}

	meeting_payload = _assert_meeting_payload(meeting_payload)

	if target_row:
		for fieldname in MEETING_FIELDS:
			target_row.set(fieldname, meeting_payload.get(fieldname))
	else:
		doc.append("reunioes", meeting_payload)

	doc.flags.portal_draft_save = False
	doc.save()

	return {
		"ok": True,
		"reunioes": _serialize_reunioes(doc.get("reunioes") or []),
	}


# ---------------------------------------------------------------------------
# Avaliação de Projeto — endpoints protegidos
# ---------------------------------------------------------------------------


def _get_avaliacao_for_projeto(projeto_name: str):
	"""Retorna a Avaliacao de Projeto vinculada ou None."""
	avaliacao_name = frappe.db.get_value("Avaliacao de Projeto", {"projeto": projeto_name}, "name")
	if not avaliacao_name:
		return None
	return frappe.get_doc("Avaliacao de Projeto", avaliacao_name)


def _serialize_avaliacao_individuais(avaliacao_doc) -> list[dict[str, Any]]:
	"""Serializa as avaliações individuais para o frontend."""
	result: list[dict[str, Any]] = []
	for row in avaliacao_doc.avaliacoes_individuais or []:
		result.append(
			{
				"idx": row.idx,
				"name": row.name,
				"avaliador": row.avaliador,
				"email": row.email,
				"avaliacao_concluida": cint(row.avaliacao_concluida),
				"resultado_projeto": row.resultado_projeto if cint(row.avaliacao_concluida) else None,
				"satisfacao_colaboracao": row.satisfacao_colaboracao
				if cint(row.avaliacao_concluida)
				else None,
				"objetivos_atingidos": row.objetivos_atingidos if cint(row.avaliacao_concluida) else None,
				"muito_bom": row.muito_bom if cint(row.avaliacao_concluida) else None,
				"pontos_melhoria": row.pontos_melhoria if cint(row.avaliacao_concluida) else None,
			}
		)
	return result


def _serialize_objetivos_atingidos(avaliacao_doc) -> list[dict[str, Any]]:
	"""Serializa os objetivos atingidos para o frontend."""
	result: list[dict[str, Any]] = []
	for row in avaliacao_doc.objetivos_atingidos or []:
		result.append(
			{
				"idx": row.idx,
				"name": row.name,
				"objetivo": row.objetivo,
				"objetivo_atingido": row.objetivo_atingido,
				"porque_nao_foi_atingido": row.porque_nao_foi_atingido,
			}
		)
	return result


def _serialize_avaliacao(avaliacao_doc) -> dict[str, Any]:
	"""Serializa a avaliação completa para o frontend."""
	individuais = _serialize_avaliacao_individuais(avaliacao_doc)
	total = len(individuais)
	concluidas = sum(1 for i in individuais if i["avaliacao_concluida"])

	return {
		"name": avaliacao_doc.name,
		"status": avaliacao_doc.status or AVALIACAO_STATUS_EM_ANDAMENTO,
		"avaliacao_geral": avaliacao_doc.avaliacao_geral or 0,
		"satisfacao_dos_participantes": avaliacao_doc.satisfacao_dos_participantes or 0,
		"individuais": individuais,
		"total_individuais": total,
		"concluidas_individuais": concluidas,
		"objetivos_atingidos": _serialize_objetivos_atingidos(avaliacao_doc),
		"o_que_funcionou_bem_na_dinamica_da_equipe": avaliacao_doc.o_que_funcionou_bem_na_dinamica_da_equipe
		or "",
		"o_que_nao_funcionou_na_dinamica_da_equipe": avaliacao_doc.o_que_nao_funcionou_na_dinamica_da_equipe
		or "",
		"maior_aprendizado_gerado": avaliacao_doc.maior_aprendizado_gerado or "",
		"impacto_gerado_para_comunidade": avaliacao_doc.impacto_gerado_para_comunidade or "",
		"pontos_positivos_adicionais": avaliacao_doc.pontos_positivos_adicionais or "",
		"pontos_de_melhoria_adicionais": avaliacao_doc.pontos_de_melhoria_adicionais or "",
		"resumo_avaliacoes_individuais": avaliacao_doc.resumo_avaliacoes_individuais or "",
		"resumo_avaliacao_completa": avaliacao_doc.resumo_avaliacao_completa or "",
	}


@frappe.whitelist()
def get_avaliacao_projeto_data(projeto_name: str) -> dict[str, Any]:
	"""Retorna dados da aba de avaliação para o frontend."""
	user = _require_project_read_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	if not doc.has_permission("read"):
		frappe.throw(_("Você não tem permissão para visualizar este projeto."), frappe.PermissionError)

	_assert_project_visible_on_execution_page(doc)

	avaliacao_doc = _get_avaliacao_for_projeto(projeto_name)
	avaliacao_data = _serialize_avaliacao(avaliacao_doc) if avaliacao_doc else None

	can_edit_context = _can_user_edit_project_execution_context(user, doc)
	is_coordinator = _is_user_coordinator(user, doc)

	can_start = (
		can_edit_context
		and is_coordinator
		and avaliacao_doc is None
		and doc.get("status") in STATUS_EXECUCAO_PAGE_ALLOWED
	)

	can_edit_general = (
		can_edit_context
		and avaliacao_doc is not None
		and doc.get("status") not in STATUS_EXECUCAO_PAGE_READ_ONLY
	)

	return {
		"ok": True,
		"avaliacao_exists": avaliacao_doc is not None,
		"avaliacao": avaliacao_data,
		"can_start_evaluation": can_start,
		"can_edit_general": can_edit_general,
		"is_coordinator": is_coordinator,
	}


@frappe.whitelist()
def iniciar_avaliacao_projeto(projeto_name: str) -> dict[str, Any]:
	"""Cria a Avaliacao de Projeto e envia emails com links individuais.

	Justificativa para ignore_permissions na inserção: o coordenador já é
	autenticado com perfil Editor de projetos e a criação é feita em contexto
	controlado após validação de todas as pré-condições.
	"""
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("read"):
		frappe.throw(_("Você não tem permissão para visualizar este projeto."), frappe.PermissionError)

	if not _is_user_coordinator(user, doc):
		frappe.throw(_("Somente o coordenador do projeto pode iniciar a avaliação."), frappe.PermissionError)

	if doc.get("status") not in STATUS_EXECUCAO_PAGE_ALLOWED:
		frappe.throw(_("O projeto precisa estar em execução, concluído ou cancelado para iniciar avaliação."))

	existing = frappe.db.get_value("Avaliacao de Projeto", {"projeto": projeto_name}, "name")
	if existing:
		frappe.throw(_("Já existe uma avaliação para este projeto."))

	reviewers = _get_all_reviewer_data(doc)
	if not reviewers:
		frappe.throw(_("Nenhum envolvido encontrado no projeto para avaliação."))

	avaliacao_doc = frappe.new_doc("Avaliacao de Projeto")
	avaliacao_doc.projeto = projeto_name
	avaliacao_doc.status = AVALIACAO_STATUS_EM_ANDAMENTO

	for reviewer in reviewers:
		token = frappe.generate_hash(length=32)
		avaliacao_doc.append(
			"avaliacoes_individuais",
			{
				"avaliador": reviewer["nome"],
				"email": reviewer["email"],
				"token": token,
			},
		)

	avaliacao_doc.insert(ignore_permissions=True)

	_enviar_emails_avaliacao(doc, avaliacao_doc, reviewers)

	return {
		"ok": True,
		"avaliacao_name": avaliacao_doc.name,
	}


def _enviar_emails_avaliacao(
	projeto_doc, avaliacao_doc, reviewers: list[dict[str, str]] | None = None
) -> None:
	"""Envia email de convite para cada avaliador."""
	projeto_titulo = (projeto_doc.get("nome_do_projeto") or "").strip() or projeto_doc.name
	site_url = frappe.utils.get_url()
	reviewer_phone_map = _build_reviewers_phone_map(reviewers)

	for row in avaliacao_doc.avaliacoes_individuais or []:
		email = (row.email or "").strip()
		token = (row.token or "").strip()
		nome = (row.avaliador or "").strip()
		primeiro_nome = _get_first_name(nome, fallback="avaliador")
		if not email or not token:
			continue

		link = f"{site_url}/projetos/avaliacao_individual?token={token}"

		subject = f"Avaliação do projeto: {projeto_titulo}"
		message = f"""
		<div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
			<h2 style="color: #0d4d91;">Avaliação de Projeto</h2>
			<p>Olá, <strong>{frappe.utils.escape_html(nome)}</strong>!</p>
			<p>Você foi convidado(a) a avaliar o projeto <strong>{frappe.utils.escape_html(projeto_titulo)}</strong>.</p>
			<p>Sua opinião é fundamental para melhorarmos nossos projetos. A avaliação leva apenas alguns minutos.</p>
			<p style="margin: 24px 0;">
				<a href="{link}" style="background-color: #0d4d91; color: #fff; padding: 12px 24px;
				text-decoration: none; border-radius: 6px; display: inline-block; font-weight: 600;">
					Preencher avaliação
				</a>
			</p>
			<p style="color: #666; font-size: 13px;">
				Este é um link exclusivo para você. Não compartilhe com outras pessoas.<br>
				Caso não consiga clicar no botão, copie e cole o link abaixo no seu navegador:<br>
				<a href="{link}" style="color: #0d4d91;">{link}</a>
			</p>
		</div>
		"""

		try:
			frappe.sendmail(
				recipients=[email],
				subject=subject,
				message=message,
				now=True,
			)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Falha ao enviar email de avaliação para {email}",
			)

		telefone = reviewer_phone_map.get(("email", email.lower())) or reviewer_phone_map.get(
			("nome", nome.lower())
		)
		if telefone:
			whatsapp_message = (
				f"Oi, {primeiro_nome}!\n\n"
				f"Chegou o momento de avaliar o projeto *{projeto_titulo}*! "
				f"Para isso, basta acessar o link abaixo e preencher sua avaliação:\n{link}\n\n"
				f"Ahh, este é o mesmo link enviado por e-mail, então não precisa se preocupar em responder duas vezes, combinado?\n\n"
				"Obrigado por contribuir para melhorar nossos projetos!"
			)
			_send_whatsapp_notification(
				telefone,
				whatsapp_message,
				contexto=f"avaliacao_projeto:{projeto_doc.name}:{email}",
			)


def _enviar_email_avaliacao_individual(projeto_doc, row) -> dict[str, bool]:
	"""Reenvia convite individual por email e, quando disponível, por WhatsApp."""
	projeto_titulo = (projeto_doc.get("nome_do_projeto") or "").strip() or projeto_doc.name
	site_url = frappe.utils.get_url()
	email = (row.email or "").strip()
	token = (row.token or "").strip()
	nome = (row.avaliador or "").strip()
	primeiro_nome = _get_first_name(nome, fallback="avaliador")

	if not email or not token:
		frappe.throw(_("Avaliador sem email ou token."))

	link = f"{site_url}/projetos/avaliacao_individual?token={token}"
	subject = f"Lembrete: Avaliação do projeto {projeto_titulo}"
	message = f"""
	<div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px;">
		<h2 style="color: #0d4d91;">Lembrete de Avaliação</h2>
		<p>Olá, <strong>{frappe.utils.escape_html(nome)}</strong>!</p>
		<p>Este é um lembrete para que você avalie o projeto <strong>{frappe.utils.escape_html(projeto_titulo)}</strong>.</p>
		<p>Sua opinião é fundamental. A avaliação leva apenas alguns minutos.</p>
		<p style="margin: 24px 0;">
			<a href="{link}" style="background-color: #0d4d91; color: #fff; padding: 12px 24px;
			text-decoration: none; border-radius: 6px; display: inline-block; font-weight: 600;">
				Preencher avaliação
			</a>
		</p>
		<p style="color: #666; font-size: 13px;">
			Este é um link exclusivo para você. Não compartilhe com outras pessoas.<br>
			<a href="{link}" style="color: #0d4d91;">{link}</a>
		</p>
	</div>
	"""

	frappe.sendmail(
		recipients=[email],
		subject=subject,
		message=message,
		now=True,
	)

	reviewers = _get_all_reviewer_data(projeto_doc)
	reviewer_phone_map = _build_reviewers_phone_map(reviewers)
	telefone = reviewer_phone_map.get(("email", email.lower())) or reviewer_phone_map.get(
		("nome", nome.lower())
	)
	if not telefone:
		return {"email_sent": True, "whatsapp_sent": False}

	whatsapp_message = (
		f"Oi, {primeiro_nome}!\n\n"
		f"Este é um lembrete para avaliar o projeto *{projeto_titulo}*. "
		f"Acesse o link para preencher sua avaliação:\n{link}\n\n"
		"Obrigado por contribuir para melhorar nossos projetos!"
	)
	whatsapp_sent = _send_whatsapp_notification(
		telefone,
		whatsapp_message,
		contexto=f"reenviar_avaliacao_projeto:{projeto_doc.name}:{email}",
	)

	return {"email_sent": True, "whatsapp_sent": bool(whatsapp_sent)}


@frappe.whitelist()
def reenviar_email_avaliacao(projeto_name: str, avaliador_idx: int) -> dict[str, Any]:
	"""Reenvia convite de avaliação (email e WhatsApp) para avaliador pendente."""
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not _is_user_coordinator(user, doc):
		frappe.throw(
			_("Somente o coordenador do projeto pode reenviar convites de avaliação."),
			frappe.PermissionError,
		)

	avaliacao_doc = _get_avaliacao_for_projeto(projeto_name)
	if not avaliacao_doc:
		frappe.throw(_("Nenhuma avaliação encontrada para este projeto."))

	avaliador_idx = cint(avaliador_idx)
	target = None
	for row in avaliacao_doc.avaliacoes_individuais or []:
		if row.idx == avaliador_idx:
			target = row
			break

	if not target:
		frappe.throw(_("Avaliador não encontrado."))

	if cint(target.avaliacao_concluida):
		frappe.throw(_("Este avaliador já respondeu a avaliação."))

	resultado_envio = _enviar_email_avaliacao_individual(doc, target)

	return {
		"ok": True,
		"email_sent": bool(resultado_envio.get("email_sent")),
		"whatsapp_sent": bool(resultado_envio.get("whatsapp_sent")),
	}


@frappe.whitelist()
def salvar_avaliacao_geral_projeto(projeto_name: str, data: str | dict[str, Any]) -> dict[str, Any]:
	"""Salva os dados da avaliação geral do projeto."""
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("write"):
		frappe.throw(_("Você não tem permissão para editar este projeto."), frappe.PermissionError)

	avaliacao_doc = _get_avaliacao_for_projeto(projeto_name)
	if not avaliacao_doc:
		frappe.throw(_("Nenhuma avaliação encontrada para este projeto."))

	payload = _parse_payload(data)

	objetivos_data = payload.get("objetivos_atingidos")
	if isinstance(objetivos_data, list):
		for item in objetivos_data:
			if not isinstance(item, dict):
				continue
			objetivo_text = (item.get("objetivo") or "").strip()
			for row in avaliacao_doc.objetivos_atingidos or []:
				if (row.objetivo or "").strip() == objetivo_text:
					row.objetivo_atingido = item.get("objetivo_atingido") or ""
					row.porque_nao_foi_atingido = item.get("porque_nao_foi_atingido") or ""
					break

	text_fields = [
		"o_que_funcionou_bem_na_dinamica_da_equipe",
		"o_que_nao_funcionou_na_dinamica_da_equipe",
		"maior_aprendizado_gerado",
		"impacto_gerado_para_comunidade",
		"pontos_positivos_adicionais",
		"pontos_de_melhoria_adicionais",
	]
	for field in text_fields:
		if field in payload:
			avaliacao_doc.set(field, (payload.get(field) or "").strip())

	avaliacao_doc.flags.ignore_validate = False
	avaliacao_doc.save(ignore_permissions=True)

	return {
		"ok": True,
		"avaliacao": _serialize_avaliacao(avaliacao_doc),
	}


@frappe.whitelist()
def solicitar_resumo_avaliacoes_individuais(projeto_name: str) -> dict[str, Any]:
	"""Dispara geração de resumo das avaliações individuais via LLM."""
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("read"):
		frappe.throw(_("Você não tem permissão para visualizar este projeto."), frappe.PermissionError)

	avaliacao_doc = _get_avaliacao_for_projeto(projeto_name)
	if not avaliacao_doc:
		frappe.throw(_("Nenhuma avaliação encontrada para este projeto."))

	concluidas = sum(1 for r in avaliacao_doc.avaliacoes_individuais if cint(r.avaliacao_concluida))
	if concluidas == 0:
		frappe.throw(_("Nenhuma avaliação individual foi concluída ainda."))

	frappe.db.set_value(
		"Avaliacao de Projeto",
		avaliacao_doc.name,
		"resumo_avaliacoes_individuais",
		AVALIACAO_RESUMO_EM_PROCESSAMENTO,
		update_modified=True,
	)

	frappe.enqueue(
		method="gris.api.gestao_de_projetos.avaliacao_projeto_tasks.processar_resumo_individuais",
		queue="long",
		timeout=600,
		enqueue_after_commit=True,
		avaliacao_name=avaliacao_doc.name,
	)

	return {
		"ok": True,
		"pending": True,
		"resumo_avaliacoes_individuais": AVALIACAO_RESUMO_EM_PROCESSAMENTO,
	}


@frappe.whitelist()
def solicitar_resumo_avaliacao_completa(projeto_name: str) -> dict[str, Any]:
	"""Dispara geração do resumo completo da avaliação via LLM."""
	user = _require_project_editor_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	doc = frappe.get_doc("Projeto", projeto_name)
	_require_project_execution_edit_access(doc, user=user)
	if not doc.has_permission("read"):
		frappe.throw(_("Você não tem permissão para visualizar este projeto."), frappe.PermissionError)

	avaliacao_doc = _get_avaliacao_for_projeto(projeto_name)
	if not avaliacao_doc:
		frappe.throw(_("Nenhuma avaliação encontrada para este projeto."))

	frappe.db.set_value(
		"Avaliacao de Projeto",
		avaliacao_doc.name,
		"resumo_avaliacao_completa",
		AVALIACAO_RESUMO_EM_PROCESSAMENTO,
		update_modified=True,
	)

	frappe.enqueue(
		method="gris.api.gestao_de_projetos.avaliacao_projeto_tasks.processar_resumo_completo",
		queue="long",
		timeout=600,
		enqueue_after_commit=True,
		avaliacao_name=avaliacao_doc.name,
	)

	return {
		"ok": True,
		"pending": True,
		"resumo_avaliacao_completa": AVALIACAO_RESUMO_EM_PROCESSAMENTO,
	}


@frappe.whitelist()
def consultar_resumo_avaliacao(projeto_name: str) -> dict[str, Any]:
	"""Consulta o estado dos resumos da avaliação (polling)."""
	_require_project_read_access()
	if not projeto_name:
		frappe.throw(_("Projeto não informado."))

	avaliacao_doc = _get_avaliacao_for_projeto(projeto_name)
	if not avaliacao_doc:
		return {
			"ok": True,
			"resumo_avaliacoes_individuais": "",
			"resumo_avaliacao_completa": "",
			"pending_individuais": False,
			"pending_completa": False,
		}

	resumo_ind = avaliacao_doc.resumo_avaliacoes_individuais or ""
	resumo_comp = avaliacao_doc.resumo_avaliacao_completa or ""

	return {
		"ok": True,
		"resumo_avaliacoes_individuais": resumo_ind,
		"resumo_avaliacao_completa": resumo_comp,
		"pending_individuais": resumo_ind == AVALIACAO_RESUMO_EM_PROCESSAMENTO,
		"pending_completa": resumo_comp == AVALIACAO_RESUMO_EM_PROCESSAMENTO,
	}
