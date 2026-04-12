# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

_CAMPOS_MONITORADOS = ("atividade", "inicio", "termino", "local", "secao", "nivel", "sem_atividade", "abertura_geral")


class Calendario(Document):
	def validate(self):
		if int(self.abertura_geral or 0):
			self.atividade = "Abertura Geral"

		if int(self.sem_atividade or 0) and int(self.abertura_geral or 0):
			frappe.throw(_("'Sem Atividade' e 'Abertura Geral' não podem ser marcados ao mesmo tempo."))

	def after_insert(self):
		self.flags.notificacao_enviada = True
		try:
			from gris.api.calendario_notificacoes import notificar_alteracao_calendario

			notificar_alteracao_calendario(
				evento_name=self.name,
				tipo_alteracao="criado",
				atividade=self.atividade or "",
				inicio=str(self.inicio) if self.inicio else "",
				secao=self.secao or "",
				local=self.local or "",
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Notificacao after_insert Calendario {self.name}")

	def on_update(self):
		if self.flags.get("notificacao_enviada"):
			return

		doc_antes = self.get_doc_before_save()
		if not doc_antes:
			return

		changed_fields = {}
		for campo in _CAMPOS_MONITORADOS:
			antes = doc_antes.get(campo)
			depois = self.get(campo)
			if str(antes or "") != str(depois or ""):
				changed_fields[campo] = (antes, depois)

		if not changed_fields:
			return

		try:
			from gris.api.calendario_notificacoes import notificar_alteracao_calendario

			notificar_alteracao_calendario(
				evento_name=self.name,
				tipo_alteracao="atualizado",
				atividade=self.atividade or "",
				inicio=str(self.inicio) if self.inicio else "",
				secao=self.secao or "",
				local=self.local or "",
				changed_fields=changed_fields,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Notificacao on_update Calendario {self.name}")

	def on_trash(self):
		try:
			from gris.api.calendario_notificacoes import notificar_alteracao_calendario

			notificar_alteracao_calendario(
				evento_name=self.name,
				tipo_alteracao="excluido",
				atividade=self.atividade or "",
				inicio=str(self.inicio) if self.inicio else "",
				secao=self.secao or "",
				local=self.local or "",
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Notificacao on_trash Calendario {self.name}")

