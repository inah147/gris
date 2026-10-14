# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from gris.api.festas import totais_payload
from gris.festas.doctype.compra_festa.test_compra_festa import _novo_produto


def _completar_portaria(festa_name: str) -> None:
	portaria = frappe.get_doc("Area da Festa", f"{festa_name} - Portaria")
	portaria.nome_coord = "Coord Portaria"
	portaria.email_coord = "portaria@example.com"
	portaria.telefone_coord = "+5511999999999"
	portaria.save(ignore_permissions=True)


class TestFesta(FrappeTestCase):
	def _nova_festa(self):
		festa = frappe.get_doc(
			{
				"doctype": "Festa",
				"nome_festa": f"Festa Teste {frappe.generate_hash(length=8)}",
				"data": add_days(today(), 30),
				"data_limite_vendas": add_days(today(), 20),
				"status": "Em andamento",
				"expectativa_publico_min": 10,
				"expectativa_publico_intermediario": 20,
				"expectativa_publico_max": 30,
			}
		).insert(ignore_permissions=True)
		_completar_portaria(festa.name)
		return festa

	def test_lista_de_compras_usa_quantidade_final(self):
		festa = self._nova_festa()
		frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Copos",
				"unidade_compra": "unidade",
				"quantidade_compra": 2,
				"quantidade_compra_final": 8,
				"cotacoes": [
					{
						"fornecedor": "Fornecedor A",
						"valor": 10,
						"quantidade": 2,
						"unidade_medida": "unidade",
						"escolhida": 1,
					}
				],
			}
		).insert(ignore_permissions=True)

		# 8 cotações de 2 copos a R$ 10: 16 copos, R$ 5 cada, R$ 80 no total.
		festa.reload()
		self.assertEqual(len(festa.lista_compras), 1)
		self.assertEqual(flt(festa.lista_compras[0].quantidade), 16)
		self.assertEqual(flt(festa.lista_compras[0].valor_unitario), 5)
		self.assertEqual(flt(festa.lista_compras[0].valor_total), 80)

	def test_despesas_por_area_continuam_agregando_compra(self):
		festa = self._nova_festa()
		area = frappe.get_doc(
			{
				"doctype": "Area da Festa",
				"festa": festa.name,
				"nome_area": "Cozinha",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"area": area.name,
				"nome_item": "Guardanapos",
				"unidade_compra": "unidade",
				"quantidade_compra_final": 3,
				"cotacoes": [
					{
						"fornecedor": "Fornecedor A",
						"valor": 10,
						"quantidade": 1,
						"unidade_medida": "unidade",
						"escolhida": 1,
					}
				],
			}
		).insert(ignore_permissions=True)

		festa.reload()
		linha = next((d for d in festa.despesas_por_area if d.area == area.name), None)
		self.assertIsNotNone(linha)
		self.assertEqual(flt(linha.esperado_intermediario), 30)

	def test_previsto_usa_quantidade_final_e_cenario_ativo(self):
		festa = self._nova_festa()
		area = frappe.get_doc(
			{
				"doctype": "Area da Festa",
				"festa": festa.name,
				"nome_area": "Cozinha",
			}
		).insert(ignore_permissions=True)
		produto = _novo_produto(festa, expectativa_venda_por_pessoa=1)
		# Cenário intermediário (20 pessoas x 1 uso) pede 2 pacotes de 10 = R$ 100;
		# a quantidade final decidida é 5 pacotes = R$ 250.
		frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"area": area.name,
				"nome_item": "Pão",
				"usado_em_produtos": 1,
				"unidade_compra": "unidade",
				"quantidade_compra_final": 5,
				"cotacoes": [
					{
						"fornecedor": "Padaria",
						"valor": 50,
						"quantidade": 10,
						"unidade_medida": "unidade",
						"escolhida": 1,
					}
				],
				"usos_em_produto": [
					{"produto": produto.name, "quantidade_usada": 1, "unidade_medida_uso": "unidade"}
				],
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Contratacao Festa",
				"festa": festa.name,
				"area": area.name,
				"nome_item": "Som",
				"cotacoes": [{"fornecedor": "DJ", "valor": 100, "escolhida": 1}],
			}
		).insert(ignore_permissions=True)

		festa.reload()
		festa.margem_seguranca = 10
		festa.cenario_simulacao = "Máximo"
		festa.save(ignore_permissions=True)

		linha = next(d for d in festa.despesas_por_area if d.area == area.name)
		self.assertEqual(flt(linha.esperado_intermediario), 200)
		self.assertEqual(festa.despesas_previstas_por_area()[area.name], 350)

		totais = totais_payload(festa)
		previsto = totais["previsto"]
		self.assertEqual(previsto["cenario"], "Máximo")
		self.assertAlmostEqual(previsto["margem"], 35)
		self.assertAlmostEqual(previsto["despesa"], 385)
		self.assertAlmostEqual(previsto["receita"], totais["max"]["receita"])
		self.assertAlmostEqual(previsto["saldo"], totais["max"]["receita"] - 385)
