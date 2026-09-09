# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AgendadeVisitas(Document):
	def validate(self):
		self._garantir_visita_unica()

	def _garantir_visita_unica(self):
		"""Cada jovem tem no máximo uma visita agendada.

		Remarcar é alterar a data desta linha (ver ``gris.api.recepcao_visitas``). Enquanto
		reagendar inseria um registro novo, o antigo ficava parado na data velha e voltava a
		aparecer na mensagem de visitas do dia no grupo de chefes de seção.

		A trava mora no controller, e não só no serviço, porque Desk, MCP e portal escrevem
		aqui por caminhos diferentes.
		"""
		if not self.jovem:
			return

		if not frappe.db.exists(self.doctype, {"jovem": self.jovem, "name": ["!=", self.name]}):
			return

		nome = frappe.db.get_value("Novo Associado", self.jovem, "nome_completo") or self.jovem
		frappe.throw(
			_(
				"{0} já tem uma visita agendada. Altere a data da visita existente em vez de criar outra."
			).format(nome)
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
