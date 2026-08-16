# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from gris.financeiro.doctype.transacao_extrato_geral.transacao_extrato_geral import (
	criar_transacao_de_sistema,
)


class TestCriarTransacaoDeSistema(FrappeTestCase):
	"""O helper é a única porta de entrada das integrações no extrato geral."""

	def test_helper_marca_fonte_sistema(self):
		tx = criar_transacao_de_sistema({"id": f"test-helper-{random_string(10)}", "valor": 10})
		self.assertEqual(tx.fonte, "Sistema")
		self.assertEqual(frappe.db.get_value("Transacao Extrato Geral", tx.name, "fonte"), "Sistema")

	def test_helper_ignora_tentativa_de_sobrescrever_fonte(self):
		# A fonte é aplicada depois dos campos do chamador: quem passar "Planilha" é ignorado.
		tx = criar_transacao_de_sistema(
			{"id": f"test-helper-{random_string(10)}", "valor": 10, "fonte": "Planilha"}
		)
		self.assertEqual(tx.fonte, "Sistema")

	def test_helper_ignora_tentativa_de_trocar_doctype(self):
		tx = criar_transacao_de_sistema(
			{"id": f"test-helper-{random_string(10)}", "valor": 10, "doctype": "Carteira"}
		)
		self.assertEqual(tx.doctype, "Transacao Extrato Geral")

	def test_transacao_criada_fora_do_helper_e_planilha(self):
		# Entrada manual / Data Import continuam caindo no default.
		tx = frappe.get_doc(
			{
				"doctype": "Transacao Extrato Geral",
				"id": f"test-manual-{random_string(10)}",
				"valor": 10,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(tx.fonte, "Planilha")


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

	def _criar_carteira(self):
		nome = f"Carteira Teste {random_string(8)}"
		frappe.get_doc(
			{
				"doctype": "Carteira",
				"nome": nome,
				"saldo_inicial": 0,
			}
		).insert(ignore_permissions=True)
		return nome

	def _tx_carteira(self, carteira, valor, excluir_do_total=0):
		return frappe.get_doc(
			{
				"doctype": "Transacao Extrato Geral",
				"id": f"test-wallet-{random_string(10)}",
				"categoria": "Categoria Teste Comum",
				"carteira": carteira,
				"valor": valor,
				"excluir_do_total": excluir_do_total,
			}
		).insert(ignore_permissions=True)

	def test_update_wallet_ignora_excluir_do_total(self):
		carteira = self._criar_carteira()

		self._tx_carteira(carteira, 100)
		self._tx_carteira(carteira, 100)
		self.assertEqual(frappe.db.get_value("Carteira", carteira, "saldo"), 200)

		# Uma duplicata conciliada não deve compor o saldo.
		tx_dup = self._tx_carteira(carteira, 100, excluir_do_total=1)
		self.assertEqual(frappe.db.get_value("Carteira", carteira, "saldo"), 200)

		# Ao devolver a transação ao total, o saldo volta a considerá-la.
		tx_dup.excluir_do_total = 0
		tx_dup.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Carteira", carteira, "saldo"), 300)
