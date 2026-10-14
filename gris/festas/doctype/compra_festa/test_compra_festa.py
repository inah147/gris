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

		# Quantidade final = nº de cotações: 8 cotações de 2 kg a R$ 20.
		self.assertEqual(flt(compra.valor_total_compra), 160)

	def test_valor_total_com_cotacao_em_outra_unidade(self):
		# Água com gás comprada em ml, cotada a R$ 2,19 a garrafa de 0,5 litro:
		# 6 cotações custam 6 x 2,19, não ⌈6 ml ÷ 500 ml⌉ x 2,19.
		festa = _nova_festa()
		compra = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Agua com gas",
				"unidade_compra": "ml",
				"quantidade_compra_final": 6,
				"cotacoes": [
					{
						"fornecedor": "Atacadao",
						"valor": 2.19,
						"quantidade": 0.5,
						"unidade_medida": "litro",
						"escolhida": 1,
					}
				],
			}
		).insert(ignore_permissions=True)

		self.assertAlmostEqual(flt(compra.valor_total_compra), 13.14, places=2)
		# Item constante: os três cenários compram a própria quantidade final.
		for chave in ("min", "intermediario", "max"):
			self.assertEqual(flt(compra.get(f"qtd_sugerida_{chave}")), 6)
			self.assertAlmostEqual(flt(compra.get(f"valor_total_{chave}")), 13.14, places=2)

	def test_cenario_arredonda_sem_erro_de_ponto_flutuante(self):
		# 70 g x 100 produtos convertidos para kg dá 7,000000000000001 em float:
		# são 7 pacotes de 1 kg, não 8.
		festa = _nova_festa(publico_intermediario=100)
		produto = _novo_produto(festa, expectativa_venda_por_pessoa=1)
		compra = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Farinha",
				"usado_em_produtos": 1,
				"unidade_compra": "kg",
				"quantidade_compra_final": 7,
				"cotacoes": [
					{
						"fornecedor": "Fornecedor A",
						"valor": 10,
						"quantidade": 1,
						"unidade_medida": "kg",
						"escolhida": 1,
					}
				],
				"usos_em_produto": [
					{"produto": produto.name, "quantidade_usada": 70, "unidade_medida_uso": "g"}
				],
			}
		).insert(ignore_permissions=True)

		self.assertEqual(flt(compra.qtd_sugerida_intermediario), 7)

	def test_sobra_desconta_o_consumo_do_cenario(self):
		# 0,5 kg x 30 produtos = 15 kg; 2 pacotes de 10 kg = 20 kg -> sobram 5 kg,
		# que valem metade de um pacote de R$ 100.
		festa = _nova_festa(publico_intermediario=30)
		produto = _novo_produto(festa, expectativa_venda_por_pessoa=1)
		compra = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Queijo ralado",
				"usado_em_produtos": 1,
				"unidade_compra": "kg",
				"quantidade_compra_final": 2,
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
					{"produto": produto.name, "quantidade_usada": 0.5, "unidade_medida_uso": "kg"}
				],
			}
		).insert(ignore_permissions=True)

		self.assertEqual(flt(compra.qtd_sugerida_intermediario), 2)
		self.assertEqual(flt(compra.qtd_sobra_individual_intermediario), 5)
		self.assertEqual(flt(compra.valor_sobra_intermediario), 50)

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

	def test_patch_recalcula_compras_gravadas(self):
		from gris.patches.recalcular_valor_total_compra_festa import execute

		festa = _nova_festa()
		cotacao = {"fornecedor": "Atacadao", "unidade_medida": "litro", "escolhida": 1}
		agua = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Agua com gas",
				"unidade_compra": "ml",
				"quantidade_compra_final": 6,
				"cotacoes": [{**cotacao, "valor": 2.19, "quantidade": 0.5}],
			}
		).insert(ignore_permissions=True)
		refri = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Refrigerante",
				"unidade_compra": "litro",
				"quantidade_compra_final": 0.2,
				"cotacoes": [{**cotacao, "valor": 5, "quantidade": 0.5}],
			}
		).insert(ignore_permissions=True)
		# O que a regra antiga gravou: ⌈6 ml ÷ 500 ml⌉ x 2,19 e 1 cotação no cenário;
		# no item "varia com o público", 0,2 litro por pessoa virou 40 garrafas.
		frappe.db.set_value(
			"Compra Festa",
			agua.name,
			{"valor_total_compra": 2.19, "qtd_sugerida_intermediario": 1},
			update_modified=False,
		)
		frappe.db.set_value(
			"Compra Festa",
			refri.name,
			{"varia_com_publico": 1, "quantidade_compra": 40, "valor_total_compra": 5},
			update_modified=False,
		)
		modified = frappe.db.get_value("Compra Festa", agua.name, "modified")
		# Festa antiga que reprova a validação: o patch refaz o orçamento sem save().
		frappe.db.set_value("Festa", festa.name, "data_limite_vendas", add_days(festa.data, 1))
		frappe.db.sql("update `tabLista de Compras Festa` set valor_total = 0 where parent = %s", festa.name)

		execute()

		agua.reload()
		self.assertAlmostEqual(flt(agua.valor_total_compra), 13.14, places=2)
		self.assertEqual(flt(agua.qtd_sugerida_intermediario), 6)
		self.assertEqual(agua.modified, modified)
		refri.reload()
		self.assertEqual(flt(refri.quantidade_compra_final), 40)
		self.assertEqual(flt(refri.valor_total_compra), 200)
		festa.reload()
		totais_lista = {linha.item: flt(linha.valor_total) for linha in festa.lista_compras}
		self.assertAlmostEqual(totais_lista["Agua com gas"], 13.14, places=2)
