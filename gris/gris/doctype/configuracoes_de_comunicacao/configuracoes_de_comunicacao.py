# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

CAMPOS_DE_DOCUMENTO = (
	("link_papel_timbrado", "Link do papel timbrado inválido. Cole o endereço do documento no Google Docs."),
)


class ConfiguracoesdeComunicacao(Document):
	def validate(self):
		# Import tardio: o parser vive no módulo de Drive, que carrega a googleapiclient.
		# Um DocType não pode deixar de abrir no Desk por causa de uma dependência de integração.
		from gris.api.google_workspace.recepcao_drive import extract_google_doc_id

		for campo, mensagem in CAMPOS_DE_DOCUMENTO:
			valor = (self.get(campo) or "").strip()
			self.set(campo, valor)

			if valor and not extract_google_doc_id(valor):
				frappe.throw(_(mensagem))
