# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import hashlib
import re

import frappe
from frappe.model.document import Document


class TransacaoBTGEmpresas(Document):
	def before_insert(self):
		tx_id = f"{self.data_transacao}{self.valor}{self.saldo}{self.descricao}"

		tx_hash = hashlib.md5(tx_id.encode("utf-8")).hexdigest()

		self.id = f"BTGEmpresas-{tx_hash}"

	def after_insert(self):
		# get method
		method = None
		if (self.descricao or "").lower().startswith("pix "):
			method = "Pix"

		# get destination and source
		destination = None
		source = None
		if self.valor < 0:
			source = "Grupo Escoteiro Professora Inah De Melo N 147. - BTG Empresas"
			_, _, destination = (self.descricao or "").partition(" para ")
		else:
			destination = "Grupo Escoteiro Professora Inah De Melo N 147. - BTG Empresas"
			m = re.search(r"\brecebid[oa]\s+de\b", (self.descricao or ""), flags=re.IGNORECASE)
			if m:
				source = self.descricao[m.end() :].strip() or None

		tx = frappe.get_doc(
			{
				"doctype": "Transacao Extrato Geral",
				"id": self.id,
				"data_transacao": self.data_transacao,
				"descricao": self.descricao,
				"valor": self.valor,
				"valor_absoluto": abs(self.valor),
				"debito_credito": "Crédito" if self.valor > 0 else "Débito",
				"metodo": method,
				"origem": source,
				"destino": destination,
				"instituicao": "BTG Empresas",
				"centro_de_custo": "Presidência",
				"carteira": "BTG Empresas",
			}
		)
		tx.insert()
		pass
