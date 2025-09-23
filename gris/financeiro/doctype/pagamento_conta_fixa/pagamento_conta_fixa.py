# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from datetime import datetime

import frappe
from frappe.model.document import Document

PORTUGUESE_MONTHS = [
	"janeiro",
	"fevereiro",
	"março",
	"abril",
	"maio",
	"junho",
	"julho",
	"agosto",
	"setembro",
	"outubro",
	"novembro",
	"dezembro",
]


def _format_reference_month(date_value) -> str | None:
	"""Return month name in Portuguese + year (e.g., 'março de 2025').

	Accepts date, datetime or string (YYYY-MM-DD). Returns None if invalid.
	"""
	if not date_value:
		return None
	try:
		if isinstance(date_value, str):
			# Try parse ISO (YYYY-MM-DD)
			parsed = datetime.strptime(date_value, "%Y-%m-%d")
		else:
			parsed = date_value
		month_idx = parsed.month - 1
		if 0 <= month_idx < 12:
			return f"{PORTUGUESE_MONTHS[month_idx]} de {parsed.year}"
	except Exception:
		return None
	return None


class PagamentoContaFixa(Document):
	def validate(self):
		self._set_title()

	def before_insert(self):  # redundancy ensures title is set early for naming if needed
		self._set_title()

	def _set_title(self):
		"""Compose title as 'conta - mês de ano'. Only if conta & mes_referencia present."""
		account = getattr(self, "conta", None)
		ref = getattr(self, "mes_referencia", None)
		if not account or not ref:
			return
		formatted = _format_reference_month(ref)
		if formatted:
			self.titulo = f"{account} - {formatted}"
