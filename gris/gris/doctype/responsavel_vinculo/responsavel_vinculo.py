# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

# import frappe
import hashlib

from frappe.model.document import Document


class ResponsavelVinculo(Document):
	def autoname(self):
		self.name = (
			(self.responsavel or "")
			+ (self.beneficiario_associado or "")
			+ (self.beneficiario_novo_associado or "")
		)
