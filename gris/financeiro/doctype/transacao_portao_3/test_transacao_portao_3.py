# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime


class TestTransacaoPortao3(FrappeTestCase):
	"""A importação do Portão 3 é um fluxo de sistema: o extrato geral tem de refletir isso."""

	def setUp(self):
		if not frappe.db.exists("Instituicao Financeira", "Portão 3"):
			frappe.get_doc({"doctype": "Instituicao Financeira", "nome": "Portão 3", "ativa": 1}).insert(
				ignore_permissions=True
			)
		if not frappe.db.exists("Carteira", "Ramo Escoteiro"):
			frappe.get_doc(
				{
					"doctype": "Carteira",
					"nome": "Ramo Escoteiro",
					"instituicao_financeira": "Portão 3",
					"ativa": 1,
					"saldo_inicial": 0,
				}
			).insert(ignore_permissions=True)

	def _importar(self, descricao, valor, entrada_saida, tipo="PIX"):
		"""Simula a importação do CSV inserindo a transação de origem.

		O `id` é gerado no before_insert a partir do hash das colunas — por isso o
		timestamp único, para não colidir entre casos de teste.
		"""
		return frappe.get_doc(
			{
				"doctype": "Transacao Portao 3",
				"timestamp": now_datetime(),
				"descricao": descricao,
				"valor": valor,
				"entrada_saida": entrada_saida,
				"carteira": "Ramo Escoteiro",
				"tipo": tipo,
				"tipo_de_transacao": "Teste",
			}
		).insert(ignore_permissions=True)

	def test_after_insert_gera_transacao_de_sistema(self):
		origem = self._importar("pix recebido de Fulano", 120, "Crédito")

		geral = frappe.get_doc("Transacao Extrato Geral", {"id": origem.id})
		self.assertEqual(geral.fonte, "Sistema")
		self.assertEqual(geral.instituicao, "Portão 3")
		self.assertEqual(geral.carteira, "Ramo Escoteiro")
		self.assertEqual(geral.valor, 120)

	def test_transferencia_entre_carteiras_tambem_e_sistema(self):
		origem = self._importar("transferência interna", 50, "Crédito", tipo="TRANFERÊNCIA ENTRE CARTEIRAS")

		geral = frappe.get_doc("Transacao Extrato Geral", {"id": origem.id})
		self.assertEqual(geral.fonte, "Sistema")
		self.assertEqual(geral.repasse_entre_contas, 1)
