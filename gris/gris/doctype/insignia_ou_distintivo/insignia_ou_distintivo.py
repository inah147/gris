# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InsigniaouDistintivo(Document):
	def validate(self):
		self.nome = (self.nome or "").strip()
		if not self.nome:
			frappe.throw("Informe o nome da insígnia ou distintivo.")

		self.codigo = (self.codigo or "").strip() or None

		if self.valor_unitario and self.valor_unitario < 0:
			frappe.throw("O valor unitário não pode ser negativo.")
