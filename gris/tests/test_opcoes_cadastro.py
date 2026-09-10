"""Sincronia entre as listas de opções do Paxtu e o schema dos DocTypes.

O cadastro do GRIS é transcrito à mão para o Paxtu. Quando uma opção diverge — na grafia, na
ordem ou nos itens — quem transcreve reescreve o valor em vez de copiá-lo. As listas foram
unificadas em ``gris.utils.opcoes_cadastro``, e é este teste que impede a divergência voltar:
sem ele, editar o JSON de um DocType e esquecer o outro passa despercebido.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.utils import opcoes_cadastro


class TestOpcoesCadastro(FrappeTestCase):
	def test_selects_dos_doctypes_batem_com_as_listas_canonicas(self):
		for doctype, campos in opcoes_cadastro.CAMPOS_SELECT_POR_DOCTYPE.items():
			meta = frappe.get_meta(doctype)
			for fieldname, valores in campos.items():
				with self.subTest(doctype=doctype, fieldname=fieldname):
					campo = meta.get_field(fieldname)
					self.assertIsNotNone(campo, f"{doctype}.{fieldname} não existe")
					self.assertEqual(campo.fieldtype, "Select")
					self.assertEqual(campo.options, opcoes_cadastro.opcoes_do_doctype(valores))

	def test_opcoes_comecam_em_branco_para_nada_ser_escolhido_sozinho(self):
		"""O Frappe escolhe a primeira opção quando não há uma vazia — e o Paxtu abre em "Selecione"."""
		for doctype, campos in opcoes_cadastro.CAMPOS_SELECT_POR_DOCTYPE.items():
			meta = frappe.get_meta(doctype)
			for fieldname in campos:
				with self.subTest(doctype=doctype, fieldname=fieldname):
					self.assertTrue(meta.get_field(fieldname).options.startswith("\n"))

	def test_escolaridade_segue_a_ordem_do_paxtu(self):
		lista = opcoes_cadastro.ESCOLARIDADE
		self.assertEqual(lista[0], "Não Informado")
		self.assertLess(
			lista.index("Especialização incompleta"),
			lista.index("Especialização completa"),
			"o Paxtu lista a especialização incompleta antes da completa",
		)

	def test_grafias_antigas_apontam_para_opcoes_que_existem(self):
		for campo, mapa in opcoes_cadastro.GRAFIAS_ANTIGAS.items():
			for antigo, novo in mapa.items():
				with self.subTest(campo=campo, antigo=antigo):
					self.assertIn(novo, opcoes_cadastro.LISTAS_POR_CAMPO[campo])
					self.assertNotIn(antigo, opcoes_cadastro.LISTAS_POR_CAMPO[campo])

	def test_profissao_mantem_os_itens_fixos_no_topo(self):
		"""O Paxtu exibe "* Estudante *" e "* Outras Profissões *" antes da ordem alfabética."""
		self.assertEqual(opcoes_cadastro.PROFISSAO[:2], ["* Estudante *", "* Outras Profissões *"])

	def test_profissao_segue_como_texto_livre_no_schema(self):
		"""A lista transcrita do Paxtu ainda está incompleta: um Select recusaria o que falta nela.

		A lista fechada é oferecida no formulário (ver ``_enriquecer_opcoes_do_formulario``);
		o schema só pode fechar quando a transcrição terminar, junto de um patch dos dados.
		"""
		for doctype, fieldname in (("Novo Associado", "profissao"), ("Responsavel", "profissão")):
			with self.subTest(doctype=doctype):
				self.assertEqual(frappe.get_meta(doctype).get_field(fieldname).fieldtype, "Data")

	def test_uf_exibe_o_nome_por_extenso_e_grava_a_sigla(self):
		itens = opcoes_cadastro.itens_uf()
		self.assertEqual(itens[0]["value"], "")
		sao_paulo = next(item for item in itens if item["value"] == "SP")
		self.assertEqual(sao_paulo["label"], "São Paulo")
		self.assertEqual(len(itens), 28)

	def test_pais_usa_o_formato_que_o_paxtu_exibe(self):
		itens = opcoes_cadastro.itens_paises()
		valores = [item["value"] for item in itens]
		self.assertIn(opcoes_cadastro.pais_brasil(), valores)
		self.assertEqual(opcoes_cadastro.pais_brasil(), "BR - Brasil")
		# Rótulo e valor são iguais: é o rótulo que a recepção copia para o Paxtu.
		brasil = next(item for item in itens if item["value"] == opcoes_cadastro.pais_brasil())
		self.assertEqual(brasil["label"], brasil["value"])
