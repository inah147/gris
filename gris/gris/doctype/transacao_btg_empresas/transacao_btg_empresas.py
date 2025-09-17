# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import hashlib

# import frappe
from frappe.model.document import Document


class TransacaoBTGEmpresas(Document):
	def before_insert(self):
		tx_id = f"{self.data}{self.valor}{self.saldo}{self.descricao}"

		tx_hash = hashlib.md5(tx_id.encode("utf-8")).hexdigest()

		self.id = f"BTGEmpresas-{tx_hash}"

	def after_insert(self):
		# Atualiza o saldo da conta bancária associada
		# bank_account = frappe.get_doc("Bank Account", self.bank_account)
		# bank_account.saldo_atual += self.valor
		# bank_account.save()
		pass
