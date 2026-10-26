"""Testes de listar_transacoes (MCP) contra o banco: contagem e período.

Os testes com mock em test_mcp_ferramentas conferem só os filtros montados;
aqui o que importa é o SQL de verdade — o get_all e o db.count precisam
concordar, e o filtro de período não pode esconder vendas ainda não liquidadas.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.mcp import financeiro

DOCTYPE = "Transacao Extrato Geral"
CATEGORIA = "Teste MCP Listar"

# Mês longe de qualquer dado de seed, para o recorte só ver o que o teste criou.
INICIO, FIM = "2031-10-01", "2031-10-31"


def _transacao(sufixo: str, **campos) -> str:
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"id": f"test-mcp-listar-{sufixo}-{frappe.generate_hash(length=8)}",
			"descricao": f"Teste listar {sufixo}",
			"debito_credito": "Crédito",
			"valor": 10,
			"data_transacao": "2031-10-15",
			**campos,
		}
	).insert(ignore_permissions=True)
	return doc.name


class TestListarTransacoesBanco(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Categoria de Transacao", CATEGORIA):
			frappe.get_doc(
				{"doctype": "Categoria de Transacao", "nome": CATEGORIA, "desscrição": CATEGORIA}
			).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback()

	def test_total_com_filtros_conta_os_sem_categoria(self):
		nulas = [_transacao("nula-1"), _transacao("nula-2")]
		vazia = _transacao("vazia")
		# O Frappe grava Link vazio como NULL; força o "" que vem de importações antigas.
		tabela = frappe.qb.DocType(DOCTYPE)
		frappe.qb.update(tabela).set(tabela.categoria, "").where(tabela.name == vazia).run()
		_transacao("categorizada", categoria=CATEGORIA)

		resultado = financeiro.listar_transacoes(data_inicio=INICIO, data_fim=FIM, sem_categoria=True)

		ids = {t["name"] for t in resultado["transacoes"]}
		self.assertEqual(ids, {*nulas, vazia})
		self.assertEqual(resultado["paginacao"]["total_com_filtros"], 3)
		self.assertEqual(resultado["paginacao"]["retornados"], 3)

	def test_periodo_padrao_inclui_venda_sem_data_de_deposito(self):
		# Venda de cartão da maquininha antes da liquidação: só tem data_transacao.
		pendente = _transacao("spb", data_deposito=None)
		liquidada = _transacao("pix", data_deposito="2031-10-16 09:00:00")

		resultado = financeiro.listar_transacoes(data_inicio=INICIO, data_fim=FIM)

		ids = {t["name"] for t in resultado["transacoes"]}
		self.assertEqual(ids, {pendente, liquidada})
		self.assertEqual(resultado["paginacao"]["total_com_filtros"], 2)

	def test_campo_data_deposito_omite_nao_liquidadas(self):
		_transacao("spb", data_deposito=None)
		liquidada = _transacao("pix", data_deposito="2031-10-16 09:00:00")

		resultado = financeiro.listar_transacoes(data_inicio=INICIO, data_fim=FIM, campo_data="data_deposito")

		self.assertEqual({t["name"] for t in resultado["transacoes"]}, {liquidada})
		self.assertEqual(resultado["paginacao"]["total_com_filtros"], 1)
