# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from gris.api.festas import excluir_barraca, excluir_produto


def _completar_portaria(festa_name: str) -> None:
	portaria = frappe.get_doc("Area da Festa", f"{festa_name} - Portaria")
	portaria.nome_coord = "Coord Portaria"
	portaria.email_coord = "portaria@example.com"
	portaria.telefone_coord = "+5511999999999"
	portaria.save(ignore_permissions=True)


class TestExcluirItensFesta(FrappeTestCase):
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

	def _nova_barraca(self, festa):
		return frappe.get_doc(
			{
				"doctype": "Barraca da Festa",
				"festa": festa.name,
				"area": f"{festa.name} - Portaria",
				"nome_barraca": "Barraca Lanches",
				"tipo_coord": "Outro",
			}
		).insert(ignore_permissions=True)

	def _novo_produto(self, festa, barraca=None):
		return frappe.get_doc(
			{
				"doctype": "Produto de Venda Festa",
				"festa": festa.name,
				"nome_produto": "Cachorro-quente",
				"barraca": barraca.name if barraca else None,
				"preco_venda": 10,
				"expectativa_venda_por_pessoa": 1,
			}
		).insert(ignore_permissions=True)

	# ---------- Produto ----------

	def test_excluir_produto_sem_uso_remove(self):
		festa = self._nova_festa()
		produto = self._novo_produto(festa)

		resultado = excluir_produto(produto.name, festa.name)

		self.assertTrue(resultado["ok"])
		self.assertFalse(frappe.db.exists("Produto de Venda Festa", produto.name))

	def test_excluir_produto_com_compra_bloqueia(self):
		festa = self._nova_festa()
		produto = self._novo_produto(festa)
		frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": festa.name,
				"nome_item": "Pão de cachorro-quente",
				"unidade_compra": "unidade",
				"quantidade_compra_final": 50,
				"usos_em_produto": [
					{
						"produto": produto.name,
						"quantidade_usada": 1,
						"unidade_medida_uso": "unidade",
					}
				],
			}
		).insert(ignore_permissions=True)

		resultado = excluir_produto(produto.name, festa.name)

		self.assertFalse(resultado["ok"])
		self.assertEqual(resultado["bloqueado"], "compras")
		self.assertIn("Pão de cachorro-quente", resultado["itens"])
		self.assertTrue(frappe.db.exists("Produto de Venda Festa", produto.name))

	# ---------- Barraca ----------

	def test_excluir_barraca_com_produto_bloqueia(self):
		festa = self._nova_festa()
		barraca = self._nova_barraca(festa)
		produto = self._novo_produto(festa, barraca=barraca)

		resultado = excluir_barraca(barraca.name, festa.name)

		self.assertFalse(resultado["ok"])
		self.assertEqual(resultado["bloqueado"], "produtos")
		self.assertIn(produto.nome_produto, resultado["itens"])
		self.assertTrue(frappe.db.exists("Barraca da Festa", barraca.name))

	def test_excluir_barraca_sem_produto_remove_e_limpa_orcamento(self):
		festa = self._nova_festa()
		barraca = self._nova_barraca(festa)

		# A criação da barraca dispara a re-agregação do orçamento, gerando
		# linhas de receita/despesa por barraca que a referenciam.
		festa.reload()
		self.assertTrue(any(r.barraca == barraca.name for r in festa.receitas_por_barraca))

		resultado = excluir_barraca(barraca.name, festa.name)

		self.assertTrue(resultado["ok"])
		self.assertFalse(frappe.db.exists("Barraca da Festa", barraca.name))

		festa.reload()
		self.assertFalse(any(r.barraca == barraca.name for r in festa.receitas_por_barraca))
		self.assertFalse(any(d.barraca == barraca.name for d in festa.despesas_por_barraca))
