# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from gris.api.acessos.constantes import (
	ACESSO_DOCTYPE,
	PAPEIS_PROTEGIDOS,
	ROLE_GESTOR,
	TIPO_DRIVE,
	TIPO_FERRAMENTA,
	TIPO_PAPEL,
)
from gris.api.acessos.permissoes import papel_aprovador_padrao

CAMPOS_DE_DRIVE = ("drive_id", "nome_drive")


class Acesso(Document):
	def validate(self):
		self.titulo = (self.titulo or "").strip()
		self.icone = (self.icone or "").strip() or None

		if self.tipo == TIPO_PAPEL:
			self._validar_papel()
		elif self.tipo == TIPO_DRIVE:
			self._validar_drive()
		else:
			self.papel = None
			for campo in CAMPOS_DE_DRIVE:
				self.set(campo, None)

		if self.tipo != TIPO_FERRAMENTA:
			self.limite_licencas = 0
			self.instrucoes_concessao = None

		self._garantir_etapa_padrao()
		self._validar_etapas()

	def _garantir_etapa_padrao(self):
		"""Sem fluxo próprio, o acesso é aprovado pela gestão de acessos.

		A etapa fica gravada no item, e não implícita: assim aparece no catálogo e pode ser
		trocada como qualquer outra. Apagar todas as etapas volta ao padrão.
		"""
		if self.etapas_aprovacao:
			return
		papel = papel_aprovador_padrao()
		self.append(
			"etapas_aprovacao",
			{
				"papel_aprovador": papel,
				"descricao": "Gestão de acessos" if papel == ROLE_GESTOR else "Aprovação",
			},
		)

	def _validar_papel(self):
		for campo in CAMPOS_DE_DRIVE:
			self.set(campo, None)
		if not self.papel:
			frappe.throw(_("Informe o papel concedido por este acesso."))
		if self.papel in PAPEIS_PROTEGIDOS:
			frappe.throw(_("O papel {0} não pode ser concedido pelo portal de acessos.").format(self.papel))
		self._garantir_unico("papel", self.papel)

	def _validar_drive(self):
		from gris.api.acessos.drives import nome_do_drive

		self.papel = None
		self.drive_id = (self.drive_id or "").strip()
		nome = nome_do_drive(self.drive_id)
		if not nome:
			frappe.throw(
				_("O drive {0} não está cadastrado em Configurações Google Workspace.").format(self.drive_id)
			)
		self.nome_drive = nome
		self._garantir_unico("drive_id", self.drive_id)

	def _garantir_unico(self, campo: str, valor: str):
		outro = frappe.db.get_value(ACESSO_DOCTYPE, {campo: valor, "name": ["!=", self.name or ""]}, "name")
		if outro:
			frappe.throw(_("O acesso {0} já cuida deste item.").format(outro))

	def _validar_etapas(self):
		for etapa in self.etapas_aprovacao or []:
			if etapa.papel_aprovador in {"Guest", "All"}:
				frappe.throw(_("A etapa {0} precisa de um papel aprovador específico.").format(etapa.idx))
