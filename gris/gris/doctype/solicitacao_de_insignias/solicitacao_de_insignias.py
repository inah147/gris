# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_fullname, today

STATUS_SOLICITADA = "Solicitada"
STATUS_COMPRADA = "Comprada"
STATUS_RECEBIDA = "Recebida"
STATUS_ENTREGUE = "Entregue"
STATUS_CANCELADA = "Cancelada"

# Transições permitidas do fluxo. O solicitante abre em "Solicitada"; o financeiro
# registra a compra e o recebimento; a entrega ao solicitante encerra o pedido.
TRANSICOES_PERMITIDAS: dict[str, set[str]] = {
	STATUS_SOLICITADA: {STATUS_COMPRADA, STATUS_CANCELADA},
	STATUS_COMPRADA: {STATUS_RECEBIDA, STATUS_CANCELADA},
	STATUS_RECEBIDA: {STATUS_ENTREGUE},
	STATUS_ENTREGUE: set(),
	STATUS_CANCELADA: set(),
}

# Depois de comprada a solicitação vira documento de compra: os itens não podem mais mudar.
STATUS_EDITAVEIS = {STATUS_SOLICITADA}


class SolicitacaodeInsignias(Document):
	def validate(self):
		self._preencher_cabecalho()
		self._validar_transicao_de_status()
		self._validar_itens()
		self._calcular_totais()

	def _preencher_cabecalho(self):
		if not self.solicitante:
			self.solicitante = frappe.session.user
		if not self.data_solicitacao:
			self.data_solicitacao = today()
		if not self.status:
			self.status = STATUS_SOLICITADA

		self.solicitante_nome = get_fullname(self.solicitante) or self.solicitante
		self.justificativa = (self.justificativa or "").strip() or None

	def _validar_transicao_de_status(self):
		if self.is_new():
			if self.status != STATUS_SOLICITADA:
				frappe.throw(_("Uma nova solicitação precisa ser criada com o status 'Solicitada'."))
			return

		anterior = self.get_doc_before_save()
		status_anterior = anterior.status if anterior else None

		if status_anterior and status_anterior != self.status:
			permitidos = TRANSICOES_PERMITIDAS.get(status_anterior, set())
			if self.status not in permitidos:
				frappe.throw(f"Não é possível mudar o status de '{status_anterior}' para '{self.status}'.")

		self._validar_edicao_de_itens(status_anterior)

	def _validar_edicao_de_itens(self, status_anterior: str | None):
		"""Bloqueia alteração de itens depois que a compra foi registrada."""
		if status_anterior in STATUS_EDITAVEIS or status_anterior is None:
			return

		anterior = self.get_doc_before_save()
		if not anterior:
			return

		def _assinatura(doc):
			return [
				(item.insignia, int(item.quantidade or 0), item.beneficiario) for item in (doc.itens or [])
			]

		if _assinatura(anterior) != _assinatura(self):
			frappe.throw(
				f"Os itens não podem ser alterados quando a solicitação está em '{status_anterior}'."
			)

	def _validar_itens(self):
		if not self.itens:
			frappe.throw(_("Inclua ao menos um item na solicitação."))

		vistos: set[tuple[str, str | None]] = set()
		for item in self.itens:
			if not item.insignia:
				frappe.throw(_("Todo item precisa de uma insígnia ou distintivo."))

			quantidade = int(item.quantidade or 0)
			if quantidade < 1:
				frappe.throw(f"A quantidade de '{item.insignia}' deve ser maior que zero.")
			item.quantidade = quantidade

			chave = (item.insignia, item.beneficiario or None)
			if chave in vistos:
				frappe.throw(
					f"O item '{item.insignia}' está duplicado. Some as quantidades em uma única linha."
				)
			vistos.add(chave)

			item.observacao = (item.observacao or "").strip() or None

	def _calcular_totais(self):
		total = 0.0
		for item in self.itens:
			valor_unitario = flt(item.valor_unitario)
			if valor_unitario < 0:
				frappe.throw(_("O valor unitário não pode ser negativo."))
			item.valor_total = flt(valor_unitario * int(item.quantidade or 0), 2)
			total += item.valor_total

		self.valor_estimado = flt(total, 2)
