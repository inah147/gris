# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate, random_string


class TestTransacaoBTGEmpresas(FrappeTestCase):
	"""A importação do BTG é um fluxo de sistema: o extrato geral tem de refletir isso."""

	def setUp(self):
		if not frappe.db.exists("Instituicao Financeira", "BTG Empresas"):
			frappe.get_doc(
				{"doctype": "Instituicao Financeira", "nome": "BTG Empresas", "ativa": 1}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Carteira", "BTG Empresas"):
			frappe.get_doc(
				{
					"doctype": "Carteira",
					"nome": "BTG Empresas",
					"instituicao_financeira": "BTG Empresas",
					"ativa": 1,
					"saldo_inicial": 0,
				}
			).insert(ignore_permissions=True)

	def _importar(self, descricao, valor):
		"""Simula a importação do OFX inserindo a transação de origem."""
		return frappe.get_doc(
			{
				"doctype": "Transacao BTG Empresas",
				"id": f"test-btg-{random_string(10)}",
				"data_transacao": nowdate(),
				"descricao": descricao,
				"valor": valor,
				"tipo": "CREDIT" if valor > 0 else "DEBIT",
			}
		).insert(ignore_permissions=True)

	def test_after_insert_gera_transacao_de_sistema(self):
		origem = self._importar("Pix recebido de Fulano", 250)

		geral = frappe.get_doc("Transacao Extrato Geral", {"id": origem.id})
		self.assertEqual(geral.fonte, "Sistema")
		self.assertEqual(geral.instituicao, "BTG Empresas")
		self.assertEqual(geral.valor, 250)
		self.assertEqual(geral.debito_credito, "Crédito")

	def test_debito_tambem_e_sistema(self):
		origem = self._importar("Pix enviado para Beltrano", -80)

		geral = frappe.get_doc("Transacao Extrato Geral", {"id": origem.id})
		self.assertEqual(geral.fonte, "Sistema")
		self.assertEqual(geral.debito_credito, "Débito")
