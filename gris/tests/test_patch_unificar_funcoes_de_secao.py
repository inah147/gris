# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes do planejamento da fusão das funções de seção.

`planejar_fusao` é pura: decide quais títulos viram qual papel genérico, e em que
seção a pessoa passa a estar. O critério é restritivo de propósito — função
batizada à mão não pode ser engolida pela migração.
"""

from unittest import TestCase

from gris.patches.unificar_funcoes_de_secao import (
	PAPEL_ASSISTENTE,
	PAPEL_CHEFE,
	SEPARADOR,
	planejar_fusao,
)


def _funcao(nome, origem_automatica=1):
	return {"name": nome, "origem_automatica": origem_automatica}


class TestPlanejarFusao(TestCase):
	def test_chefe_de_secao_vira_generica_com_a_secao_na_area(self):
		plano = planejar_fusao([_funcao(f"{PAPEL_CHEFE}{SEPARADOR}Alcateia")])

		self.assertEqual(plano, {f"{PAPEL_CHEFE}{SEPARADOR}Alcateia": (PAPEL_CHEFE, "Alcateia")})

	def test_assistente_de_secao_tambem(self):
		titulo = f"{PAPEL_ASSISTENTE}{SEPARADOR}Tropa Escoteira"

		plano = planejar_fusao([_funcao(titulo)])

		self.assertEqual(plano, {titulo: (PAPEL_ASSISTENTE, "Tropa Escoteira")})

	def test_secao_com_espaco_e_acento_sobrevive(self):
		titulo = f"{PAPEL_CHEFE}{SEPARADOR}Clã Chefe Alvim"

		plano = planejar_fusao([_funcao(titulo)])

		self.assertEqual(plano[titulo], (PAPEL_CHEFE, "Clã Chefe Alvim"))

	def test_funcao_feita_a_mao_nao_e_fundida(self):
		"""Sem `origem_automatica`, é decisão humana — a migração não passa por cima."""
		plano = planejar_fusao([_funcao(f"{PAPEL_CHEFE}{SEPARADOR}Alcateia", origem_automatica=0)])

		self.assertEqual(plano, {})

	def test_papel_desconhecido_nao_e_fundido(self):
		plano = planejar_fusao([_funcao(f"Chefe de Equipe{SEPARADOR}Alcateia")])

		self.assertEqual(plano, {})

	def test_funcao_ja_generica_nao_entra(self):
		plano = planejar_fusao([_funcao(PAPEL_CHEFE)])

		self.assertEqual(plano, {})

	def test_separador_precisa_ser_o_travessao(self):
		"""Hífen comum não é o separador que a sincronização usava."""
		plano = planejar_fusao([_funcao(f"{PAPEL_CHEFE} - Alcateia")])

		self.assertEqual(plano, {})

	def test_titulo_sem_secao_depois_do_separador_e_ignorado(self):
		plano = planejar_fusao([_funcao(f"{PAPEL_CHEFE}{SEPARADOR}   ")])

		self.assertEqual(plano, {})

	def test_varias_secoes_apontam_para_o_mesmo_papel(self):
		plano = planejar_fusao(
			[
				_funcao(f"{PAPEL_CHEFE}{SEPARADOR}Alcateia"),
				_funcao(f"{PAPEL_CHEFE}{SEPARADOR}Tropa Sênior"),
			]
		)

		self.assertEqual({papel for papel, _ in plano.values()}, {PAPEL_CHEFE})
		self.assertEqual({secao for _, secao in plano.values()}, {"Alcateia", "Tropa Sênior"})
