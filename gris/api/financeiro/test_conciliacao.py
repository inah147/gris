# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import random_string

from gris.api.financeiro import conciliacao


class TestConciliacao(FrappeTestCase):
	def setUp(self):
		if not frappe.db.exists("Categoria de Transacao", "Categoria Conc Teste"):
			frappe.get_doc(
				{
					"doctype": "Categoria de Transacao",
					"nome": "Categoria Conc Teste",
					"desscrição": "Categoria Conc Teste",
				}
			).insert(ignore_permissions=True)

	def _tx(self, fonte, valor=150.0):
		return frappe.get_doc(
			{
				"doctype": "Transacao Extrato Geral",
				"id": f"test-conc-{random_string(10)}",
				"fonte": fonte,
				"valor": valor,
				"data_deposito": "2026-05-10",
				"descricao": "Pagamento Fulano de Tal",
			}
		).insert(ignore_permissions=True)

	def test_get_candidatos_encontra_planilha(self):
		sistema = self._tx("Sistema", 150.0)
		planilha = self._tx("Planilha", 150.49)  # dentro da tolerância de ±R$1

		res = conciliacao.get_candidatos_planilha(sistema.name)
		nomes = [c["name"] for c in res["candidatos"]]
		self.assertIn(planilha.name, nomes)

	def test_conciliar_e_desconciliar(self):
		sistema = self._tx("Sistema", 150.0)
		planilha = self._tx("Planilha", 150.0)

		conciliacao.conciliar(
			sistema.name,
			planilha.name,
			manter="sistema",
			categoria="Categoria Conc Teste",
			descricao_reduzida="Conciliado teste",
		)

		sistema.reload()
		planilha.reload()

		# Vínculo recíproco e status.
		self.assertEqual(sistema.transacao_conciliada, planilha.name)
		self.assertEqual(planilha.transacao_conciliada, sistema.name)
		self.assertEqual(sistema.status_conciliacao, "Conciliada")
		self.assertEqual(planilha.status_conciliacao, "Conciliada")

		# Sistema mantido no total; planilha excluída.
		self.assertEqual(sistema.excluir_do_total, 0)
		self.assertEqual(planilha.excluir_do_total, 1)

		# Categorização aplicada ao mantido + marcado como revisado.
		self.assertEqual(sistema.categoria, "Categoria Conc Teste")
		self.assertEqual(sistema.descricao_reduzida, "Conciliado teste")
		self.assertEqual(sistema.transacao_revisada, 1)

		# Desconciliar devolve ambos aos totais.
		conciliacao.desconciliar(sistema.name)
		sistema.reload()
		planilha.reload()
		self.assertEqual(sistema.status_conciliacao, "Não conciliada")
		self.assertEqual(planilha.status_conciliacao, "Não conciliada")
		self.assertEqual(sistema.excluir_do_total, 0)
		self.assertEqual(planilha.excluir_do_total, 0)
		self.assertFalse(sistema.transacao_conciliada)
		self.assertFalse(planilha.transacao_conciliada)

	def test_manter_planilha_exclui_sistema(self):
		sistema = self._tx("Sistema", 200.0)
		planilha = self._tx("Planilha", 200.0)

		conciliacao.conciliar(sistema.name, planilha.name, manter="planilha")
		sistema.reload()
		planilha.reload()
		self.assertEqual(planilha.excluir_do_total, 0)
		self.assertEqual(sistema.excluir_do_total, 1)
		self.assertEqual(planilha.transacao_revisada, 1)

	def test_marcar_sem_duplicata(self):
		sistema = self._tx("Sistema", 99.0)
		conciliacao.marcar_sem_duplicata(sistema.name, categoria="Categoria Conc Teste")
		sistema.reload()
		self.assertEqual(sistema.status_conciliacao, "Conciliada")
		self.assertEqual(sistema.excluir_do_total, 0)
		self.assertEqual(sistema.transacao_revisada, 1)
		self.assertFalse(sistema.transacao_conciliada)
		self.assertEqual(sistema.categoria, "Categoria Conc Teste")
