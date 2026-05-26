# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CobrancaBTG(Document):
	def after_insert(self):
		"""Ao criar uma cobrança, envia para a API BTG automaticamente."""
		from gris.api.financeiro.btg_cobrancas import criar_cobranca

		try:
			criar_cobranca(self.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"BTG Criar Cobrança: {self.name}")
			# Não bloqueia o insert; o operador pode retentar manualmente
