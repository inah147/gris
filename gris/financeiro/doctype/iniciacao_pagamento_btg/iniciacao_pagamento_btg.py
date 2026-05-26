# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import uuid

import frappe
from frappe.model.document import Document


class IniciacaoPagamentoBTG(Document):
	def before_insert(self):
		if not self.idempotency_key:
			self.idempotency_key = str(uuid.uuid4())

	def on_submit(self):
		"""Ao submeter, envia o pagamento para a API BTG."""
		from gris.api.financeiro.btg_payments import iniciar_pagamento

		iniciar_pagamento(self.name)
