from __future__ import annotations

import unicodedata

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

MAPEAMENTO_DTYPE = "Mapeamento de perguntas e respostas da entrevista"

SCORE_FIELDS = [
	"pontuacao_dirigente_administrativo_financeiro",
	"pontuacao_dirigente_gestao_institucional",
	"pontuacao_dirigente_metodos_educativos",
	"pontuacao_ramo_lobinho",
	"pontuacao_ramo_escoteiro",
	"pontuacao_ramo_senior",
	"pontuacao_ramo_pioneiro",
]

QUESTION_FIELDS: list[dict[str, str]] = [
	{
		"fieldname": "q_ce_1",
		"pergunta": "Por que você deseja ingressar, retornar, permanecer ou mudar de cargo no Movimento Escoteiro?",
	},
	{
		"fieldname": "q_ce_2",
		"pergunta": "Como foi seu processo de educação e formação? Quando algum tema trouxe curiosidade ou dúvida, você buscou conhecê-lo melhor? Se sim, como? Se não, por quê?",
	},
	{
		"fieldname": "q_ce_3",
		"pergunta": "Alguma vez você já esteve diante de uma situação que fez você alterar seu jeito de fazer as coisas? Se sim, como foi esse processo para você?",
	},
	{
		"fieldname": "q_ce_4",
		"pergunta": "Em algum momento você precisou assumir responsabilidade por uma tarefa que não fazia parte do seu escopo de trabalho? Se sim, como você se viu nessa situação?",
	},
	{
		"fieldname": "q_ce_5",
		"pergunta": "Alguma vez você já trabalhou com planejamento? Como organizava sua rotina e seus projetos?",
	},
	{
		"fieldname": "q_di_1",
		"pergunta": "Você poderia nos contar um pouco sobre sua experiência com gestão financeira?",
	},
	{
		"fieldname": "q_di_2",
		"pergunta": "Você já precisou pensar em projetos ou campanhas para arrecadação de dinheiro? Se sim, como foi essa experiência?",
	},
	{
		"fieldname": "q_di_3",
		"pergunta": "Você já coordenou alguma equipe ou esteve à frente de algum projeto? Como foi para você?",
	},
	{
		"fieldname": "q_di_4",
		"pergunta": "Você já assumiu a responsabilidade por algum projeto?",
	},
	{
		"fieldname": "q_di_5",
		"pergunta": "Caso tenha coordenado um projeto, como você organizava as tarefas?",
	},
	{
		"fieldname": "q_di_6",
		"pergunta": "Você já coordenou alguma equipe?",
	},
	{
		"fieldname": "q_di_7",
		"pergunta": "Como você ensinava as pessoas e as motivava?",
	},
	{
		"fieldname": "q_di_8",
		"pergunta": "Se você se sentiu como exemplo para alguém, como foi esse processo para você?",
	},
	{
		"fieldname": "q_es_1",
		"pergunta": "Você tem, ou teve, experiência no trabalho com crianças de 6,5 anos a 10 anos? Fale sobre.",
	},
	{
		"fieldname": "q_es_2",
		"pergunta": "Você já teve que trabalhar com um mundo de imaginação, usando fantasia para envolver os jovens?",
	},
	{
		"fieldname": "q_es_3",
		"pergunta": "Você tem ou teve experiência no trabalho com crianças de 11 anos a 14 anos? Fale sobre.",
	},
	{
		"fieldname": "q_es_4",
		"pergunta": "Você já coordenou alguma equipe de jovens? Como foi a vivência de deixá-los trabalhar em grupo?",
	},
	{
		"fieldname": "q_es_5",
		"pergunta": "Você já teve vivências em atividades ao ar livre, como trilhas, caminhadas ou acampamentos?",
	},
	{
		"fieldname": "q_es_6",
		"pergunta": "Você tem, ou teve, experiência no trabalho com jovens de 15 anos a 17 anos? Fale sobre.",
	},
	{
		"fieldname": "q_es_7",
		"pergunta": "Você já teve vivências em atividades radicais ao ar livre? Trilhas longas, rapel, acampamentos rústicos etc.?",
	},
	{
		"fieldname": "q_es_8",
		"pergunta": "Você já precisou exercer autoridade sobre grupos de jovens? Como vivenciou esse processo?",
	},
	{
		"fieldname": "q_es_9",
		"pergunta": "Você tem, ou teve, experiência no trabalho com jovens de 18 anos a 21 anos? Fale sobre.",
	},
	{
		"fieldname": "q_es_10",
		"pergunta": "Você já precisou inspirar e orientar adultos em suas vidas pessoais? Como foi essa experiência?",
	},
	{
		"fieldname": "q_es_11",
		"pergunta": "Você já buscou realizar projetos para melhorar a vida dos outros? Como foi essa vivência?",
	},
]

RESUMO_TRIGGER_FIELDS = {
	"funcao_atual",
	"profissao",
	"formacao",
	"hobbies_e_interesses",
	"motivo_da_entrevista",
	"observacoes",
	*[item["fieldname"] for item in QUESTION_FIELDS],
	*[f"obs_{item['fieldname']}" for item in QUESTION_FIELDS],
}


def _normalize_text(value: str | None) -> str:
	if not value:
		return ""
	normalized = unicodedata.normalize("NFKD", value)
	without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
	return " ".join(without_accents.lower().split())


def get_question_options_map() -> dict[str, list[str]]:
	rows = frappe.get_all(
		MAPEAMENTO_DTYPE,
		fields=["pergunta", "resposta"],
		order_by="id_origem asc",
		limit_page_length=0,
	)

	options_map: dict[str, list[str]] = {}
	for row in rows:
		question_key = _normalize_text(row.get("pergunta"))
		if not question_key:
			continue
		options_map.setdefault(question_key, [])
		answer = row.get("resposta")
		if answer and answer not in options_map[question_key]:
			options_map[question_key].append(answer)
	return options_map


def get_ordered_questions_from_mapping() -> list[str]:
	rows = frappe.get_all(
		MAPEAMENTO_DTYPE,
		fields=["pergunta", "id_origem"],
		order_by="id_origem asc",
		limit_page_length=0,
	)

	questions: list[str] = []
	seen: set[str] = set()
	for row in rows:
		question = (row.get("pergunta") or "").strip()
		if not question:
			continue
		normalized = _normalize_text(question)
		if normalized in seen:
			continue
		seen.add(normalized)
		questions.append(question)

	return questions


def get_fieldname_question_map() -> dict[str, str]:
	mapped_questions = get_ordered_questions_from_mapping()
	result: dict[str, str] = {}

	for index, item in enumerate(QUESTION_FIELDS):
		fieldname = item["fieldname"]
		if index < len(mapped_questions):
			result[fieldname] = mapped_questions[index]
		else:
			result[fieldname] = item["pergunta"]

	return result


def get_options_by_fieldname() -> dict[str, list[str]]:
	options_map = get_question_options_map()
	question_map = get_fieldname_question_map()
	result: dict[str, list[str]] = {}
	for item in QUESTION_FIELDS:
		fieldname = item["fieldname"]
		question = question_map.get(fieldname, item["pergunta"])
		result[fieldname] = options_map.get(_normalize_text(question), [])
	return result


def get_question_by_fieldname() -> dict[str, str]:
	return get_fieldname_question_map()


def get_mapping_by_question_and_answer(question: str, answer: str):
	if not answer:
		return None

	candidates = frappe.get_all(
		MAPEAMENTO_DTYPE,
		filters={"resposta": answer},
		fields=["name", "pergunta", "resposta", "alerta", "motivo_do_alerta", *SCORE_FIELDS],
		limit_page_length=0,
	)

	question_key = _normalize_text(question)
	for row in candidates:
		if _normalize_text(row.get("pergunta")) == question_key:
			return row

	return None


class EntrevistaporCompetencias(Document):
	def validate(self):
		self.validate_associado_unico()
		self.calculate_scores_and_alerts()
		self.clear_resumo_when_needed()
		self.data_da_ultima_atualizacao = now_datetime()

	def clear_resumo_when_needed(self):
		if self.is_new():
			return

		if not self.resumo:
			return

		if not any(self.has_value_changed(fieldname) for fieldname in RESUMO_TRIGGER_FIELDS):
			return

		self.resumo = ""

	def after_insert(self):
		self._enqueue_summary_generation()

	def on_update(self):
		if self.flags.in_insert:
			return

		if self.flags.from_summary_job:
			return

		if not self._should_enqueue_summary_generation():
			return

		self._enqueue_summary_generation()

	def _should_enqueue_summary_generation(self) -> bool:
		for fieldname in RESUMO_TRIGGER_FIELDS:
			if self.has_value_changed(fieldname):
				return True
		return False

	def _enqueue_summary_generation(self):
		from gris.api.gestao_adultos.summary_tasks import enfileirar_resumo_entrevista

		enfileirar_resumo_entrevista(self.name)

	def validate_associado_unico(self):
		if not self.associado:
			return

		existing_name = frappe.db.get_value(
			"Entrevista por Competencias",
			{"associado": self.associado, "name": ["!=", self.name]},
			"name",
		)
		if existing_name:
			frappe.throw("Já existe entrevista cadastrada para este associado.")

	def calculate_scores_and_alerts(self):
		score_totals = {fieldname: 0 for fieldname in SCORE_FIELDS}
		self.set("alertas", [])
		question_map = get_fieldname_question_map()

		for item in QUESTION_FIELDS:
			fieldname = item["fieldname"]
			answer = self.get(fieldname)
			if not answer:
				continue

			question = question_map.get(fieldname, item["pergunta"])
			mapping = get_mapping_by_question_and_answer(question, answer)
			if not mapping:
				continue

			for score_field in SCORE_FIELDS:
				score_totals[score_field] += int(mapping.get(score_field) or 0)

			if int(mapping.get("alerta") or 0):
				self.append(
					"alertas",
					{
						"pergunta": mapping.get("pergunta"),
						"resposta": mapping.get("resposta"),
						"motivo_do_alerta": mapping.get("motivo_do_alerta"),
					},
				)

		for score_field, value in score_totals.items():
			self.set(score_field, value)
