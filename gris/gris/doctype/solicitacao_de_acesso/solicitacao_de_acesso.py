# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_fullname

from gris.api.acessos.constantes import (
	ACESSO_DOCTYPE,
	DECISAO_PENDENTE,
	SOLICITACAO_DOCTYPE,
	STATUS_ABERTOS,
	STATUS_AGUARDANDO_CONCESSAO,
	STATUS_CANCELADA,
	STATUS_CONCEDIDA,
	STATUS_EM_APROVACAO,
	STATUS_RECUSADA,
)
from gris.api.acessos.permissoes import papel_aprovador_padrao

# Quem decide cada passo está em `gris.api.acessos.solicitacoes`; aqui ficam as regras
# que valem por qualquer caminho de gravação, inclusive o Desk.
TRANSICOES_PERMITIDAS: dict[str, set[str]] = {
	STATUS_EM_APROVACAO: {STATUS_AGUARDANDO_CONCESSAO, STATUS_CONCEDIDA, STATUS_RECUSADA, STATUS_CANCELADA},
	STATUS_AGUARDANDO_CONCESSAO: {STATUS_CONCEDIDA, STATUS_RECUSADA, STATUS_CANCELADA},
	STATUS_CONCEDIDA: set(),
	STATUS_RECUSADA: set(),
	STATUS_CANCELADA: set(),
}


class SolicitacaodeAcesso(Document):
	def validate(self):
		self._preencher_cabecalho()
		if self.is_new():
			self._copiar_etapas()
		self._validar_transicao_de_status()
		self._validar_decisoes()
		self._validar_unica_aberta()

	# ─── consultas usadas pela API e pelas permissões ──────────────────────────

	def etapa_corrente(self):
		return next((etapa for etapa in self.etapas or [] if etapa.ordem == self.etapa_atual), None)

	def total_de_etapas(self) -> int:
		return len(self.etapas or [])

	# ─── validações ─────────────────────────────────────────────────────────────

	def _preencher_cabecalho(self):
		if not self.solicitante:
			self.solicitante = frappe.session.user
		if not self.status:
			self.status = STATUS_EM_APROVACAO
		self.solicitante_nome = get_fullname(self.solicitante) or self.solicitante
		item = frappe.db.get_value(ACESSO_DOCTYPE, self.acesso, ["tipo", "por_secao"], as_dict=True)
		self.tipo = item.tipo if item else None
		por_secao = bool(item and item.por_secao)
		self.justificativa = (self.justificativa or "").strip() or None
		self.secao = " ".join((self.secao or "").split()) or None
		if not por_secao:
			self.secao = None
		elif self.is_new() and not self.secao:
			frappe.throw(_("Escolha a seção que você quer ver."))

		if not self.associado:
			self.associado = frappe.db.get_value("Associado", {"id_escoteiros": self.solicitante}, "name")
		if self.associado and not self.email_concessao:
			email = frappe.db.get_value("Associado", self.associado, "id_escoteiros")
			self.email_concessao = (email or "").strip().lower() or None

	def _copiar_etapas(self):
		"""Congela o fluxo no momento do pedido.

		Mudar as etapas do catálogo depois não pode mudar o caminho de um pedido em
		andamento: quem já aprovou continuaria valendo para uma etapa que não existe mais.
		"""
		if self.etapas:
			return

		etapas = frappe.get_all(
			"Etapa de Aprovacao de Acesso",
			filters={"parenttype": ACESSO_DOCTYPE, "parent": self.acesso},
			fields=["papel_aprovador", "descricao"],
			order_by="idx asc",
		)
		if not etapas:
			# Todo acesso nasce com a etapa padrão (`Acesso.validate`); isto cobre um item
			# gravado sem passar pelo controller.
			etapas = [{"papel_aprovador": papel_aprovador_padrao(), "descricao": "Gestão de acessos"}]

		for ordem, etapa in enumerate(etapas, start=1):
			self.append(
				"etapas",
				{
					"ordem": ordem,
					"papel_aprovador": etapa["papel_aprovador"],
					"descricao": etapa.get("descricao") or f"Etapa {ordem}",
					"decisao": DECISAO_PENDENTE,
				},
			)
		self.etapa_atual = 1

	def _validar_transicao_de_status(self):
		if self.is_new():
			if self.status != STATUS_EM_APROVACAO:
				frappe.throw(_("Uma nova solicitação precisa começar em 'Em aprovação'."))
			return

		anterior = self.get_doc_before_save()
		status_anterior = anterior.status if anterior else None
		if status_anterior and status_anterior != self.status:
			if self.status not in TRANSICOES_PERMITIDAS.get(status_anterior, set()):
				frappe.throw(
					_("Não é possível mudar a solicitação de '{0}' para '{1}'.").format(
						status_anterior, self.status
					)
				)

	def _validar_decisoes(self):
		"""Ninguém aprova o próprio pedido, por qualquer caminho de gravação."""
		for etapa in self.etapas or []:
			if etapa.decisao == DECISAO_PENDENTE or not etapa.decidido_por:
				continue
			if etapa.decidido_por == self.solicitante:
				frappe.throw(_("Quem solicitou não pode decidir a própria solicitação."))

	def _validar_unica_aberta(self):
		if self.status not in STATUS_ABERTOS:
			return
		filtros = {
			"solicitante": self.solicitante,
			"acesso": self.acesso,
			"status": ["in", STATUS_ABERTOS],
		}
		if self.secao:
			# Acesso por seção: um pedido aberto por seção, não um por acesso.
			filtros["secao"] = self.secao
		if not self.is_new():
			filtros["name"] = ["!=", self.name]
		if frappe.db.exists(SOLICITACAO_DOCTYPE, filtros):
			frappe.throw(_("Já existe uma solicitação em andamento para este acesso."))
