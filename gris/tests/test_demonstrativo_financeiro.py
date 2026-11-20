"""Testes do demonstrativo financeiro anual e da exportação em Excel.

O cálculo é o mesmo da página `/financeiro/demonstrativo`; o .xlsx deve trazer as
mesmas linhas (saldo inicial, categorias por seção, totais, resultados e saldo final).
"""

import io

import frappe
from frappe.tests.utils import FrappeTestCase
from openpyxl import load_workbook

from gris.api.financeiro.demonstrativo import (
	exportar_demonstrativo_excel,
	gerar_planilha_demonstrativo,
	montar_demonstrativo,
	normalizar_ano,
)

DOCTYPE = "Transacao Extrato Geral"
ANO = 2099
PREFIXO_ID = "teste-demonstrativo-"


def _transacao(sufixo, data, valor, debito_credito, **extra):
	return frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"id": PREFIXO_ID + sufixo,
			"descricao": f"Teste demonstrativo {sufixo}",
			"data_deposito": data,
			"data_transacao": data[:10],
			"debito_credito": debito_credito,
			"valor": valor if debito_credito == "Crédito" else -valor,
			"valor_absoluto": valor,
			"metodo": "Pix",
			**extra,
		}
	).insert(ignore_permissions=True)


class TestDemonstrativoFinanceiro(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		_transacao("ano-anterior", f"{ANO - 1}-12-15 10:00:00", 100.0, "Crédito")
		_transacao(
			"jan-credito", f"{ANO}-01-10 10:00:00", 500.0, "Crédito", ordinaria_extraordinaria="Ordinária"
		)
		_transacao(
			"jan-debito", f"{ANO}-01-20 10:00:00", 200.0, "Débito", ordinaria_extraordinaria="Ordinária"
		)
		_transacao(
			"mar-debito", f"{ANO}-03-05 10:00:00", 50.0, "Débito", ordinaria_extraordinaria="Extraordinária"
		)
		# Ficam de fora do demonstrativo: dinheiro, duplicata excluída do total.
		_transacao("dinheiro", f"{ANO}-01-11 10:00:00", 999.0, "Crédito", metodo="Dinheiro")
		_transacao("excluida", f"{ANO}-01-12 10:00:00", 888.0, "Crédito", excluir_do_total=1)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _saldo_antes_do_ano(self):
		return (
			frappe.db.sql(
				f"""
				SELECT SUM(valor) FROM `tab{DOCTYPE}`
				WHERE data_deposito < %s AND metodo != 'Dinheiro'
				AND repasse_entre_contas = 0 AND excluir_do_total = 0
				""",
				(f"{ANO}-01-01",),
			)[0][0]
			or 0.0
		)

	def test_soma_por_secao_categoria_e_mes(self):
		demo = montar_demonstrativo(ANO)

		self.assertEqual(demo["year"], ANO)
		self.assertEqual([m["label"] for m in demo["months"]][:3], ["jan-99", "fev-99", "mar-99"])
		self.assertEqual(demo["month_totals"]["entradas"][1], 500.0)
		self.assertEqual(demo["month_totals"]["saidas"][1], 200.0)
		self.assertEqual(demo["month_totals"]["saidas"][3], 50.0)
		self.assertEqual(demo["data"]["entradas"]["(Sem Categoria)"][1], 500.0)
		self.assertEqual(demo["month_totals_ordinarias"]["saidas"][3], 0.0)

	def test_saldos_encadeiam_mes_a_mes(self):
		demo = montar_demonstrativo(ANO)
		saldo_antes = self._saldo_antes_do_ano()

		self.assertAlmostEqual(demo["saldo_inicial"][1], saldo_antes)
		self.assertAlmostEqual(demo["saldo_final"][1], saldo_antes + 300.0)
		self.assertAlmostEqual(demo["saldo_inicial"][2], demo["saldo_final"][1])
		self.assertAlmostEqual(demo["saldo_final"][12], saldo_antes + 250.0)

	def test_ano_invalido_cai_no_ano_atual(self):
		self.assertEqual(normalizar_ano("abc"), frappe.utils.now_datetime().year)
		self.assertEqual(normalizar_ano(None), frappe.utils.now_datetime().year)
		self.assertEqual(normalizar_ano("2024"), 2024)

	def test_planilha_tem_as_linhas_da_pagina(self):
		demo = montar_demonstrativo(ANO)
		wb = load_workbook(io.BytesIO(gerar_planilha_demonstrativo(demo)))
		ws = wb.active

		rotulos = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
		for esperado in (
			"Saldo Inicial",
			"Entradas (Créditos)",
			"Total Entradas",
			"Saídas (Débitos)",
			"Total Saídas",
			"Resultado do Mês",
			"Resultado Ordinário",
			"Saldo Final",
		):
			self.assertIn(esperado, rotulos)

		cabecalho = [ws.cell(row=4, column=c).value for c in range(1, 14)]
		self.assertEqual(cabecalho[0], "Categoria")
		self.assertEqual(cabecalho[1], "jan-99")
		self.assertEqual(cabecalho[12], "dez-99")

		linha_resultado = rotulos.index("Resultado do Mês") + 1
		self.assertEqual(ws.cell(row=linha_resultado, column=2).value, 300.0)
		self.assertEqual(ws.cell(row=linha_resultado, column=4).value, -50.0)
		linha_ordinario = rotulos.index("Resultado Ordinário") + 1
		self.assertEqual(ws.cell(row=linha_ordinario, column=4).value, 0.0)

	def test_endpoint_devolve_download_xlsx(self):
		exportar_demonstrativo_excel(str(ANO))

		self.assertEqual(frappe.local.response.type, "download")
		self.assertEqual(frappe.local.response.filename, f"demonstrativo-financeiro-{ANO}.xlsx")
		self.assertTrue(frappe.local.response.filecontent.startswith(b"PK"))

	def test_endpoint_exige_login(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			exportar_demonstrativo_excel(str(ANO))
