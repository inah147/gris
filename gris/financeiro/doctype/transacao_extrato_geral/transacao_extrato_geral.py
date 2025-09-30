# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TransacaoExtratoGeral(Document):
	def _update_wallet(self):
		if self.carteira:
			# 1. Somar o valor de cada transação da carteira no Transacao Extrato Geral
			total = frappe.db.get_value(
				"Transacao Extrato Geral",
				filters={"carteira": self.carteira},
				fieldname=["sum(valor) as total"],
				as_dict=True,
			)
			total_valor = total["total"] if total and total["total"] else 0

			# 2. Atualizar o saldo da carteira no doctype Carteira
			frappe.db.set_value("Carteira", self.carteira, "saldo", total_valor)
			frappe.db.commit()

	def after_insert(self):
		self._update_wallet()

	def after_update(self):
		self._update_wallet()

	def after_delete(self):
		self._update_wallet()
