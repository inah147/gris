# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from gris.api.acessos.constantes import (
	ACESSO_DOCTYPE,
	LICENCA_ATIVA,
	LICENCA_DOCTYPE,
	LICENCA_REVOGACAO_PENDENTE,
	LICENCA_REVOGADA,
	TIPO_FERRAMENTA,
)


class LicencadeFerramenta(Document):
	def validate(self):
		self._validar_ferramenta()
		self._preencher_titular()
		self._validar_transicao()
		self._carimbar_status()
		self._validar_unica()

	def _validar_ferramenta(self):
		if frappe.db.get_value(ACESSO_DOCTYPE, self.acesso, "tipo") != TIPO_FERRAMENTA:
			frappe.throw(_("Licenças só existem para acessos do tipo {0}.").format(TIPO_FERRAMENTA))

	def _preencher_titular(self):
		"""A conta na ferramenta é sempre o id@escoteiros do associado."""
		associado = frappe.db.get_value(
			"Associado", self.associado, ["nome_completo", "id_escoteiros"], as_dict=True
		)
		if not associado:
			frappe.throw(_("Associado {0} não encontrado.").format(self.associado))

		self.nome = associado.nome_completo
		email = (associado.id_escoteiros or "").strip().lower()
		if email:
			self.email = email
		if not self.email:
			frappe.throw(
				_("{0} não tem id@escoteiros: a conta na ferramenta precisa dele.").format(self.nome)
			)
		self.usuario = self.email if frappe.db.exists("User", self.email) else None

	def _validar_transicao(self):
		anterior = None if self.is_new() else self.get_doc_before_save()
		if anterior and anterior.status == LICENCA_REVOGADA and self.status != LICENCA_REVOGADA:
			frappe.throw(_("Uma licença revogada não volta: registre uma nova licença."))

	def _carimbar_status(self):
		agora = now_datetime()
		if self.status == LICENCA_ATIVA:
			if not self.concedida_em:
				self.concedida_em = agora
			if not self.concedida_por:
				self.concedida_por = frappe.session.user
			# Voltou a valer (ex.: reativação antes da revogação): o pendente sai de cena.
			self.revogacao_pendente_desde = None
			self.motivo_revogacao = None
			self.aviso_tecnologia_enviado_em = None
		elif self.status == LICENCA_REVOGACAO_PENDENTE:
			if not self.revogacao_pendente_desde:
				self.revogacao_pendente_desde = agora
		elif self.status == LICENCA_REVOGADA:
			if not self.revogada_em:
				self.revogada_em = agora
			if not self.revogada_por:
				self.revogada_por = frappe.session.user

	def _validar_unica(self):
		if self.status == LICENCA_REVOGADA:
			return
		outra = frappe.db.get_value(
			LICENCA_DOCTYPE,
			{
				"acesso": self.acesso,
				"associado": self.associado,
				"status": ["!=", LICENCA_REVOGADA],
				"name": ["!=", self.name or ""],
			},
			"name",
		)
		if outra:
			frappe.throw(_("{0} já tem uma licença desta ferramenta ({1}).").format(self.nome, outra))
