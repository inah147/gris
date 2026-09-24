# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes do Conselho de Responsáveis no organograma.

`montar_no_conselho` é pura e é testada direto. O resto cobre a estrutura fixa (área
raiz + função) e a trava que impede a área de virar filha de outra.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.gestao_adultos.responsaveis import (
	AREA_CONSELHO,
	FUNCAO_RESPONSAVEL_LEGAL,
	LINHA_RESPONSAVEL,
	PREFIXO_RESPONSAVEL,
	garantir_estrutura_do_conselho,
	montar_no_conselho,
)

PREFIXO = "ZZ Teste Conselho"


class TestMontarNoConselho(FrappeTestCase):
	"""Função pura: sem banco, sem fixture."""

	def test_sem_responsavel_nao_ha_no(self):
		self.assertIsNone(montar_no_conselho([]))

	def test_um_no_por_responsavel_em_ordem_de_nome(self):
		no = montar_no_conselho(
			[
				{"name": "b", "nome_completo": "Beatriz"},
				{"name": "a", "nome_completo": "Ana"},
			]
		)

		self.assertEqual(no["tipo"], "grupo")
		self.assertEqual(no["membros"], 2)
		self.assertEqual([filho["nome"] for filho in no["children"]], ["Ana", "Beatriz"])

	def test_o_grupo_nasce_recolhido(self):
		"""São mais de cem cards: abertos de saída, empurram o resto para fora da tela."""
		no = montar_no_conselho([{"name": "a", "nome_completo": "Ana"}])

		self.assertTrue(no["recolhido"])

	def test_a_chave_da_pessoa_tem_espaco_de_nomes(self):
		"""`Responsavel.name` e `Associado.name` são os dois md5 de CPF."""
		no = montar_no_conselho([{"name": "abc", "nome_completo": "Ana"}])

		filho = no["children"][0]
		self.assertEqual(filho["tipo_pessoa"], "responsavel")
		self.assertEqual(filho["pessoa"], f"{PREFIXO_RESPONSAVEL}abc")
		self.assertIsNone(filho["associado"])

	def test_todo_responsavel_tem_a_funcao_e_a_area_fixas(self):
		no = montar_no_conselho([{"name": "abc", "nome_completo": "Ana Maria Souza"}])

		filho = no["children"][0]
		self.assertEqual(filho["funcao_interna"], FUNCAO_RESPONSAVEL_LEGAL)
		self.assertEqual(filho["area"], AREA_CONSELHO)
		self.assertEqual(filho["linha"], LINHA_RESPONSAVEL)
		self.assertEqual(filho["iniciais"], "AS")

	def test_responsavel_sem_nome_cai_para_o_identificador(self):
		no = montar_no_conselho([{"name": "abc", "nome_completo": None}])

		self.assertEqual(no["children"][0]["nome"], "abc")


class TestEstruturaDoConselho(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_a_area_e_raiz_e_automatica(self):
		garantir_estrutura_do_conselho()

		area = frappe.db.get_value(
			"Unidade Organizacional",
			AREA_CONSELHO,
			["responde_para", "ativa", "origem_automatica"],
			as_dict=True,
		)
		self.assertIsNone(area.responde_para)
		self.assertTrue(area.ativa)
		self.assertTrue(area.origem_automatica)

	def test_a_funcao_existe_e_esta_vinculada_a_area(self):
		garantir_estrutura_do_conselho()

		self.assertTrue(frappe.db.exists("Funcao Voluntario", FUNCAO_RESPONSAVEL_LEGAL))
		self.assertTrue(
			frappe.db.exists(
				"Funcao da Area",
				{
					"parent": AREA_CONSELHO,
					"parenttype": "Unidade Organizacional",
					"funcao": FUNCAO_RESPONSAVEL_LEGAL,
				},
			)
		)

	def test_rodar_de_novo_nao_cria_nada(self):
		garantir_estrutura_do_conselho()

		self.assertEqual(garantir_estrutura_do_conselho(), {"area": 0, "funcao": 0, "vinculo": 0})

	def test_o_conselho_nao_pode_responder_para_outra_area(self):
		"""A tela de administração arrasta áreas; sem a trava, o conselho sai da raiz."""
		garantir_estrutura_do_conselho()
		outra = f"{PREFIXO} Diretoria"
		if not frappe.db.exists("Unidade Organizacional", outra):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": outra}).insert(
				ignore_permissions=True
			)

		doc = frappe.get_doc("Unidade Organizacional", AREA_CONSELHO)
		doc.responde_para = outra

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)


class TestConselhoNoOrganograma(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_o_conselho_entra_como_raiz_propria(self):
		from gris.api.gestao_adultos.organograma import obter_organograma

		garantir_estrutura_do_conselho()
		self._criar_responsavel()

		arvore = obter_organograma()

		conselhos = [no for no in arvore["raizes"] if no.get("nome") == AREA_CONSELHO]
		self.assertEqual(len(conselhos), 1)
		self.assertGreaterEqual(conselhos[0]["membros"], 1)

	def test_filtrar_por_outra_area_esconde_o_conselho(self):
		from gris.api.gestao_adultos.organograma import obter_organograma

		garantir_estrutura_do_conselho()
		self._criar_responsavel("Filtrado")
		outra = f"{PREFIXO} Area"
		if not frappe.db.exists("Unidade Organizacional", outra):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": outra}).insert(
				ignore_permissions=True
			)

		arvore = obter_organograma(outra)

		self.assertEqual([no for no in arvore["raizes"] if no.get("nome") == AREA_CONSELHO], [])

	def test_detalhe_do_responsavel_e_somente_leitura(self):
		from gris.api.gestao_adultos.responsaveis import obter_detalhe_do_responsavel

		nome = self._criar_responsavel("Detalhe")

		detalhe = obter_detalhe_do_responsavel(nome)

		self.assertTrue(detalhe["somente_leitura"])
		self.assertFalse(detalhe["permite_ficha"])
		self.assertEqual(detalhe["funcao_principal"], FUNCAO_RESPONSAVEL_LEGAL)
		self.assertEqual(detalhe["areas"], [AREA_CONSELHO])

	def test_detalhe_de_quem_nao_existe_e_recusado(self):
		from gris.api.gestao_adultos.responsaveis import obter_detalhe_do_responsavel

		with self.assertRaises(frappe.DoesNotExistError):
			obter_detalhe_do_responsavel("nao-existe")

	def _criar_responsavel(self, sufixo="Pessoa"):
		doc = frappe.get_doc(
			{
				"doctype": "Responsavel",
				"nome_completo": f"{PREFIXO} {sufixo}",
				"cpf": frappe.generate_hash(length=11),
				"celular": "11999990000",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
