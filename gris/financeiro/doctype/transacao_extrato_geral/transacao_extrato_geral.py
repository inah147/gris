# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class TransacaoExtratoGeral(Document):
	def _update_wallet(self):
		if self.carteira:
			# 1. Somar o valor de cada transação da carteira no Transacao Extrato Geral
			#    Regra: excluir "Dinheiro" apenas quando a instituição da carteira for Infinitepay
			inst = frappe.db.get_value("Carteira", self.carteira, "instituicao_financeira") or ""
			apply_cash_filter = "infinitepay" in inst.lower()

			_filters = {"carteira": self.carteira}
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
			frappe.db.set_value("Carteira", self.carteira, "saldo", saldo_atual)
			frappe.db.commit()

	def _update_pagamento_contribuicao_mensal(self):
		"""Atualiza o status de Pagamento Contribuicao Mensal quando beneficiario é preenchido."""
		# Log para debug
		frappe.logger().info(
			f"_update_pagamento_contribuicao_mensal chamado. beneficiario={self.beneficiario}, data_transacao={self.data_transacao}"
		)

		if not self.beneficiario or not self.data_transacao:
			frappe.logger().info("Retornando: beneficiario ou data_transacao está vazio")
			return

		# Verifica se o beneficiário mudou
		if self.has_value_changed("beneficiario") and self.beneficiario:
			frappe.logger().info(f"Beneficiário mudou para: {self.beneficiario}")

			# Extrai o mês de referência da data da transação
			data = getdate(self.data_transacao)
			# Primeiro dia do mês da transação
			mes_referencia = data.replace(day=1)

			frappe.logger().info(
				f"Buscando pagamento para associado={self.beneficiario}, mes_referencia={mes_referencia}"
			)

			# Busca o registro de Pagamento Contribuicao Mensal
			pagamentos = frappe.get_all(
				"Pagamento Contribuicao Mensal",
				filters={
					"associado": self.beneficiario,
					"mes_de_referencia": mes_referencia,
				},
				limit=1,
			)

			frappe.logger().info(f"Pagamentos encontrados: {pagamentos}")

			if pagamentos:
				# Atualiza o status para "Pago"
				pagamento = frappe.get_doc("Pagamento Contribuicao Mensal", pagamentos[0].name)
				frappe.logger().info(f"Status atual do pagamento: {pagamento.status}")

				if pagamento.status != "Pago":
					pagamento.status = "Pago"
					pagamento.save(ignore_permissions=True)
					frappe.db.commit()
					frappe.logger().info("Pagamento atualizado para Pago")
					frappe.msgprint(
						f"Pagamento de contribuição mensal marcado como Pago para {mes_referencia.strftime('%m/%Y')}",
						alert=True,
					)
				else:
					frappe.logger().info("Pagamento já estava como Pago")
			else:
				frappe.logger().warning(
					f"Nenhum pagamento encontrado para {self.beneficiario} no mês {mes_referencia}"
				)
		else:
			frappe.logger().info("Beneficiário não mudou ou está vazio")

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
					frappe.db.commit()
					frappe.msgprint(
						f"Pagamento de conta fixa atualizado para Pago no mês {mes_referencia.strftime('%m/%Y')}",
						alert=True,
					)

	def on_update(self):
		self._update_pagamento_contribuicao_mensal()
		self._update_pagamento_conta_fixa()

	def after_update(self):
		self._update_wallet()

	def after_delete(self):
		self._update_wallet()
