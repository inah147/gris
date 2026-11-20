# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from gris.api.associados_vencimento_modelos import validar_configuracoes


class ConfiguracoesdeAssociados(Document):
	def validate(self):
		validar_configuracoes(self)
