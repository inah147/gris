from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class AvaliacaodeProjeto(Document):
	def validate(self):
		self._validate_projeto()
		self._sync_objetivos_do_projeto()
		self._validate_avaliadores_permitidos()
		self._calculate_review_metrics()

	def _validate_projeto(self):
		if not self.projeto:
			frappe.throw(_("Projeto e obrigatorio."))

		if not frappe.db.exists("Projeto", self.projeto):
			frappe.throw(_("Projeto informado nao existe."))

	def _sync_objetivos_do_projeto(self):
		project_goals = _get_project_goals(self.projeto)
		if not project_goals:
			return

		existing = {
			(row.objetivo or "").strip(): row for row in (self.objetivos_atingidos or []) if (row.objetivo or "").strip()
		}
		self.set("objetivos_atingidos", [])
		for objetivo in project_goals:
			previous = existing.get(objetivo)
			self.append(
				"objetivos_atingidos",
				{
					"objetivo": objetivo,
					"objetivo_atingido": previous.objetivo_atingido if previous else None,
					"porque_nao_foi_atingido": previous.porque_nao_foi_atingido if previous else None,
				},
			)

	def _validate_avaliadores_permitidos(self):
		allowed = set(_get_allowed_reviewer_names(self.projeto))
		for individual in self.avaliacoes_individuais or []:
			if individual.avaliador and individual.avaliador not in allowed:
				frappe.throw(
					_("Avaliador '{0}' deve ser da equipe de interesse ou padrinho/orientador.").format(
						individual.avaliador
					)
				)

	def _calculate_review_metrics(self):
		results: list[int] = []
		satisfaction: list[int] = []

		for individual in self.avaliacoes_individuais or []:
			if individual.resultado_projeto is not None and str(individual.resultado_projeto) != "":
				results.append(cint(individual.resultado_projeto))
			if individual.satisfacao_colaboracao is not None and str(individual.satisfacao_colaboracao) != "":
				satisfaction.append(cint(individual.satisfacao_colaboracao))

		self.avaliacao_geral = round(sum(results) / len(results), 2) if results else 0
		if satisfaction:
			promoters = sum(1 for value in satisfaction if value >= 9)
			detractors = sum(1 for value in satisfaction if value <= 6)
			self.satisfacao_dos_participantes = round((promoters - detractors) / len(satisfaction), 4)
		else:
			self.satisfacao_dos_participantes = 0


@frappe.whitelist()
def get_avaliadores_permitidos(projeto: str) -> list[str]:
	if not projeto:
		return []
	return _get_allowed_reviewer_names(projeto)


def _get_project_goals(projeto: str) -> list[str]:
	doc = frappe.get_doc("Projeto", projeto)
	return [(row.objetivo or "").strip() for row in (doc.objetivos or []) if (row.objetivo or "").strip()]


def _get_allowed_reviewer_names(projeto: str) -> list[str]:
	doc = frappe.get_doc("Projeto", projeto)
	names = [(row.nome or "").strip() for row in (doc.equipe_de_interesse or []) if (row.nome or "").strip()]

	padrinho = None
	if doc.tipo_padrinho_ou_orientador == "Responsavel" and doc.padrinho_responsavel:
		padrinho = frappe.db.get_value("Responsavel", doc.padrinho_responsavel, "nome_completo")
	elif doc.padrinho_associado:
		padrinho = frappe.db.get_value("Associado", doc.padrinho_associado, "nome_completo")

	if padrinho:
		names.append(padrinho)

	# Preserva ordem e remove duplicados.
	return list(dict.fromkeys([name for name in names if name]))
