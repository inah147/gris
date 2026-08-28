# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PagamentoContribuicaoMensal(Document):
	def _get_payments_beneficiary(self) -> dict[str, int]:
		rows = frappe.get_all(
			"Pagamento Contribuicao Mensal",
			filters={"associado": self.associado},
			fields=["status", "count(name) as qty"],
			group_by="status",
		)
		return {r.status: int(r.qty) for r in rows}

	def _update_beneficiary_payments(self) -> None:
		"""Atualiza contadores de contribuições no DocType Associado.

		Usa aggregation dos pagamentos para preencher:
		- qt_contribuicoes_pagas (status = Pago)
		- qt_contribuicoes_atrasadas (status = Atrasado)

		Não força commit aqui; a transação é concluída pelo ciclo normal do request.
		"""

		payments = self._get_payments_beneficiary()

		frappe.db.set_value(
			"Associado",
			self.associado,
			{
				"qt_contribuicoes_pagas": payments.get("Pago", 0),
				"qt_contribuicoes_atrasadas": payments.get("Atrasado", 0),
			},
			update_modified=False,
		)

	def on_update(self):
		# `after_save` não é hook de controller do Frappe (nunca era disparado pelo
		# framework). `on_update` roda em toda inserção e atualização.
		self._update_beneficiary_payments()

	# uma vez por dia:
	#    - atualizar status de todos os beneficiários que não estão com status em aberto
	#    - se passar da data de vencimento:
	#        - atualizar para Atrasado
	# - atualizar quantidades no doctype de associados
	#
	# no primeiro dia de cada mes
	#    - adicionar linha com status em aberto para todos os beneficiários com status ativo no grupo
	#
	# sempre que atualizar um status:
	#    - atualizar quantidades no doctype de associados - OK
