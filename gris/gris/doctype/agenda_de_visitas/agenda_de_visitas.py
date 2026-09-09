# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AgendadeVisitas(Document):
	def validate(self):
		"""Garante no máximo um registro de visita agendada por jovem (SUG-00046).

		Sem esta trava, um cadastro criado sem passar pelo fluxo de reagendamento
		(que atualiza a data no registro existente) deixaria um registro antigo
		órfão no banco — e ele reaparece na mensagem diária de visitas do dia se
		a data antiga voltar a bater com "hoje".
		"""
		if not self.jovem:
			return

		duplicada = frappe.db.exists("Agenda de Visitas", {"jovem": self.jovem, "name": ["!=", self.name]})
		if duplicada:
			frappe.throw(
				frappe._(
					"Já existe uma visita agendada para este jovem ({0}). "
					"Remarque a visita existente em vez de criar uma nova."
				).format(duplicada)
			)

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
