# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

FONTE_SISTEMA = "Sistema"
FONTE_PLANILHA = "Planilha"


def criar_transacao_de_sistema(campos: dict) -> Document:
	"""Cria uma Transacao Extrato Geral originada de integração de sistema.

	Todo fluxo automático de importação (botão "Importar dados" e os `after_insert` das
	doctypes de origem) deve criar a transação consolidada por aqui. `doctype` e `fonte`
	são aplicados depois de `campos`, de modo que o chamador não consiga sobrescrevê-los
	nem esquecer a fonte e cair no default "Planilha" — que é reservado para o que entra
	por planilha/Data Import ou digitação manual.
	"""
	doc = frappe.get_doc(
		{
			**campos,
			"doctype": "Transacao Extrato Geral",
			"fonte": FONTE_SISTEMA,
		}
	)
	doc.insert()
	return doc


class TransacaoExtratoGeral(Document):
	TRANSFER_CATEGORIES = (
		"Transferência entre Contas",
		"Transferência entre Carteiras",
	)

	def _sync_repasse_entre_contas_with_categoria(self):
		categoria = (self.categoria or "").strip()
		self.repasse_entre_contas = 1 if categoria in self.TRANSFER_CATEGORIES else 0

	def validate(self):
		self._sync_repasse_entre_contas_with_categoria()

	def _update_wallet(self):
		if self.carteira:
			# 1. Somar o valor de cada transação da carteira no Transacao Extrato Geral
			#    Regra: excluir "Dinheiro" apenas quando a instituição da carteira for Infinitepay
			inst = frappe.db.get_value("Carteira", self.carteira, "instituicao_financeira") or ""
			apply_cash_filter = "infinitepay" in inst.lower()

			# Duplicatas conciliadas marcadas com excluir_do_total não entram no saldo.
			_filters = {"carteira": self.carteira, "excluir_do_total": 0}
			if apply_cash_filter:
				_filters["metodo"] = ["!=", "Dinheiro"]

			total = frappe.db.get_value(
				"Transacao Extrato Geral",
				filters=_filters,
				fieldname=["sum(valor) as total"],
				as_dict=True,
			)
			total_transacoes = total["total"] if total and total["total"] else 0

			# 2. Buscar o saldo inicial da carteira
			saldo_inicial = frappe.db.get_value("Carteira", self.carteira, "saldo_inicial") or 0

			# 3. Saldo atual = soma das transações + saldo inicial
			saldo_atual = total_transacoes + saldo_inicial

			# 4. Atualizar o saldo da carteira no doctype Carteira
			# Sem commit explícito: o Frappe commita ao final da requisição/job, e o commit
			# aqui quebraria o rollback dos testes, persistindo dados de teste no site.
			frappe.db.set_value("Carteira", self.carteira, "saldo", saldo_atual)

	def _upsert_pagamento_contribuicao_mensal(self, mes_referencia, valor, atrasou: bool) -> None:
		"""Cria ou atualiza o Pagamento Contribuicao Mensal de um mês, vinculado a esta transação."""
		pagamentos = frappe.get_all(
			"Pagamento Contribuicao Mensal",
			filters={"associado": self.beneficiario, "mes_de_referencia": mes_referencia},
			limit=1,
		)
		if pagamentos:
			pagamento = frappe.get_doc("Pagamento Contribuicao Mensal", pagamentos[0].name)
		else:
			pagamento = frappe.new_doc("Pagamento Contribuicao Mensal")
			pagamento.associado = self.beneficiario
			pagamento.mes_de_referencia = mes_referencia

		if (
			pagamento.status == "Pago"
			and pagamento.transacao_extrato == self.name
			and float(pagamento.valor or 0) == float(valor or 0)
			and bool(pagamento.atrasou) == bool(atrasou)
		):
			return

		pagamento.status = "Pago"
		pagamento.valor = valor
		pagamento.atrasou = 1 if atrasou else 0
		pagamento.transacao_extrato = self.name
		pagamento.save(ignore_permissions=True)
		frappe.msgprint(
			f"Pagamento de contribuição mensal marcado como Pago para {getdate(mes_referencia).strftime('%m/%Y')}",
			alert=True,
		)

	def _update_pagamento_contribuicao_mensal(self):
		"""Atualiza o(s) Pagamento Contribuicao Mensal quitado(s) por esta transação.

		Quando a transação detalha os meses cobertos em `competencias_contribuicao`
		(um pagamento que quita mais de um mês, ex.: mês atrasado + mês em dia), cada
		linha gera ou atualiza o Pagamento Contribuicao Mensal do mês correspondente,
		vinculado a esta transação. Sem detalhamento, mantém o comportamento anterior:
		um único mês, o da data da transação.
		"""
		if not self.beneficiario:
			return

		if self.competencias_contribuicao:
			for linha in self.competencias_contribuicao:
				if not linha.mes_referencia:
					continue
				self._upsert_pagamento_contribuicao_mensal(
					getdate(linha.mes_referencia).replace(day=1), linha.valor, bool(linha.em_atraso)
				)
			return

		if not self.data_transacao:
			return

		if self.has_value_changed("beneficiario") and self.beneficiario:
			mes_referencia = getdate(self.data_transacao).replace(day=1)
			self._upsert_pagamento_contribuicao_mensal(mes_referencia, abs(self.valor or 0), False)

	def after_insert(self):
		self._update_wallet()

	def _update_pagamento_conta_fixa(self):
		"""Atualiza o status de Pagamento Conta Fixa quando conta_fixa é preenchido."""
		if not self.conta_fixa or not self.data_transacao:
			return

		if self.has_value_changed("conta_fixa") and self.conta_fixa:
			data = getdate(self.data_transacao)
			mes_referencia = data.replace(day=1)

			pagamentos = frappe.get_all(
				"Pagamento Conta Fixa",
				filters={
					"conta": self.conta_fixa,
					"mes_referencia": mes_referencia,
				},
				limit=1,
			)

			if pagamentos:
				pagamento = frappe.get_doc("Pagamento Conta Fixa", pagamentos[0].name)
				# Update status and value
				if pagamento.status != "Pago" or pagamento.valor != abs(self.valor):
					pagamento.status = "Pago"
					pagamento.valor = abs(self.valor)
					pagamento.save(ignore_permissions=True)
					frappe.msgprint(
						f"Pagamento de conta fixa atualizado para Pago no mês {mes_referencia.strftime('%m/%Y')}",
						alert=True,
					)

	def on_update(self):
		self._update_pagamento_contribuicao_mensal()
		self._update_pagamento_conta_fixa()
		# `on_update` é o hook real do Frappe para pós-save; `after_update` não existe e
		# nunca era chamado, então o saldo da carteira não acompanhava edições da transação
		# (ex.: marcar excluir_do_total ao conciliar).
		self._update_wallet()

	def after_delete(self):
		self._update_wallet()
