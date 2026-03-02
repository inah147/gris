# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Calendario(Document):
	def validate(self):
		if int(self.abertura_geral or 0):
			self.atividade = "Abertura Geral"

		if int(self.sem_atividade or 0) and int(self.abertura_geral or 0):
			frappe.throw(_("'Sem Atividade' e 'Abertura Geral' não podem ser marcados ao mesmo tempo."))
