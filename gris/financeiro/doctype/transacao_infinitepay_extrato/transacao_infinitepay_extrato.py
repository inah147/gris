# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
import hashlib

# import frappe
from frappe.model.document import Document


class TransacaoInfinitepayextrato(Document):
	def before_insert(self):
		pass
		# tx_id = f"{self.data_transacao}{self.tipo_transacao}{self.nome_transacao}{self.detalhe}{self.valor}"

		# tx_hash = hashlib.md5(tx_id.encode("utf-8")).hexdigest()

		# self.id = f"IntiniepayExtrato-{tx_hash}"
