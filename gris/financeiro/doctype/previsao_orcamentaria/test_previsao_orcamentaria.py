# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.financeiro.doctype.previsao_orcamentaria.previsao_orcamentaria import (
	contar_meses,
	distribuicao_do_item,
	distribuir_valor,
	meses_do_periodo,
	primeiro_dia_do_mes,
)


class TestPrevisaoOrcamentariaHelpers(FrappeTestCase):
	"""Cobre a distribuição do valor previsto pelos meses do período."""

	def test_meses_do_periodo_inclui_mes_inicial_e_final(self):
		self.assertEqual(
			meses_do_periodo("2026-01-15", "2026-04-02"),
			["2026-01", "2026-02", "2026-03", "2026-04"],
		)

	def test_meses_do_periodo_atravessa_virada_de_ano(self):
		self.assertEqual(
			meses_do_periodo("2025-11-01", "2026-02-28"),
			["2025-11", "2025-12", "2026-01", "2026-02"],
		)

	def test_meses_do_periodo_com_periodo_invertido(self):
		self.assertEqual(meses_do_periodo("2026-05-01", "2026-01-01"), [])

	def test_contar_meses(self):
		self.assertEqual(contar_meses("2026-01-01", "2026-12-31"), 12)
		self.assertEqual(contar_meses("2026-01-31", "2026-01-01"), 1)
		self.assertEqual(contar_meses("2026-03-01", "2026-01-01"), 0)

	def test_primeiro_dia_do_mes(self):
		self.assertEqual(str(primeiro_dia_do_mes("2026-07-23")), "2026-07-01")

	def test_distribuir_valor_soma_exatamente_o_total(self):
		parcelas = distribuir_valor(1000, 3)
		self.assertEqual(len(parcelas), 3)
		self.assertEqual(round(sum(parcelas), 2), 1000.0)
		# O centavo de resto vai para o primeiro mês.
		self.assertEqual(parcelas[0], 333.34)
		self.assertEqual(parcelas[1], 333.33)

	def test_distribuir_valor_sem_meses(self):
		self.assertEqual(distribuir_valor(500, 0), [])

	def test_distribuicao_uniforme(self):
		meses = ["2026-01", "2026-02", "2026-03", "2026-04"]
		item = {"valor_previsto": 400, "distribuicao": "Uniforme no período"}
		self.assertEqual(
			distribuicao_do_item(item, meses),
			{"2026-01": 100.0, "2026-02": 100.0, "2026-03": 100.0, "2026-04": 100.0},
		)

	def test_distribuicao_em_mes_especifico(self):
		meses = ["2026-01", "2026-02", "2026-03"]
		item = {
			"valor_previsto": 750,
			"distribuicao": "Mês específico",
			"mes_referencia": "2026-02-17",
		}
		self.assertEqual(distribuicao_do_item(item, meses), {"2026-02": 750.0})

	def test_distribuicao_em_mes_fora_do_periodo_e_ignorada(self):
		meses = ["2026-01", "2026-02"]
		item = {
			"valor_previsto": 750,
			"distribuicao": "Mês específico",
			"mes_referencia": "2026-09-01",
		}
		self.assertEqual(distribuicao_do_item(item, meses), {})


class TestPrevisaoOrcamentaria(FrappeTestCase):
	def _nova_previsao(self, titulo, itens=None, data_inicio="2026-01-01", data_fim="2026-03-31"):
		doc = frappe.get_doc(
			{
				"doctype": "Previsao Orcamentaria",
				"titulo": titulo,
				"exercicio": 2026,
				"status": "Rascunho",
				"data_inicio": data_inicio,
				"data_fim": data_fim,
				"itens": itens or [],
			}
		)
		doc.insert()
		return doc

	def test_totais_sao_calculados_na_validacao(self):
		doc = self._nova_previsao(
			"Orçamento Teste Totais",
			itens=[
				{"tipo": "Receita", "descricao": "Contribuições", "valor_previsto": 9000},
				{"tipo": "Despesa", "descricao": "Aluguel", "valor_previsto": 3000},
				{"tipo": "Despesa", "descricao": "Materiais", "valor_previsto": 1500},
			],
		)
		self.assertEqual(doc.total_receitas_previstas, 9000)
		self.assertEqual(doc.total_despesas_previstas, 4500)
		self.assertEqual(doc.resultado_previsto, 4500)

	def test_periodo_invertido_e_rejeitado(self):
		with self.assertRaises(frappe.ValidationError):
			self._nova_previsao(
				"Orçamento Teste Período",
				data_inicio="2026-06-01",
				data_fim="2026-02-01",
			)

	def test_item_com_valor_nao_positivo_e_rejeitado(self):
		with self.assertRaises(frappe.ValidationError):
			self._nova_previsao(
				"Orçamento Teste Valor",
				itens=[{"tipo": "Despesa", "descricao": "Zerada", "valor_previsto": 0}],
			)

	def test_mes_de_referencia_fora_do_periodo_e_rejeitado(self):
		with self.assertRaises(frappe.ValidationError):
			self._nova_previsao(
				"Orçamento Teste Mês",
				itens=[
					{
						"tipo": "Despesa",
						"descricao": "Fora do período",
						"valor_previsto": 100,
						"distribuicao": "Mês específico",
						"mes_referencia": "2027-01-01",
					}
				],
			)

	def test_distribuicao_mensal_combina_uniforme_e_mes_especifico(self):
		doc = self._nova_previsao(
			"Orçamento Teste Distribuição",
			itens=[
				{"tipo": "Receita", "descricao": "Mensalidades", "valor_previsto": 3000},
				{
					"tipo": "Despesa",
					"descricao": "Acampamento",
					"valor_previsto": 1200,
					"distribuicao": "Mês específico",
					"mes_referencia": "2026-02-10",
				},
			],
		)
		distribuicao = doc.distribuicao_mensal()
		self.assertEqual(sorted(distribuicao.keys()), ["2026-01", "2026-02", "2026-03"])
		self.assertEqual(distribuicao["2026-01"]["receitas"], 1000)
		self.assertEqual(distribuicao["2026-01"]["despesas"], 0)
		self.assertEqual(distribuicao["2026-02"]["despesas"], 1200)
		self.assertEqual(distribuicao["2026-03"]["despesas"], 0)
		self.assertEqual(
			round(sum(m["receitas"] for m in distribuicao.values()), 2),
			doc.total_receitas_previstas,
		)

	def test_mes_de_referencia_e_normalizado_para_o_primeiro_dia(self):
		doc = self._nova_previsao(
			"Orçamento Teste Normalização",
			itens=[
				{
					"tipo": "Despesa",
					"descricao": "Evento",
					"valor_previsto": 500,
					"distribuicao": "Mês específico",
					"mes_referencia": "2026-03-27",
				}
			],
		)
		self.assertEqual(str(doc.itens[0].mes_referencia), "2026-03-01")

	def test_mes_de_referencia_e_limpo_na_distribuicao_uniforme(self):
		doc = self._nova_previsao(
			"Orçamento Teste Limpeza",
			itens=[
				{
					"tipo": "Despesa",
					"descricao": "Uniforme",
					"valor_previsto": 300,
					"distribuicao": "Uniforme no período",
					"mes_referencia": "2026-02-01",
				}
			],
		)
		self.assertIsNone(doc.itens[0].mes_referencia)
