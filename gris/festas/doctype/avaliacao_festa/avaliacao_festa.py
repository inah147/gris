from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

VALID_RATING_OPTIONS = {str(i) for i in range(11)}


class AvaliacaoFesta(Document):
	def validate(self):
		self._validate_festa()
		self._ensure_token_convidado()
		self._calculate_review_metrics()

	def _validate_festa(self):
		if not self.festa:
			frappe.throw(_("Festa é obrigatória."))
		if not frappe.db.exists("Festa", self.festa):
			frappe.throw(_("Festa informada não existe."))

	def _ensure_token_convidado(self):
		if not self.token_convidado:
			self.token_convidado = frappe.generate_hash(length=32)

	def _calculate_review_metrics(self):
		results: list[int] = []
		satisfaction: list[int] = []
		for ind in self.avaliacoes_individuais or []:
			# Só linhas efetivamente respondidas entram nas métricas. As pendentes
			# carregam o placeholder "0" do campo Select (resultado_festa/
			# satisfacao_colaboracao) e distorceriam a média — espelha o tratamento
			# de _serialize_avaliacao, que também só considera linhas concluídas.
			if not cint(ind.avaliacao_concluida):
				continue
			if ind.resultado_festa is not None and str(ind.resultado_festa) != "":
				results.append(cint(ind.resultado_festa))
			if ind.satisfacao_colaboracao is not None and str(ind.satisfacao_colaboracao) != "":
				satisfaction.append(cint(ind.satisfacao_colaboracao))

		self.avaliacao_geral = round(sum(results) / len(results), 2) if results else 0
		if satisfaction:
			promoters = sum(1 for value in satisfaction if value >= 9)
			detractors = sum(1 for value in satisfaction if value <= 6)
			self.satisfacao_dos_participantes = round((promoters - detractors) / len(satisfaction), 4)
		else:
			self.satisfacao_dos_participantes = 0

		recomendacoes = [
			cint(c.recomendacao)
			for c in self.avaliacoes_convidados or []
			if c.recomendacao is not None and str(c.recomendacao) != ""
		]
		self.recomendacao_media_convidados = (
			round(sum(recomendacoes) / len(recomendacoes), 2) if recomendacoes else 0
		)


@frappe.whitelist(allow_guest=True)
def get_avaliacao_individual_festa_por_token(token: str) -> dict[str, Any]:
	"""Retorna dados mínimos de uma avaliação individual via token único (público)."""
	token = (token or "").strip()
	if not token or len(token) < 16:
		frappe.throw(_("Link de avaliação inválido."))

	row = frappe.db.get_value(
		"Avaliacao Individual Festa",
		{"token": token},
		["name", "parent", "avaliador", "avaliacao_concluida"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Link de avaliação inválido ou expirado."))

	festa_name = frappe.db.get_value("Avaliacao Festa", row.parent, "festa")
	festa_titulo = ""
	if festa_name:
		festa_titulo = frappe.db.get_value("Festa", festa_name, "nome_festa") or festa_name

	return {
		"ok": True,
		"avaliador": row.avaliador,
		"festa_titulo": festa_titulo,
		"avaliacao_concluida": cint(row.avaliacao_concluida),
	}


@frappe.whitelist(allow_guest=True)
def submeter_avaliacao_individual_festa(
	token: str,
	resultado_festa: str,
	satisfacao_colaboracao: str,
	muito_bom: str,
	pontos_melhoria: str,
) -> dict[str, Any]:
	"""Permite que um membro da equipe submeta sua avaliação via token único (público).

	Justificativa para allow_guest e ignore_permissions: endpoint público com acesso
	controlado exclusivamente por token único e não-reutilizável.
	"""
	token = (token or "").strip()
	if not token or len(token) < 16:
		frappe.throw(_("Link de avaliação inválido."))

	resultado_festa = (resultado_festa or "").strip()
	satisfacao_colaboracao = (satisfacao_colaboracao or "").strip()
	muito_bom = (muito_bom or "").strip()
	pontos_melhoria = (pontos_melhoria or "").strip()

	if resultado_festa not in VALID_RATING_OPTIONS:
		frappe.throw(_("Resultado da festa deve ser um valor de 0 a 10."))
	if satisfacao_colaboracao not in VALID_RATING_OPTIONS:
		frappe.throw(_("Satisfação deve ser um valor de 0 a 10."))
	if not muito_bom:
		frappe.throw(_("Preencha o que foi muito bom na festa."))
	if not pontos_melhoria:
		frappe.throw(_("Preencha os pontos de melhoria."))

	row = frappe.db.get_value(
		"Avaliacao Individual Festa",
		{"token": token},
		["name", "parent", "avaliacao_concluida"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Link de avaliação inválido ou expirado."))

	if cint(row.avaliacao_concluida):
		frappe.throw(_("Esta avaliação já foi respondida."))

	avaliacao_doc = frappe.get_doc("Avaliacao Festa", row.parent)
	target = None
	for individual in avaliacao_doc.avaliacoes_individuais or []:
		if individual.name == row.name:
			target = individual
			break

	if not target:
		frappe.throw(_("Avaliação individual não encontrada."))

	target.resultado_festa = resultado_festa
	target.satisfacao_colaboracao = satisfacao_colaboracao
	target.muito_bom = muito_bom
	target.pontos_melhoria = pontos_melhoria
	target.avaliacao_concluida = 1

	all_done = all(cint(ind.avaliacao_concluida) for ind in avaliacao_doc.avaliacoes_individuais)
	if all_done:
		avaliacao_doc.status = "Avaliacoes individuais concluidas"

	avaliacao_doc.save(ignore_permissions=True)

	return {"ok": True}


@frappe.whitelist(allow_guest=True)
def get_festa_convidado_por_token(token: str) -> dict[str, Any]:
	"""Valida o token público de convidados e retorna o título da festa."""
	token = (token or "").strip()
	if not token or len(token) < 16:
		frappe.throw(_("Link de avaliação inválido."))

	row = frappe.db.get_value("Avaliacao Festa", {"token_convidado": token}, ["name", "festa"], as_dict=True)
	if not row:
		frappe.throw(_("Link de avaliação inválido ou expirado."))

	festa_titulo = frappe.db.get_value("Festa", row.festa, "nome_festa") or row.festa
	return {"ok": True, "festa_titulo": festa_titulo}


@frappe.whitelist(allow_guest=True)
def submeter_avaliacao_convidado(
	token: str,
	recomendacao: str,
	mais_gostou: str,
	pode_melhorar: str,
	email: str | None = None,
) -> dict[str, Any]:
	"""Registra a avaliação anônima de um convidado via token público da festa.

	Justificativa para allow_guest e ignore_permissions: coleta pública controlada
	por token único da festa. O e-mail é opcional; quando informado, impede respostas
	duplicadas para o mesmo e-mail nesta festa.
	"""
	token = (token or "").strip()
	if not token or len(token) < 16:
		frappe.throw(_("Link de avaliação inválido."))

	recomendacao = (str(recomendacao) if recomendacao is not None else "").strip()
	mais_gostou = (mais_gostou or "").strip()
	pode_melhorar = (pode_melhorar or "").strip()
	email = (email or "").strip().lower()

	if recomendacao not in VALID_RATING_OPTIONS:
		frappe.throw(_("A recomendação deve ser um valor de 0 a 10."))
	if not mais_gostou:
		frappe.throw(_("Conte o que você mais gostou na festa."))
	if not pode_melhorar:
		frappe.throw(_("Conte o que você acha que pode melhorar."))

	row = frappe.db.get_value("Avaliacao Festa", {"token_convidado": token}, ["name"], as_dict=True)
	if not row:
		frappe.throw(_("Link de avaliação inválido ou expirado."))

	avaliacao_doc = frappe.get_doc("Avaliacao Festa", row.name)

	if email:
		for convidado in avaliacao_doc.avaliacoes_convidados or []:
			if (convidado.email or "").strip().lower() == email:
				return {"ok": False, "duplicate": True}

	avaliacao_doc.append(
		"avaliacoes_convidados",
		{
			"email": email,
			"recomendacao": cint(recomendacao),
			"mais_gostou": mais_gostou,
			"pode_melhorar": pode_melhorar,
		},
	)
	avaliacao_doc.save(ignore_permissions=True)

	return {"ok": True}
