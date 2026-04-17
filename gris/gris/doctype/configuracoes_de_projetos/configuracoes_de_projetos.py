# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

GOOGLE_SETTINGS_DOCTYPE = "Configuracoes Google Workspace"


class ConfiguracoesdeProjetos(Document):
	def validate(self):
		self._normalize_fields()
		self._validate_drive_selection()
		self._validate_required_fields_when_enabled()

	def _normalize_fields(self):
		self.drive_compartilhado_projetos = (self.drive_compartilhado_projetos or "").strip()
		self.pasta_projetos_id = (self.pasta_projetos_id or "").strip()

	def _validate_drive_selection(self):
		drive_map = _get_active_project_drive_map()

		if self.drive_compartilhado_projetos and self.drive_compartilhado_projetos not in drive_map:
			frappe.throw(
				_(
					"Drive compartilhado dos projetos invalido. Selecione um drive ativo em Configuracoes Google Workspace."
				)
			)

		if cint(self.habilitar_pastas_projetos_drive) and not drive_map:
			frappe.throw(
				_("Nao ha drives ativos em Configuracoes Google Workspace para habilitar pastas de projetos.")
			)

	def _validate_required_fields_when_enabled(self):
		if not cint(self.habilitar_pastas_projetos_drive):
			return

		if not self.drive_compartilhado_projetos:
			frappe.throw(_("Selecione o drive compartilhado dos projetos."))

		if not self.pasta_projetos_id:
			frappe.throw(_("Informe o ID da pasta de projetos."))


@frappe.whitelist()
def get_opcoes_drives_compartilhados_projetos() -> list[dict[str, str]]:
	if not frappe.has_permission("Configuracoes de Projetos", "read"):
		frappe.throw(_("Sem permissao para consultar configuracoes de projetos."), frappe.PermissionError)

	return [
		{"label": label, "value": drive_id} for drive_id, label in _get_active_project_drive_map().items()
	]


def _get_active_project_drive_map() -> dict[str, str]:
	if not frappe.db.exists("DocType", GOOGLE_SETTINGS_DOCTYPE):
		return {}

	try:
		google_settings = frappe.get_single(GOOGLE_SETTINGS_DOCTYPE)
	except Exception:
		return {}

	drive_map: dict[str, str] = {}
	for row in google_settings.drives_compartilhados or []:
		if not cint(row.ativo):
			continue
		drive_id = (row.drive_id or "").strip()
		nome_drive = (row.nome_drive or "").strip()
		if not drive_id or not nome_drive:
			continue
		drive_map[drive_id] = nome_drive

	return dict(sorted(drive_map.items(), key=lambda item: item[1].lower()))
