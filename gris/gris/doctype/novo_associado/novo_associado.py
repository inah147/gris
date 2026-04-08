# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import hashlib
import re

import frappe
from frappe.model.document import Document


class NovoAssociado(Document):
	def autoname(self):
		if self.cpf:
			cpf_clean = re.sub(r"\D", "", self.cpf)
			self.name = hashlib.md5(cpf_clean.encode("utf-8")).hexdigest()

	def on_trash(self):
		"""Limpa referências em Responsavel Vinculo ao excluir Novo Associado."""
		vinculos = frappe.get_all(
			"Responsavel Vinculo",
			filters={"beneficiario_novo_associado": self.name},
			pluck="name",
		)
		for vinculo_name in vinculos:
			frappe.db.set_value(
				"Responsavel Vinculo", vinculo_name, "beneficiario_novo_associado", None
			)
