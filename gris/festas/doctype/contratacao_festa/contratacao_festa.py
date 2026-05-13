# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ContratacaoFesta(Document):
	def validate(self):
		self._validar_area()
		self._validar_cotacoes()
		self._calcular_valor_total()

	def on_update(self):
		self._reagregar_festa()

	def on_trash(self):
		self._reagregar_festa()

	def _validar_area(self):
		if not self.area:
			return
		festa_da_area = frappe.db.get_value("Area da Festa", self.area, "festa")
		if festa_da_area and festa_da_area != self.festa:
			frappe.throw(_("A area selecionada nao pertence a esta festa."))

	def _validar_cotacoes(self):
		escolhidas = [c for c in self.cotacoes or [] if c.escolhida]
		if len(escolhidas) > 1:
			frappe.throw(_("Apenas uma cotacao pode ser marcada como escolhida."))

	def _cotacao_escolhida(self):
		for c in self.cotacoes or []:
			if c.escolhida:
				return c
		return None

	def _calcular_valor_total(self):
		escolhida = self._cotacao_escolhida()
		if not escolhida:
			self.valor_total_contratacao = 0
			return
		self.valor_total_contratacao = flt(escolhida.valor)

	def _reagregar_festa(self):
		if not self.festa:
			return
		try:
			festa_doc = frappe.get_doc("Festa", self.festa)
			festa_doc.save(ignore_permissions=True)
		except frappe.DoesNotExistError:
			return
