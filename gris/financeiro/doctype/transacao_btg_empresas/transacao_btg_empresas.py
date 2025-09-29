# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import hashlib
import re

import frappe
from frappe.model.document import Document


class TransacaoBTGEmpresas(Document):
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

		if self.descricao in (
			"Crédito na Conta Corrente",
			"Resgate Conta Remunerada",
			"Aplicação Conta Remunerada",
			"Débito na Conta Corrente",
		):
			is_internal_tx = 1
		else:
			is_internal_tx = 0

		tx = frappe.get_doc(
			{
				"doctype": "Transacao Extrato Geral",
				"id": self.id,
				"timestamp_transacao": self.data_transacao,
				"data_transacao": self.data_transacao,
				"data_deposito": self.data_transacao,
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
				"repasse_entre_contas": is_internal_tx,
			}
		)
		tx.insert()
		pass
