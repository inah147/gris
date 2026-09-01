# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

GOOGLE_SETTINGS_DOCTYPE = "Configuracoes Google Workspace"

# Pastas do Drive exigidas quando o envio de documentos está habilitado.
CAMPOS_DE_PASTA = (
	("pasta_documentos_identificacao_id", "Informe o ID da pasta de documentos de identificação."),
	(
		"pasta_declaracoes_nao_assinadas_id",
		"Informe o ID da pasta de declarações de idoneidade não assinadas.",
	),
	(
		"pasta_declaracoes_assinadas_id",
		"Informe o ID da pasta de declarações de idoneidade assinadas.",
	),
)


class ConfiguracoesdeRecepcao(Document):
	def validate(self):
		self._normalize_fields()
		self._validate_drive_selection()
		self._validate_required_fields_when_enabled()
		self._validate_template_declaracao()

	def _normalize_fields(self):
		self.drive_compartilhado_acesso_restrito = (self.drive_compartilhado_acesso_restrito or "").strip()
		self.link_template_declaracao_idoneidade = (self.link_template_declaracao_idoneidade or "").strip()
		for campo, _mensagem in CAMPOS_DE_PASTA:
			self.set(campo, (self.get(campo) or "").strip())

	def _validate_template_declaracao(self):
		if not self.link_template_declaracao_idoneidade:
			return

		# Import tardio: o parser vive no módulo de Drive, que carrega a googleapiclient.
		# Um DocType não pode deixar de abrir no Desk por causa de uma dependência de integração.
		from gris.api.google_workspace.recepcao_drive import extract_google_doc_id

		if not extract_google_doc_id(self.link_template_declaracao_idoneidade):
			frappe.throw(
				_(
					"Link do modelo da declaração de idoneidade inválido. "
					"Cole o endereço do documento no Google Docs."
				)
			)

	def _validate_drive_selection(self):
		drive_map = _get_active_reception_drive_map()

		if (
			self.drive_compartilhado_acesso_restrito
			and self.drive_compartilhado_acesso_restrito not in drive_map
		):
			frappe.throw(
				_(
					"Drive compartilhado de acesso restrito inválido. Selecione um drive ativo em Configuracoes Google Workspace."
				)
			)

		if cint(self.habilitar_documentos_drive) and not drive_map:
			frappe.throw(
				_(
					"Não há drives ativos em Configuracoes Google Workspace para habilitar o envio de documentos."
				)
			)

	def _validate_required_fields_when_enabled(self):
		if not cint(self.habilitar_documentos_drive):
			return

		if not self.drive_compartilhado_acesso_restrito:
			frappe.throw(_("Selecione o drive compartilhado de acesso restrito."))

		for campo, mensagem in CAMPOS_DE_PASTA:
			if not self.get(campo):
				frappe.throw(_(mensagem))


@frappe.whitelist()
def get_opcoes_drives_compartilhados_recepcao() -> list[dict[str, str]]:
	if not frappe.has_permission("Configuracoes de Recepcao", "read"):
		frappe.throw(_("Sem permissão para consultar configurações de recepção."), frappe.PermissionError)

	return [
		{"label": label, "value": drive_id} for drive_id, label in _get_active_reception_drive_map().items()
	]


def _get_active_reception_drive_map() -> dict[str, str]:
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
