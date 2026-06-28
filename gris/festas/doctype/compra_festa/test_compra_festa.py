import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today


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
		# Público intermediário=1 e expectativa=1 → qtd do produto no cenário = 1,
		# de modo que a necessidade do queijo seja exatamente o uso (2 kg).
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
		self.assertEqual(flt(compra.quantidade_compra), 2)
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

	def test_varia_com_publico_sugestao_por_consumo_e_valor_por_final(self):
		# Coca-cola: consumo 0,6 L/pessoa (2 copos x 300 ml); público 150/200/250.
		# Cotação em ml para exercitar a conversão ml -> litro.
		festa = _nova_festa(publico_min=150, publico_intermediario=200, publico_max=250)
		compra = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Coca-Cola",
				"varia_com_publico": 1,
				"unidade_compra": "litro",
				"consumo_por_pessoa": 0.6,
				# Quantidade final = total absoluto que será comprado (decidido pelo usuário),
				# propositalmente diferente da sugestão do cenário ativo (120 L).
				"quantidade_compra_final": 100,
				"cotacoes": [
					{
						"fornecedor": "Fornecedor A",
						"valor": 10.49,
						"quantidade": 2500,
						"unidade_medida": "ml",
						"escolhida": 1,
					}
				],
			}
		).insert(ignore_permissions=True)

		# Quantidade sugerida (indicativa) = consumo por pessoa x público, na unidade de medida.
		self.assertEqual(flt(compra.qtd_sugerida_min, 2), 90)
		self.assertEqual(flt(compra.qtd_sugerida_intermediario, 2), 120)
		self.assertEqual(flt(compra.qtd_sugerida_max, 2), 150)

		# Valor total de compra = pacotes inteiros da QUANTIDADE FINAL (100 L), não da sugestão.
		# ceil(100/2,5)=40 -> 40*10,49
		self.assertEqual(flt(compra.valor_total_compra, 2), flt(40 * 10.49, 2))

		# Valor indicativo por cenário continua baseado na sugestão (90/120/150 L).
		self.assertEqual(flt(compra.valor_total_min, 2), flt(36 * 10.49, 2))
		self.assertEqual(flt(compra.valor_total_intermediario, 2), flt(48 * 10.49, 2))

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
