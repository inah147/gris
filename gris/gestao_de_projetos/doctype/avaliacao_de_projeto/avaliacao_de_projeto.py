from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

VALID_RESULTADO_OPTIONS = {str(i) for i in range(11)}


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
			(row.objetivo or "").strip(): row
			for row in (self.objetivos_atingidos or [])
			if (row.objetivo or "").strip()
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
					_("Avaliador '{0}' deve ser um envolvido marcado para participar da avaliação.").format(
						individual.avaliador
					)
				)

	def _calculate_review_metrics(self):
		results: list[int] = []
		satisfaction: list[int] = []

		for individual in self.avaliacoes_individuais or []:
			# Só linhas efetivamente respondidas entram nas métricas: as pendentes
			# carregam o placeholder "0" do campo Select e distorceriam a média.
			if not cint(individual.avaliacao_concluida):
				continue
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


# Público por necessidade: formulário de avaliação aberto por link. O acesso é
# controlado pelo token único de no mínimo 16 caracteres.
@frappe.whitelist(allow_guest=True)  # nosemgrep
def get_avaliacao_individual_por_token(token: str) -> dict[str, Any]:
	"""Retorna dados mínimos de uma avaliação individual via token único (público)."""
	token = (token or "").strip()
	if not token or len(token) < 16:
		frappe.throw(_("Link de avaliação inválido."))

	row = frappe.db.get_value(
		"Avaliacao Individual Projeto",
		{"token": token},
		["name", "parent", "avaliador", "avaliacao_concluida"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Link de avaliação inválido ou expirado."))

	projeto_name = frappe.db.get_value("Avaliacao de Projeto", row.parent, "projeto")
	projeto_titulo = ""
	if projeto_name:
		projeto_titulo = frappe.db.get_value("Projeto", projeto_name, "nome_do_projeto") or ""

	return {
		"ok": True,
		"avaliador": row.avaliador,
		"projeto_titulo": projeto_titulo,
		"avaliacao_concluida": cint(row.avaliacao_concluida),
	}


# Público por necessidade: envio da avaliação pelo link, controlado pelo token único
# e não reutilizável, como diz a docstring.
@frappe.whitelist(allow_guest=True)  # nosemgrep
def submeter_avaliacao_individual(
	token: str,
	resultado_projeto: str,
	satisfacao_colaboracao: str,
	objetivos_atingidos: str,
	muito_bom: str,
	pontos_melhoria: str,
) -> dict[str, Any]:
	"""Permite que um avaliador submeta sua avaliação individual via token único (público).

	Justificativa para allow_guest e ignore_permissions: endpoint público com acesso
	controlado exclusivamente por token único e não-reutilizável.
	"""
	token = (token or "").strip()
	if not token or len(token) < 16:
		frappe.throw(_("Link de avaliação inválido."))

	resultado_projeto = (resultado_projeto or "").strip()
	satisfacao_colaboracao = (satisfacao_colaboracao or "").strip()
	objetivos_atingidos = (objetivos_atingidos or "").strip()
	muito_bom = (muito_bom or "").strip()
	pontos_melhoria = (pontos_melhoria or "").strip()

	if resultado_projeto not in VALID_RESULTADO_OPTIONS:
		frappe.throw(_("Resultado do projeto deve ser um valor de 0 a 10."))
	if satisfacao_colaboracao not in VALID_RESULTADO_OPTIONS:
		frappe.throw(_("Satisfação deve ser um valor de 0 a 10."))
	if not objetivos_atingidos:
		frappe.throw(_("Preencha se o projeto atingiu os objetivos."))
	if not muito_bom:
		frappe.throw(_("Preencha o que foi muito bom no projeto."))
	if not pontos_melhoria:
		frappe.throw(_("Preencha os pontos de melhoria."))

	row = frappe.db.get_value(
		"Avaliacao Individual Projeto",
		{"token": token},
		["name", "parent", "avaliacao_concluida"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Link de avaliação inválido ou expirado."))

	if cint(row.avaliacao_concluida):
		frappe.throw(_("Esta avaliação já foi respondida."))

	avaliacao_doc = frappe.get_doc("Avaliacao de Projeto", row.parent)
	target = None
	for individual in avaliacao_doc.avaliacoes_individuais or []:
		if individual.name == row.name:
			target = individual
			break

	if not target:
		frappe.throw(_("Avaliação individual não encontrada."))

	target.resultado_projeto = resultado_projeto
	target.satisfacao_colaboracao = satisfacao_colaboracao
	target.objetivos_atingidos = objetivos_atingidos
	target.muito_bom = muito_bom
	target.pontos_melhoria = pontos_melhoria
	target.avaliacao_concluida = 1

	all_done = all(cint(ind.avaliacao_concluida) for ind in avaliacao_doc.avaliacoes_individuais)
	if all_done:
		avaliacao_doc.status = "Avaliacoes individuais concluidas"

	avaliacao_doc.flags.ignore_validate = False
	avaliacao_doc.save(ignore_permissions=True)

	return {"ok": True}


def _get_project_goals(projeto: str) -> list[str]:
	doc = frappe.get_doc("Projeto", projeto)
	return [(row.objetivo or "").strip() for row in (doc.objetivos or []) if (row.objetivo or "").strip()]


def _get_allowed_reviewer_names(projeto: str) -> list[str]:
	doc = frappe.get_doc("Projeto", projeto)

	names = [
		(row.get("nome") or "").strip()
		for row in (doc.get("envolvidos") or [])
		if cint(row.get("participa_avaliacao")) and (row.get("nome") or "").strip()
	]

	return list(dict.fromkeys([name for name in names if name]))


def _get_all_reviewer_data(projeto_doc) -> list[dict[str, str]]:
	"""Retorna lista de {nome, email, telefone} para todos os envolvidos no projeto."""
	reviewers: list[dict[str, str]] = []
	seen_names: set[str] = set()
	for row in projeto_doc.get("envolvidos") or []:
		if not cint(row.get("participa_avaliacao")):
			continue

		nome = (row.get("nome") or "").strip()
		email = (row.get("email") or "").strip()
		telefone = (row.get("telefone") or "").strip()
		if nome and email and nome not in seen_names:
			reviewers.append({"nome": nome, "email": email, "telefone": telefone})
			seen_names.add(nome)

	return reviewers
