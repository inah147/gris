# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from gris.api.festas import copiar_dados_festa_anterior


def _nova_festa():
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
	return festa


def _completar_portaria(festa_name: str, **campos) -> None:
	portaria = frappe.get_doc("Area da Festa", f"{festa_name} - Portaria")
	portaria.tipo_coord = "Outro"
	portaria.nome_coord = campos.get("nome_coord", "Coord Portaria")
	portaria.email_coord = campos.get("email_coord", "portaria@example.com")
	portaria.telefone_coord = campos.get("telefone_coord", "+5511999999999")
	portaria.save(ignore_permissions=True)


class TestCopiarFesta(FrappeTestCase):
	def _montar_festa_origem(self):
		origem = _nova_festa()
		_completar_portaria(origem.name)

		area = frappe.get_doc(
			{
				"doctype": "Area da Festa",
				"festa": origem.name,
				"nome_area": "Alimentação",
				"descricao": "Barracas de comida",
				"tipo_coord": "Outro",
				"nome_coord": "Ana",
				"email_coord": "ana@example.com",
				"telefone_coord": "+5511988887777",
				"equipe": [
					{
						"tipo_pessoa": "Outro",
						"nome": "Bia",
						"email": "bia@example.com",
						"telefone": "+5511977776666",
						"funcao": "Apoio",
					}
				],
			}
		).insert(ignore_permissions=True)

		barraca = frappe.get_doc(
			{
				"doctype": "Barraca da Festa",
				"festa": origem.name,
				"area": area.name,
				"nome_barraca": "Barraca Lanches",
				"tipo_coord": "Outro",
				"nome_coord": "Carlos",
				"email_coord": "carlos@example.com",
				"telefone_coord": "+5511966665555",
				"valor_arrecadado_realizado_real": 999,
			}
		).insert(ignore_permissions=True)

		produto = frappe.get_doc(
			{
				"doctype": "Produto de Venda Festa",
				"festa": origem.name,
				"nome_produto": "Cachorro-quente",
				"barraca": barraca.name,
				"preco_venda": 12,
				"expectativa_venda_por_pessoa": 1,
				"qtd_realizada_vendas": 40,
			}
		).insert(ignore_permissions=True)

		compra = frappe.get_doc(
			{
				"doctype": "Compra Festa",
				"festa": origem.name,
				"nome_item": "Pão",
				"area": area.name,
				"unidade_compra": "unidade",
				"quantidade_compra_final": 50,
				"usado_em_produtos": 1,
				"cotacoes": [
					{
						"fornecedor": "Padaria X",
						"valor": 30,
						"quantidade": 50,
						"unidade_medida": "unidade",
						"escolhida": 1,
					}
				],
				"usos_em_produto": [
					{
						"produto": produto.name,
						"quantidade_usada": 1,
						"unidade_medida_uso": "unidade",
					}
				],
				"valor_total_realizado": 500,
				"fornecedor_realizado": "Padaria X",
			}
		).insert(ignore_permissions=True)

		contratacao = frappe.get_doc(
			{
				"doctype": "Contratacao Festa",
				"festa": origem.name,
				"nome_item": "Som",
				"area": area.name,
				"cotacoes": [
					{"fornecedor": "Som & Cia", "valor": 300, "escolhida": 1},
				],
				"valor_total_realizado": 280,
				"fornecedor_realizado": "Som & Cia",
			}
		).insert(ignore_permissions=True)

		convite = frappe.get_doc(
			{
				"doctype": "Opcao Convite Festa",
				"festa": origem.name,
				"nome_convite": "Adulto",
				"ramo": "Escoteiro",
				"ativo": 1,
				"valor": 25,
				"valor_consumacao": 10,
				"quantidade_esperada": 100,
				"quantidade_vendida": 87,
			}
		).insert(ignore_permissions=True)

		convite_portaria = frappe.get_doc(
			{
				"doctype": "Opcao Convite Festa",
				"festa": origem.name,
				"nome_convite": "Portaria",
				"portaria": 1,
				"ativo": 1,
				"valor": 30,
			}
		).insert(ignore_permissions=True)

		return {
			"festa": origem,
			"area": area,
			"barraca": barraca,
			"produto": produto,
			"compra": compra,
			"contratacao": contratacao,
			"convite": convite,
			"convite_portaria": convite_portaria,
		}

	def test_copia_areas_barracas_e_produtos(self):
		origem = self._montar_festa_origem()
		destino = _nova_festa()

		copiar_dados_festa_anterior(destino.name, origem["festa"].name)

		area_destino = frappe.get_doc("Area da Festa", f"{destino.name} - Alimentação")
		self.assertEqual(area_destino.descricao, "Barracas de comida")
		self.assertEqual(len(area_destino.equipe), 1)
		self.assertEqual(area_destino.equipe[0].nome, "Bia")

		barraca_destino = frappe.get_doc("Barraca da Festa", f"{destino.name} - Barraca Lanches")
		self.assertEqual(barraca_destino.area, area_destino.name)
		self.assertEqual(barraca_destino.nome_coord, "Carlos")
		# Resultado realizado não é copiado — cada festa apura o seu.
		self.assertEqual(flt(barraca_destino.valor_arrecadado_realizado_real), 0)

		produto_destino = frappe.get_doc(
			"Produto de Venda Festa", f"{destino.name} - Cachorro-quente"
		)
		self.assertEqual(produto_destino.barraca, barraca_destino.name)
		self.assertEqual(flt(produto_destino.preco_venda), 12)
		self.assertEqual(flt(produto_destino.qtd_realizada_vendas), 0)

	def test_copia_portaria_atualiza_area_existente_sem_duplicar(self):
		origem = self._montar_festa_origem()
		destino = _nova_festa()

		copiar_dados_festa_anterior(destino.name, origem["festa"].name)

		portaria_destino = frappe.get_doc("Area da Festa", f"{destino.name} - Portaria")
		self.assertEqual(portaria_destino.nome_coord, "Coord Portaria")
		self.assertEqual(portaria_destino.email_coord, "portaria@example.com")

		total_portarias = frappe.db.count(
			"Area da Festa", {"festa": destino.name, "nome_area": "Portaria"}
		)
		self.assertEqual(total_portarias, 1)

	def test_copia_compras_e_contratacoes_sem_valores_realizados(self):
		origem = self._montar_festa_origem()
		destino = _nova_festa()

		copiar_dados_festa_anterior(destino.name, origem["festa"].name)

		compra_destino = frappe.get_doc("Compra Festa", f"{destino.name} - Pão")
		self.assertEqual(len(compra_destino.cotacoes), 1)
		self.assertEqual(compra_destino.cotacoes[0].fornecedor, "Padaria X")
		self.assertEqual(len(compra_destino.usos_em_produto), 1)
		produto_destino_name = f"{destino.name} - Cachorro-quente"
		self.assertEqual(compra_destino.usos_em_produto[0].produto, produto_destino_name)
		# Resultado realizado não é copiado.
		self.assertEqual(flt(compra_destino.valor_total_realizado), 0)
		self.assertFalse(compra_destino.fornecedor_realizado)

		# O uso da compra recalcula o custo do produto de destino (preco_custo).
		produto_destino = frappe.get_doc("Produto de Venda Festa", produto_destino_name)
		self.assertGreater(flt(produto_destino.preco_custo), 0)

		contratacao_destino = frappe.get_doc("Contratacao Festa", f"{destino.name} - Som")
		self.assertEqual(len(contratacao_destino.cotacoes), 1)
		self.assertEqual(flt(contratacao_destino.valor_total_contratacao), 300)
		self.assertEqual(flt(contratacao_destino.valor_total_realizado), 0)

	def test_copia_convites_ignora_portaria_e_zera_vendidos(self):
		origem = self._montar_festa_origem()
		destino = _nova_festa()

		copiar_dados_festa_anterior(destino.name, origem["festa"].name)

		convite_destino = frappe.get_doc("Opcao Convite Festa", f"{destino.name} - Adulto")
		self.assertEqual(flt(convite_destino.valor), 25)
		self.assertEqual(flt(convite_destino.valor_consumacao), 10)
		self.assertEqual(convite_destino.quantidade_esperada, 100)
		self.assertEqual(convite_destino.quantidade_vendida, 0)

		self.assertFalse(
			frappe.db.exists("Opcao Convite Festa", f"{destino.name} - Portaria")
		)

	def test_recusa_copiar_de_festa_inexistente(self):
		destino = _nova_festa()
		with self.assertRaises(frappe.ValidationError):
			copiar_dados_festa_anterior(destino.name, "Festa Que Nao Existe")

	def test_recusa_copiar_de_si_mesma(self):
		destino = _nova_festa()
		with self.assertRaises(frappe.ValidationError):
			copiar_dados_festa_anterior(destino.name, destino.name)
