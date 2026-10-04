# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

AREA_PROGRAMA_EDUCATIVO = "Programa Educativo"


class ItemdeCatalogodeCompras(Document):
	def validate(self):
		self.nome = (self.nome or "").strip()
		if not self.nome:
			frappe.throw(_("Informe o nome do item."))

		self.codigo = (self.codigo or "").strip() or None

		if self.valor_unitario and self.valor_unitario < 0:
			frappe.throw(_("O valor unitário não pode ser negativo."))

		# Tipo e ramo descrevem insígnias e distintivos. Nas outras áreas não têm
		# sentido, e um valor herdado (o default "Todos" do ramo) só confundiria a lista.
		if self.area != AREA_PROGRAMA_EDUCATIVO:
			self.tipo = None
			self.ramo = None
