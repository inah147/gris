# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes do planejamento da sincronização de seções.

`planejar_secoes` e `planejar_linhas` são puras: a primeira recebe os associados
já lidos e decide quais seções viram área, quem chefia cada uma e que função cada
escotista recebe; a segunda decide o que fazer com as linhas de função interna de
uma pessoa.
"""

from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from gris.api.gestao_adultos.secoes import (
	PAPEL_ASSISTENTE,
	PAPEL_CHEFE,
	planejar_linhas,
	planejar_secoes,
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

	def test_papel_e_generico_e_a_secao_vem_do_plano(self):
		"""A seção saiu do título da função: quem diz onde é o par (papel, seção)."""
		plano = planejar_secoes(
			[
				_pessoa("Ana", "Alcateia", funcao="Chefe de Seção"),
				_pessoa("Bia", "Tropa Escoteira", funcao="Chefe de Seção"),
			]
		)

		# O mesmo papel serve as duas seções — é isso que o vínculo M:N permitiu.
		self.assertEqual(plano["atribuicoes"]["Ana"], {"Alcateia": PAPEL_CHEFE})
		self.assertEqual(plano["atribuicoes"]["Bia"], {"Tropa Escoteira": PAPEL_CHEFE})
		self.assertNotIn("Alcateia", PAPEL_CHEFE)
		self.assertNotIn("Tropa", PAPEL_CHEFE)


HOJE = getdate("2026-09-23")
AUTOMATICAS = {PAPEL_CHEFE, PAPEL_ASSISTENTE}
AREAS_AUTOMATICAS = {"Alcateia", "Tropa Escoteira"}


def _linha(funcao, area, data_fim=None):
	return {"funcao": funcao, "area": area, "data_fim": data_fim}


class TestPlanejarLinhas(FrappeTestCase):
	"""O que a sincronização pode mexer nas funções internas de uma pessoa."""

	def _planejar(self, linhas, desejados):
		return planejar_linhas(linhas, desejados, AUTOMATICAS, AREAS_AUTOMATICAS, HOJE)

	def test_abre_o_par_que_falta(self):
		plano = self._planejar([], {(PAPEL_CHEFE, "Alcateia")})

		self.assertEqual(plano["abrir"], [(PAPEL_CHEFE, "Alcateia")])
		self.assertEqual(plano["encerrar"], [])

	def test_promocao_encerra_o_antigo_e_abre_o_novo(self):
		linhas = [_linha(PAPEL_ASSISTENTE, "Alcateia")]

		plano = self._planejar(linhas, {(PAPEL_CHEFE, "Alcateia")})

		self.assertEqual(plano["encerrar"], [0])
		self.assertEqual(plano["abrir"], [(PAPEL_CHEFE, "Alcateia")])

	def test_saiu_da_secao_encerra(self):
		plano = self._planejar([_linha(PAPEL_CHEFE, "Alcateia")], set())

		self.assertEqual(plano["encerrar"], [0])

	def test_voltou_para_a_secao_reabre_em_vez_de_duplicar(self):
		linhas = [_linha(PAPEL_CHEFE, "Alcateia", data_fim=getdate("2026-01-10"))]

		plano = self._planejar(linhas, {(PAPEL_CHEFE, "Alcateia")})

		self.assertEqual(plano["reabrir"], [0])
		self.assertEqual(plano["abrir"], [])

	def test_funcao_generica_em_area_feita_a_mao_fica_intocada(self):
		"""O caso que a função genérica criou: o título sozinho não diz mais de quem é a linha.

		"Chefe de Seção" é sempre automática agora. Sem cruzar com a área, a rotina
		encerraria uma lotação que um humano criou numa área que ela nunca tocou.
		"""
		linhas = [_linha(PAPEL_CHEFE, "Equipe de Apoio")]

		plano = self._planejar(linhas, set())

		self.assertEqual(plano["encerrar"], [])
		self.assertEqual(plano["reabrir"], [])

	def test_funcao_nao_automatica_em_area_automatica_fica_intocada(self):
		plano = self._planejar([_linha("Diretor(a) Presidente", "Alcateia")], set())

		self.assertEqual(plano["encerrar"], [])

	def test_linha_sem_area_nunca_e_encerrada(self):
		"""Linha legada, de função que nunca teve área: ambígua demais para mexer."""
		plano = self._planejar([_linha(PAPEL_CHEFE, None)], set())

		self.assertEqual(plano["encerrar"], [])

	def test_pessoa_em_duas_secoes_gera_dois_pares(self):
		desejados = {(PAPEL_CHEFE, "Alcateia"), (PAPEL_ASSISTENTE, "Tropa Escoteira")}

		plano = self._planejar([], desejados)

		self.assertEqual(
			plano["abrir"],
			[(PAPEL_ASSISTENTE, "Tropa Escoteira"), (PAPEL_CHEFE, "Alcateia")],
		)

	def test_mesma_funcao_em_duas_areas_nao_se_confunde(self):
		"""Só a área distingue as duas linhas; encerrar uma não pode encerrar a outra."""
		linhas = [_linha(PAPEL_CHEFE, "Alcateia"), _linha(PAPEL_CHEFE, "Tropa Escoteira")]

		plano = self._planejar(linhas, {(PAPEL_CHEFE, "Alcateia")})

		self.assertEqual(plano["encerrar"], [1])
		self.assertEqual(plano["abrir"], [])
