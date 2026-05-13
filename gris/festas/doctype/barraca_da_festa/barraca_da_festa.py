# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class BarracadaFesta(Document):
	def validate(self):
		self._validar_area()
		self._normalizar_coordenador()

	def on_update(self):
		self._reagregar_festa()

	def on_trash(self):
		self._reagregar_festa()

	def _reagregar_festa(self):
		if not self.festa:
			return
		try:
			festa_doc = frappe.get_doc("Festa", self.festa)
			festa_doc.save(ignore_permissions=True)
		except frappe.DoesNotExistError:
			return

	def _validar_area(self):
		if not self.area:
			frappe.throw(_("Selecione a area da barraca."))
		festa_da_area = frappe.db.get_value("Area da Festa", self.area, "festa")
		if festa_da_area != self.festa:
			frappe.throw(_("A area selecionada nao pertence a esta festa."))

	def _normalizar_coordenador(self):
		if self.tipo_coord == "Associado":
			self.responsavel_coord = None
		elif self.tipo_coord == "Responsavel":
			self.associado_coord = None
		else:
			self.responsavel_coord = None
			self.associado_coord = None
