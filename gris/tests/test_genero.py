# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes da concordância de gênero usada nos textos enviados a pessoas."""

from frappe.tests.utils import FrappeTestCase

from gris.utils import genero


class TestGenero(FrappeTestCase):
	def test_flexionar_escolhe_pela_forma_do_select(self):
		self.assertEqual(genero.flexionar("Feminino", "filha", "filho"), "filha")
		self.assertEqual(genero.flexionar("Masculino", "filha", "filho"), "filho")

	def test_flexionar_tolera_espacos_e_valores_desconhecidos(self):
		self.assertEqual(genero.flexionar("  Feminino  ", "filha", "filho"), "filha")
		self.assertEqual(genero.flexionar("Outro", "filha", "filho"), "filho(filha)")
		self.assertEqual(genero.flexionar(None, "filha", "filho"), "filho(filha)")
		self.assertEqual(genero.flexionar("", "filha", "filho"), "filho(filha)")

	def test_indefinido_permite_uma_redacao_melhor(self):
		self.assertEqual(genero.flexionar(None, "filha", "filho", "filho(a)"), "filho(a)")
		# Com sexo definido o `indefinido` é ignorado.
		self.assertEqual(genero.flexionar("Feminino", "filha", "filho", "filho(a)"), "filha")

	def test_artigo(self):
		self.assertEqual(genero.artigo("Feminino"), "a")
		self.assertEqual(genero.artigo("Masculino"), "o")
		self.assertEqual(genero.artigo(None), "o(a)")

	def test_contracao_de(self):
		self.assertEqual(genero.de("Feminino"), "da")
		self.assertEqual(genero.de("Masculino"), "do")
		self.assertEqual(genero.de(None), "do(a)")

	def test_contracao_por(self):
		self.assertEqual(genero.por("Feminino"), "pela")
		self.assertEqual(genero.por("Masculino"), "pelo")
		self.assertEqual(genero.por(None), "pelo(a)")

	def test_preposicao_para(self):
		self.assertEqual(genero.para("Feminino"), "a")
		self.assertEqual(genero.para("Masculino"), "ao")
		self.assertEqual(genero.para(None), "a(o)")

	def test_pronome_oblicuo(self):
		self.assertEqual(genero.dele("Feminino"), "dela")
		self.assertEqual(genero.dele("Masculino"), "dele")
		self.assertEqual(genero.dele(None), "dele(a)")

	def test_constantes_casam_com_o_select_dos_doctypes(self):
		"""`Novo Associado`, `Responsavel` e `Associado` gravam exatamente estes rótulos."""
		self.assertEqual(genero.FEMININO, "Feminino")
		self.assertEqual(genero.MASCULINO, "Masculino")
