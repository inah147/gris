# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Registro de uma execucao de job (agendado, enfileirado ou manual)."""

from __future__ import annotations

import json

import frappe
from frappe.model.document import Document


class LogdeExecucaodeJob(Document):
	def get_eventos(self) -> list[dict]:
		"""Retorna a linha do tempo da execucao ja desserializada."""
		if not self.eventos:
			return []

		try:
			eventos = json.loads(self.eventos)
		except (ValueError, TypeError):
			return []

		return eventos if isinstance(eventos, list) else []

	def get_metricas(self) -> dict:
		"""Retorna os contadores registrados pelo job."""
		if not self.metricas:
			return {}

		try:
			metricas = json.loads(self.metricas)
		except (ValueError, TypeError):
			return {}

		return metricas if isinstance(metricas, dict) else {}
