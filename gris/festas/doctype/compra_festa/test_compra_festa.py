import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from gris.api.festas import (
	criar_compra,
	criar_compra_sem_previsao,
	excluir_compra,
	salvar_compra_sem_previsao,
	salvar_realizado_compra,
)
from gris.api.festas.relatorio import build_relatorio_payload


def _nova_festa(publico_min=0, publico_intermediario=0, publico_max=0):
	festa = frappe.get_doc(
		{
			"doctype": "Festa",
			"nome_festa": f"Festa Teste {frappe.generate_hash(length=8)}",
			"data": today(),
			"data_limite_vendas": today(),
			"status": "Em andamento",
			"expectativa_publico_min": publico_min,
			"expectativa_publico_intermediario": publico_intermediario,
			"expectativa_publico_max": publico_max,
		}
	).insert(ignore_permissions=True)
	portaria = frappe.get_doc("Area da Festa", f"{festa.name} - Portaria")
	portaria.nome_coord = "Coord Portaria"
	portaria.email_coord = "portaria@example.com"
	portaria.telefone_coord = "+5511999999999"
	portaria.save(ignore_permissions=True)
	return festa


def _novo_produto(festa, expectativa_venda_por_pessoa=0):
	return frappe.get_doc(
		{
			"doctype": "Produto de Venda Festa",
			"festa": festa.name,
			"nome_produto": f"Produto {frappe.generate_hash(length=6)}",
			"preco_venda": 10,
			"expectativa_venda_por_pessoa": expectativa_venda_por_pessoa,
		}
	).insert(ignore_permissions=True)


class TestCompraFesta(FrappeTestCase):
	def test_quantidade_final_calcula_valor_total(self):
		festa = _nova_festa()
		compra = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Carne",
				"unidade_compra": "kg",
				"quantidade_compra": 2,
				"quantidade_compra_final": 8,
				"cotacoes": [
					{
						"fornecedor": "Fornecedor A",
						"valor": 20,
						"quantidade": 2,
						"unidade_medida": "kg",
						"escolhida": 1,
					}
				],
			}
		).insert(ignore_permissions=True)

		self.assertEqual(flt(compra.valor_total_compra), 80)

	def test_quantidade_final_rateia_uso_em_produto(self):
		# Publico intermediario=1 e expectativa=1 -> qtd do produto no cenario = 1,
		# entao a necessidade de queijo e o proprio uso (2 kg) = 1 pacote de 10 kg.
		festa = _nova_festa(publico_intermediario=1)
		produto = _novo_produto(festa, expectativa_venda_por_pessoa=1)
		compra = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Queijo",
				"usado_em_produtos": 1,
				"unidade_compra": "kg",
				"quantidade_compra_final": 10,
				"cotacoes": [
					{
						"fornecedor": "Fornecedor A",
						"valor": 100,
						"quantidade": 10,
						"unidade_medida": "kg",
						"escolhida": 1,
					}
				],
				"usos_em_produto": [
					{
						"produto": produto.name,
						"quantidade_usada": 2,
						"unidade_medida_uso": "kg",
					}
				],
			}
		).insert(ignore_permissions=True)

		uso = compra.usos_em_produto[0]
		# quantidade_compra e a sugestao do cenario ativo, em pacotes inteiros.
		self.assertEqual(flt(compra.quantidade_compra), 1)
		self.assertEqual(flt(uso.fracao_item), 0.2)
		self.assertEqual(flt(uso.valor_uso), 20)

	def test_apenas_uma_cotacao_pode_ser_escolhida(self):
		festa = _nova_festa()
		compra = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Gelo",
				"unidade_compra": "kg",
				"quantidade_compra_final": 10,
				"cotacoes": [
					{"fornecedor": "A", "valor": 10, "quantidade": 1, "unidade_medida": "kg", "escolhida": 1},
					{"fornecedor": "B", "valor": 12, "quantidade": 1, "unidade_medida": "kg", "escolhida": 1},
				],
			}
		)

		self.assertRaises(frappe.ValidationError, compra.insert, ignore_permissions=True)

	def test_compra_sem_previsao_pode_ser_criada_editada_e_removida(self):
		festa = _nova_festa()
		r = criar_compra_sem_previsao(
			festa.name, json.dumps({"nome_item": "Gelo", "valor_total_realizado": 50, "cancelado": 1})
		)
		compra = r["compra"]
		self.assertFalse(compra["previsto"])
		self.assertTrue(compra["cancelado"])
		self.assertEqual(flt(compra["valor_total_realizado"]), 50)

		# Editar nome e desmarcar cancelado (item passou a ser comprado).
		r2 = salvar_compra_sem_previsao(
			compra["name"],
			json.dumps({"nome_item": "Gelo em cubos", "valor_total_realizado": 50, "cancelado": 0}),
		)
		self.assertEqual(r2["compra"]["nome_item"], "Gelo em cubos")
		self.assertFalse(r2["compra"]["cancelado"])

		excluir_compra(compra["name"], festa.name)
		self.assertFalse(frappe.db.exists("Compra Festa", compra["name"]))

	def test_salvar_compra_sem_previsao_recusa_item_previsto(self):
		festa = _nova_festa()
		compra = criar_compra(
			festa.name,
			json.dumps(
				{
					"nome_item": "Carvao",
					"unidade_compra": "kg",
					"unidade_medida_realizado": "kg",
					"quantidade_compra_final": 5,
					"cotacoes": [
						{
							"fornecedor": "A",
							"valor": 10,
							"quantidade": 1,
							"unidade_medida": "kg",
							"escolhida": 1,
						}
					],
				}
			),
		)["compra"]
		self.assertRaises(
			frappe.ValidationError,
			salvar_compra_sem_previsao,
			compra["name"],
			json.dumps({"nome_item": "Outro", "valor_total_realizado": 10}),
		)

	def test_item_cancelado_nao_entra_nas_despesas_do_relatorio(self):
		festa = _nova_festa()
		# Item comprado (entra nas despesas).
		criar_compra_sem_previsao(
			festa.name, json.dumps({"nome_item": "Comprado", "valor_total_realizado": 50, "cancelado": 0})
		)
		# Item cancelado com valor gasto (NÃO deve contar).
		criar_compra_sem_previsao(
			festa.name, json.dumps({"nome_item": "Cancelado", "valor_total_realizado": 200, "cancelado": 1})
		)

		payload = build_relatorio_payload(festa.name)
		self.assertEqual(flt(payload["despesas"]), 50)
		flags = {c["nome_item"]: c["cancelado"] for c in payload["compras"]}
		self.assertTrue(flags["Cancelado"])
		self.assertFalse(flags["Comprado"])

	def test_unidade_incompativel_falha_no_calculo(self):
		festa = _nova_festa()
		compra = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Molho",
				"unidade_compra": "kg",
				"quantidade_compra_final": 1,
				"cotacoes": [
					{
						"fornecedor": "Fornecedor A",
						"valor": 10,
						"quantidade": 1,
						"unidade_medida": "litro",
						"escolhida": 1,
					}
				],
			}
		)

		self.assertRaises(frappe.ValidationError, compra.insert, ignore_permissions=True)
