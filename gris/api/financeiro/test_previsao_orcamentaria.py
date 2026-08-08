# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro.previsao_orcamentaria import (
	_agrupar,
	_mes_label,
	_normalizar_item,
	obter_comparativo,
)

CENTRO_TESTE = "Centro Previsão Teste"


def _centro_de_custo():
	"""Centro de custo exclusivo do teste — isola o realizado de outros dados do site."""
	if not frappe.db.exists("Centro de Custo", CENTRO_TESTE):
		frappe.get_doc({"doctype": "Centro de Custo", "nome": CENTRO_TESTE}).insert(ignore_permissions=True)
	return CENTRO_TESTE


def _transacao(id_transacao: str, data: str, valor: float, categoria: str | None = None):
	"""Cria uma transação no extrato geral usada como 'realizado' do comparativo."""
	return frappe.get_doc(
		{
			"doctype": "Transacao Extrato Geral",
			"id": id_transacao,
			"descricao": id_transacao,
			"debito_credito": "Crédito" if valor > 0 else "Débito",
			"valor": valor,
			"valor_absoluto": abs(valor),
			"data_deposito": data,
			"metodo": "Pix",
			"centro_de_custo": CENTRO_TESTE,
			"categoria": categoria,
		}
	).insert(ignore_permissions=True)


class TestPrevisaoOrcamentariaHelpers(FrappeTestCase):
	def test_mes_label(self):
		self.assertEqual(_mes_label("2026-03"), "03/26")

	def test_normalizar_item_aceita_item_valido(self):
		item = _normalizar_item(
			{
				"tipo": "Despesa",
				"descricao": "  Aluguel  ",
				"valor_previsto": "1200.50",
				"distribuicao": "Mês específico",
				"mes_referencia": "2026-04-19",
			}
		)
		self.assertEqual(item["descricao"], "Aluguel")
		self.assertEqual(item["valor_previsto"], 1200.50)
		self.assertEqual(str(item["mes_referencia"]), "2026-04-01")

	def test_normalizar_item_limpa_mes_na_distribuicao_uniforme(self):
		item = _normalizar_item(
			{
				"tipo": "Receita",
				"descricao": "Mensalidades",
				"valor_previsto": 100,
				"distribuicao": "Uniforme no período",
				"mes_referencia": "2026-04-01",
			}
		)
		self.assertIsNone(item["mes_referencia"])

	def test_normalizar_item_rejeita_tipo_invalido(self):
		with self.assertRaises(frappe.ValidationError):
			_normalizar_item({"tipo": "Outro", "descricao": "X", "valor_previsto": 10})

	def test_normalizar_item_rejeita_valor_nao_positivo(self):
		with self.assertRaises(frappe.ValidationError):
			_normalizar_item({"tipo": "Despesa", "descricao": "X", "valor_previsto": 0})

	def test_normalizar_item_exige_mes_quando_especifico(self):
		with self.assertRaises(frappe.ValidationError):
			_normalizar_item(
				{
					"tipo": "Despesa",
					"descricao": "X",
					"valor_previsto": 10,
					"distribuicao": "Mês específico",
				}
			)

	def test_agrupar_junta_previsto_e_realizado(self):
		linhas = _agrupar({"Aluguel": 300.0, "Água": 50.0}, {"Aluguel": 420.0, "Luz": 80.0}, "Sem categoria")
		por_rotulo = {linha["rotulo"]: linha for linha in linhas}
		self.assertEqual(por_rotulo["Aluguel"]["desvio"], 120.0)
		self.assertEqual(por_rotulo["Água"]["realizado"], 0.0)
		self.assertEqual(por_rotulo["Luz"]["previsto"], 0.0)
		# Ordenado pelo maior valor entre previsto e realizado.
		self.assertEqual(linhas[0]["rotulo"], "Aluguel")

	def test_agrupar_descarta_linhas_zeradas(self):
		self.assertEqual(_agrupar({"Vazia": 0.0}, {"Vazia": 0.0}, "Sem categoria"), [])


class TestObterComparativo(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.previsao = frappe.get_doc(
			{
				"doctype": "Previsao Orcamentaria",
				"titulo": "Comparativo Teste",
				"exercicio": 2026,
				"status": "Aprovada",
				"data_inicio": "2026-01-01",
				"data_fim": "2026-03-31",
				"centro_de_custo": _centro_de_custo(),
				"itens": [
					{"tipo": "Receita", "descricao": "Contribuições", "valor_previsto": 3000},
					{
						"tipo": "Despesa",
						"descricao": "Acampamento",
						"valor_previsto": 900,
						"distribuicao": "Mês específico",
						"mes_referencia": "2026-02-01",
					},
				],
			}
		).insert()

		_transacao("PREV-TESTE-C1", "2026-01-10", 800)
		_transacao("PREV-TESTE-D1", "2026-02-15", -1100)
		# Fora do período: não deve entrar no comparativo.
		_transacao("PREV-TESTE-FORA", "2026-06-01", -5000)

	def test_series_mensais_cobrem_todo_o_periodo(self):
		resultado = obter_comparativo(self.previsao.name)
		self.assertTrue(resultado["success"])
		self.assertEqual(resultado["meses"], ["2026-01", "2026-02", "2026-03"])
		self.assertEqual(resultado["labels"], ["01/26", "02/26", "03/26"])
		self.assertEqual(resultado["series"]["receitas_previstas"], [1000.0, 1000.0, 1000.0])
		self.assertEqual(resultado["series"]["despesas_previstas"], [0.0, 900.0, 0.0])

	def test_realizado_respeita_o_periodo_da_previsao(self):
		resultado = obter_comparativo(self.previsao.name)
		self.assertEqual(resultado["series"]["receitas_realizadas"], [800.0, 0.0, 0.0])
		self.assertEqual(resultado["series"]["despesas_realizadas"], [0.0, 1100.0, 0.0])
		self.assertEqual(resultado["totais"]["despesas_realizadas"], 1100.0)

	def test_totais_e_desvios(self):
		totais = obter_comparativo(self.previsao.name)["totais"]
		self.assertEqual(totais["receitas_previstas"], 3000.0)
		self.assertEqual(totais["despesas_previstas"], 900.0)
		self.assertEqual(totais["desvio_receitas"], -2200.0)
		self.assertEqual(totais["desvio_despesas"], 200.0)
		self.assertEqual(totais["resultado_realizado"], -300.0)
