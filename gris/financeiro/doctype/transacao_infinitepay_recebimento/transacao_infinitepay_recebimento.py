# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import hashlib

# import re
import frappe
from frappe.model.document import Document


class TransacaoInfinitepayrecebimento(Document):
	def before_insert(self):
		tx_id = f"{self.infinite_id}{self.data_venda}{self.total_parcelas}{self.numero_parcela}{self.numero_liquidacao}"

		tx_hash = hashlib.md5(tx_id.encode("utf-8")).hexdigest()

		self.id = f"IntiniepayRecebimento-{tx_hash}"
