# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import formatdate

from gris.api.assembleias import constantes as c
from gris.api.assembleias.padroes import segunda_convocacao

DOCTYPES_DE_INSCRICAO = (c.DOCTYPE_CANDIDATURA, c.DOCTYPE_CHAPA, c.DOCTYPE_ASSUNTO)


class Assembleia(Document):
	def validate(self):
		self.titulo = f"Assembleia {self.tipo} — {formatdate(self.data, 'dd/MM/yyyy')}" if self.data else ""
		if self.hora_primeira_convocacao and not self.hora_segunda_convocacao:
			self.hora_segunda_convocacao = segunda_convocacao(self.hora_primeira_convocacao)
		self._validar_dia_livre()

	def _validar_dia_livre(self):
		# O índice único em `data` daria um DuplicateEntryError sem explicação.
		outra = frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, {"data": self.data, "name": ["!=", self.name]})
		if outra:
			frappe.throw(_("Já existe uma assembleia em {0}.").format(formatdate(self.data, "dd/MM/yyyy")))

	def on_trash(self):
		if self.edital_publicado and "System Manager" not in frappe.get_roles():
			frappe.throw(
				_("O edital já foi publicado. Para excluir, fale com o administrador do sistema."),
				frappe.PermissionError,
			)
		apagar_inscricoes(self.name)


def apagar_inscricoes(assembleia: str) -> None:
	"""Candidaturas, chapas e assuntos gerais da assembleia (CA-02.7).

	`ignore_permissions`: os DocTypes de inscrição só são gravados pelos formulários, e
	quem gerencia a assembleia não tem `delete` neles. Quem chegou aqui já passou pela
	permissão de excluir a assembleia.
	"""
	for doctype in DOCTYPES_DE_INSCRICAO:
		for name in frappe.get_all(doctype, filters={"assembleia": assembleia}, pluck="name"):
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
