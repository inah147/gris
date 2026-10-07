# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_fullname

from gris.api.acessos.constantes import SECAO_DOCTYPE
from gris.utils.chefes import normalizar_texto


class AcessoporSecao(Document):
	def validate(self):
		self.secao = " ".join((self.secao or "").split())
		if not self.secao:
			frappe.throw(_("Informe a seção."))
		self.nome = get_fullname(self.usuario) or self.usuario
		self._garantir_unica()

	def _garantir_unica(self):
		"""Uma linha por pessoa, papel e seção — a mesma seção escrita de outro jeito conta."""
		alvo = normalizar_texto(self.secao)
		outras = frappe.get_all(
			SECAO_DOCTYPE,
			filters={"usuario": self.usuario, "papel": self.papel, "name": ["!=", self.name or ""]},
			pluck="secao",
		)
		if any(normalizar_texto(secao) == alvo for secao in outras):
			frappe.throw(_("{0} já tem a seção {1}.").format(self.nome, self.secao))
