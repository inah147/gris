# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AgendadeVisitas(Document):
	def after_insert(self):
		"""Notifica o responsável via WhatsApp ao agendar uma visita."""
		try:
			from gris.api.recepcao_notificacoes import notificar_visita_agendada

			notificar_visita_agendada(self.jovem, str(self.data_da_visita))
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"after_insert Agenda de Visitas: {self.name}",
			)
