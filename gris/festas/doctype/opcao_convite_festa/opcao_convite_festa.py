# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class OpcaoConviteFesta(Document):
	def validate(self):
		self._validar_nome_unico_por_festa()

	def _validar_nome_unico_por_festa(self):
		if not self.festa or not self.nome_convite:
			return
		nome_esperado = f"{self.festa} - {self.nome_convite}"
		# Em edição: se o name não muda, é o mesmo registro.
		if not self.is_new() and self.name == nome_esperado:
			return
		if frappe.db.exists("Opcao Convite Festa", nome_esperado):
			frappe.throw(
				_("Já existe uma opção de convite com este nome para a festa selecionada.")
			)
