# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.model.document import Document
from frappe.utils import formatdate


class Assembleia(Document):
	def validate(self):
		self.titulo = f"Assembleia {self.tipo} — {formatdate(self.data, 'dd/MM/yyyy')}" if self.data else ""
