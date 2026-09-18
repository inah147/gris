# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CalendarioSimulado(Document):
	def validate(self):
		if int(self.abertura_geral or 0):
			self.atividade = "Abertura Geral"
			# Mesma coerência do Calendario oficial: a abertura geral já libera o dia.
			self.permite_visita_novos_associados = 0

		if int(self.sem_atividade or 0) and int(self.abertura_geral or 0):
			frappe.throw(_("'Sem Atividade' e 'Abertura Geral' não podem ser marcados ao mesmo tempo."))

		if int(self.sem_atividade or 0) and int(self.permite_visita_novos_associados or 0):
			frappe.throw(
				_(
					"'Sem Atividade' e 'Permite Visita de Novos Associados' não podem ser marcados ao mesmo tempo."
				)
			)
