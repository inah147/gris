# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

AREA_PORTARIA_NOME = "Portaria"


class AreadaFesta(Document):
	def validate(self):
		self._normalizar_coordenador()
		self._validar_portaria()

	def on_trash(self):
		if self.flags.get("from_festa_delete"):
			return
		if self.nome_area == AREA_PORTARIA_NOME:
			frappe.throw(
				_("A área Portaria é obrigatória e não pode ser excluída.")
			)

	def _normalizar_coordenador(self):
		if self.tipo_coord == "Associado":
			self.responsavel_coord = None
		elif self.tipo_coord == "Responsavel":
			self.associado_coord = None
		else:
			self.responsavel_coord = None
			self.associado_coord = None

	def _validar_portaria(self):
		if self.nome_area != AREA_PORTARIA_NOME:
			return
		if self.flags.get("in_portaria_auto_create"):
			return
		if self.tipo_coord == "Responsavel" and not self.responsavel_coord:
			frappe.throw(_("A área Portaria precisa de um coordenador responsável."))
		if self.tipo_coord == "Associado" and not self.associado_coord:
			frappe.throw(_("A área Portaria precisa de um coordenador associado."))
		if self.tipo_coord == "Outro" and not (
			self.nome_coord and self.email_coord and self.telefone_coord
		):
			frappe.throw(
				_(
					"A área Portaria precisa de coordenador com nome, e-mail e telefone preenchidos."
				)
			)
