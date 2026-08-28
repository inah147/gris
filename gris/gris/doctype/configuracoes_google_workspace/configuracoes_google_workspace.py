# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from frappe import _
from frappe.model.document import Document


class ConfiguracoesGoogleWorkspace(Document):
	def validate(self):
		self._normalize_domain()
		self._validate_expiration_days()

	def _normalize_domain(self):
		domain = (self.dominio_institucional or "").strip().lower()
		if domain.startswith("@"):
			domain = domain[1:]

		self.dominio_institucional = domain or "escoteiros.org.br"

	def _validate_expiration_days(self):
		if self.dias_expiracao_acesso_restrito and self.dias_expiracao_acesso_restrito < 1:
			import frappe

			frappe.throw(_("Dias para expiração do acesso restrito deve ser maior que zero."))
