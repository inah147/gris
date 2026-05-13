# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AreadaFesta(Document):
	def validate(self):
		self._normalizar_coordenador()

	def _normalizar_coordenador(self):
		if self.tipo_coord == "Associado":
			self.responsavel_coord = None
		elif self.tipo_coord == "Responsavel":
			self.associado_coord = None
		else:
			self.responsavel_coord = None
			self.associado_coord = None
