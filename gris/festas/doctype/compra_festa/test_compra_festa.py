import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today


def _nova_festa():
	return frappe.get_doc(
		{
			"doctype": "Festa",
			"nome_festa": f"Festa Teste {frappe.generate_hash(length=8)}",
			"data": today(),
			"status": "Em andamento",
		}
	).insert(ignore_permissions=True)


def _novo_produto(festa):
	return frappe.get_doc(
		{
			"doctype": "Produto de Venda Festa",
			"festa": festa.name,
			"nome_produto": f"Produto {frappe.generate_hash(length=6)}",
			"preco_venda": 10,
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
		festa = _nova_festa()
		produto = _novo_produto(festa)
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
