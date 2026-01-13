# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

# import frappe
import hashlib
import re

from frappe.model.document import Document


class Responsavel(Document):
	def autoname(self):
		if self.cpf:
			cpf_clean = re.sub(r"\D", "", self.cpf)
			self.name = hashlib.md5(cpf_clean.encode("utf-8")).hexdigest()
