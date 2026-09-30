# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from gris.api.google_workspace.project_drive import extract_drive_folder_id
from gris.gris.doctype.configuracoes_de_projetos.configuracoes_de_projetos import (
	_get_active_project_drive_map,
)


class ConfiguracoesdeCaptacao(Document):
	def validate(self):
		self._normalizar_pasta()
		self._validar_drive()

	def _normalizar_pasta(self):
		"""Aceita o link que a pessoa copia do navegador e guarda só o ID da pasta."""
		valor = (self.pasta_captacao or "").strip()
		if not valor:
			self.pasta_captacao = ""
			return
		if valor.startswith("http"):
			pasta_id = extract_drive_folder_id(valor)
			if not pasta_id:
				frappe.throw(_("Link da pasta do Google Drive inválido."))
			valor = pasta_id
		self.pasta_captacao = valor

	def _validar_drive(self):
		self.drive_compartilhado = (self.drive_compartilhado or "").strip()
		drives = _get_active_project_drive_map()
		if self.drive_compartilhado and self.drive_compartilhado not in drives:
			frappe.throw(
				_("Drive compartilhado inválido. Selecione um drive ativo em Configuracoes Google Workspace.")
			)
		if not cint(self.habilitar_pastas_drive):
			return
		if not self.drive_compartilhado:
			frappe.throw(_("Selecione o drive compartilhado dos projetos de captação."))
		if not self.pasta_captacao:
			frappe.throw(_("Informe a pasta dos projetos de captação."))


@frappe.whitelist()
def opcoes_de_drive() -> list[dict[str, str]]:
	if not frappe.has_permission("Configuracoes de Captacao", "read"):
		frappe.throw(_("Sem permissão para consultar as configurações de captação."), frappe.PermissionError)
	return [{"label": nome, "value": drive_id} for drive_id, nome in _get_active_project_drive_map().items()]
