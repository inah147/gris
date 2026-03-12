# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string


class TestTransacaoExtratoGeral(FrappeTestCase):
	def setUp(self):
		self._ensure_categoria("Transferência entre Contas")
		self._ensure_categoria("Transferência entre Carteiras")
		self._ensure_categoria("Categoria Teste Comum")

	def _ensure_categoria(self, nome):
		if frappe.db.exists("Categoria de Transacao", nome):
			return
		frappe.get_doc(
			{
				"doctype": "Categoria de Transacao",
				"nome": nome,
				"desscrição": nome,
			}
		).insert(ignore_permissions=True)

	def _build_transacao(self, categoria, repasse_entre_contas=0):
		return frappe.get_doc(
			{
				"doctype": "Transacao Extrato Geral",
				"id": f"test-repasse-{random_string(10)}",
				"categoria": categoria,
				"repasse_entre_contas": repasse_entre_contas,
				"valor": 10,
			}
		)

	def test_repasse_entre_contas_automatico_em_create(self):
		tx_transferencia = self._build_transacao("Transferência entre Contas", repasse_entre_contas=0)
		tx_transferencia.insert(ignore_permissions=True)
		self.assertEqual(tx_transferencia.repasse_entre_contas, 1)

		tx_carteiras = self._build_transacao("Transferência entre Carteiras", repasse_entre_contas=0)
		tx_carteiras.insert(ignore_permissions=True)
		self.assertEqual(tx_carteiras.repasse_entre_contas, 1)

		tx_comum = self._build_transacao("Categoria Teste Comum", repasse_entre_contas=1)
		tx_comum.insert(ignore_permissions=True)
		self.assertEqual(tx_comum.repasse_entre_contas, 0)

	def test_repasse_entre_contas_automatico_em_update(self):
		tx = self._build_transacao("Categoria Teste Comum", repasse_entre_contas=1)
		tx.insert(ignore_permissions=True)
		self.assertEqual(tx.repasse_entre_contas, 0)

		tx.categoria = "Transferência entre Contas"
		tx.repasse_entre_contas = 0
		tx.save(ignore_permissions=True)
		self.assertEqual(tx.repasse_entre_contas, 1)

		tx.categoria = "Categoria Teste Comum"
		tx.repasse_entre_contas = 1
		tx.save(ignore_permissions=True)
		self.assertEqual(tx.repasse_entre_contas, 0)
