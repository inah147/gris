# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes do planejamento da sincronização de seções.

`planejar_secoes` é pura: recebe os associados já lidos e decide quais seções
viram área, quem chefia cada uma e que função cada escotista recebe.
"""

from frappe.tests.utils import FrappeTestCase

from gris.api.gestao_adultos.secoes import (
	PAPEL_ASSISTENTE,
	PAPEL_CHEFE,
	planejar_secoes,
	titulo_da_funcao,
)


def _pessoa(nome, secao, categoria="Escotista", funcao=""):
	return {"name": nome, "nome_completo": nome, "secao": secao, "categoria": categoria, "funcao": funcao}


class TestPlanejarSecoes(FrappeTestCase):
	def test_toda_secao_vira_area(self):
		plano = planejar_secoes(
			[
				_pessoa("Ana", "Alcateia"),
				_pessoa("Bia", "Tropa Escoteira"),
				# Benefício também define que a seção existe.
				_pessoa("Caio", "Clã Pioneiro", categoria="Beneficiário"),
			]
		)

		self.assertEqual(plano["secoes"], ["Alcateia", "Clã Pioneiro", "Tropa Escoteira"])

	def test_secao_em_branco_nao_vira_area(self):
		plano = planejar_secoes([_pessoa("Ana", ""), _pessoa("Bia", "   "), _pessoa("Caio", None)])

		self.assertEqual(plano["secoes"], [])

	def test_grafias_diferentes_da_mesma_secao_viram_uma_area(self):
		"""`secao` é texto livre de planilha: acento e caixa não podem duplicar a área."""
		plano = planejar_secoes([_pessoa("Ana", "Alcateia"), _pessoa("Bia", "ALCATÉIA")])

		self.assertEqual(plano["secoes"], ["Alcateia"])
		self.assertEqual(set(plano["atribuicoes"]), {"Ana", "Bia"})

	def test_chefe_vira_responsavel_e_o_resto_assistente(self):
		plano = planejar_secoes(
			[
				_pessoa("Ana", "Alcateia", funcao="Chefe de Seção"),
				_pessoa("Bia", "Alcateia", funcao="Metalúrgico"),
			]
		)

		self.assertEqual(plano["responsaveis"], {"Alcateia": "Ana"})
		self.assertEqual(plano["atribuicoes"]["Ana"], {"Alcateia": PAPEL_CHEFE})
		self.assertEqual(plano["atribuicoes"]["Bia"], {"Alcateia": PAPEL_ASSISTENTE})

	def test_chefia_e_reconhecida_sem_acento_e_em_caixa_qualquer(self):
		plano = planejar_secoes([_pessoa("Ana", "Alcateia", funcao="CHEFE DA SECAO")])

		self.assertEqual(plano["responsaveis"], {"Alcateia": "Ana"})

	def test_dois_chefes_deixam_a_secao_sem_responsavel(self):
		plano = planejar_secoes(
			[
				_pessoa("Ana", "Alcateia", funcao="Chefe de Seção"),
				_pessoa("Bia", "Alcateia", funcao="Chefe de Seção"),
			]
		)

		self.assertEqual(plano["responsaveis"], {})
		self.assertTrue(any("mais de um chefe" in a for a in plano["avisos"]))
		# Ambos continuam como chefes na própria função.
		self.assertEqual(plano["atribuicoes"]["Ana"], {"Alcateia": PAPEL_CHEFE})
		self.assertEqual(plano["atribuicoes"]["Bia"], {"Alcateia": PAPEL_CHEFE})

	def test_secao_sem_chefe_avisa(self):
		plano = planejar_secoes([_pessoa("Ana", "Alcateia")])

		self.assertEqual(plano["responsaveis"], {})
		self.assertTrue(any("não tem chefe" in a for a in plano["avisos"]))

	def test_secao_so_com_beneficiario_vira_area_mas_avisa(self):
		plano = planejar_secoes([_pessoa("Caio", "Alcateia", categoria="Beneficiário")])

		self.assertEqual(plano["secoes"], ["Alcateia"])
		self.assertEqual(plano["atribuicoes"], {})
		self.assertTrue(any("nenhum escotista" in a for a in plano["avisos"]))

	def test_nao_escotista_na_secao_nao_recebe_funcao(self):
		plano = planejar_secoes(
			[
				_pessoa("Ana", "Alcateia", funcao="Chefe de Seção"),
				_pessoa("Dirigente", "Alcateia", categoria="Dirigente"),
			]
		)

		self.assertEqual(set(plano["atribuicoes"]), {"Ana"})

	def test_escotista_em_duas_secoes_recebe_uma_funcao_em_cada(self):
		"""Uma linha por seção: é o que coloca a pessoa em dois pontos do organograma."""
		plano = planejar_secoes(
			[
				_pessoa("Ana", "Alcateia", funcao="Chefe de Seção"),
				{
					"name": "Ana",
					"nome_completo": "Ana",
					"secao": "Tropa Escoteira",
					"categoria": "Escotista",
					"funcao": "Assistente",
				},
			]
		)

		self.assertEqual(
			plano["atribuicoes"]["Ana"],
			{"Alcateia": PAPEL_CHEFE, "Tropa Escoteira": PAPEL_ASSISTENTE},
		)

	def test_titulo_da_funcao_amarra_papel_e_secao(self):
		"""`Funcao Voluntario.area` é Link único: não existe chefe de seção genérico."""
		titulo = titulo_da_funcao(PAPEL_CHEFE, "Alcateia")

		self.assertIn("Chefe de Seção", titulo)
		self.assertIn("Alcateia", titulo)
		self.assertNotEqual(titulo, titulo_da_funcao(PAPEL_CHEFE, "Tropa Escoteira"))
