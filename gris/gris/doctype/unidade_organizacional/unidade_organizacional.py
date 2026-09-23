# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Categoria que nunca pode liderar uma área: beneficiário é assistido, não voluntário.
CATEGORIA_NAO_VOLUNTARIA = "Beneficiário"


class UnidadeOrganizacional(Document):
	def validate(self):
		self._validar_ciclo()
		self._validar_responsavel()

	def _validar_ciclo(self):
		"""Impede que a cadeia de `responde_para` volte para esta mesma área.

		O organograma percorre essa cadeia recursivamente; um ciclo trava a
		montagem da árvore, então barramos na gravação.
		"""
		if not self.responde_para:
			return

		if self.responde_para == self.name:
			frappe.throw(_("Uma área não pode responder para ela mesma."))

		visitados = {self.name}
		atual = self.responde_para
		while atual:
			if atual in visitados:
				frappe.throw(
					_("Hierarquia circular: {0} já responde, direta ou indiretamente, para {1}.").format(
						atual, self.name
					)
				)
			visitados.add(atual)
			atual = frappe.db.get_value("Unidade Organizacional", atual, "responde_para")

	def _validar_responsavel(self):
		if not self.responsavel:
			return

		categoria, status_no_grupo = frappe.db.get_value(
			"Associado", self.responsavel, ["categoria", "status_no_grupo"]
		) or (None, None)

		if categoria == CATEGORIA_NAO_VOLUNTARIA:
			frappe.throw(
				_("{0} tem categoria {1} e não pode ser responsável por uma área.").format(
					frappe.bold(self.responsavel), CATEGORIA_NAO_VOLUNTARIA
				)
			)

		if status_no_grupo == "Inativo":
			frappe.throw(
				_("{0} está inativo no grupo e não pode ser responsável por uma área.").format(
					frappe.bold(self.responsavel)
				)
			)
