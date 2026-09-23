# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes das travas de hierarquia da Unidade Organizacional."""

import frappe
from frappe.tests.utils import FrappeTestCase

PREFIXO = "ZZ Teste UO"


class TestUnidadeOrganizacionalHierarquia(FrappeTestCase):
	def tearDown(self):
		# FrappeTestCase faz rollback por classe; sem isto o próximo teste
		# esbarra em DuplicateEntryError nas áreas criadas aqui.
		frappe.db.rollback()

	def _criar(self, sufixo, mae=None):
		doc = frappe.get_doc(
			{
				"doctype": "Unidade Organizacional",
				"area": f"{PREFIXO} {sufixo}",
				"responde_para": mae,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_area_nao_pode_responder_para_ela_mesma(self):
		area = self._criar("Auto")
		area.responde_para = area.name

		with self.assertRaises(frappe.ValidationError):
			area.save(ignore_permissions=True)

	def test_ciclo_indireto_e_barrado(self):
		topo = self._criar("Topo")
		meio = self._criar("Meio", mae=topo.name)
		folha = self._criar("Folha", mae=meio.name)

		topo.responde_para = folha.name
		with self.assertRaises(frappe.ValidationError):
			topo.save(ignore_permissions=True)

	def test_hierarquia_valida_e_aceita(self):
		topo = self._criar("Valida Topo")
		filha = self._criar("Valida Filha", mae=topo.name)

		self.assertEqual(filha.responde_para, topo.name)

	def test_beneficiario_nao_pode_ser_responsavel(self):
		associado = self._criar_associado(categoria="Beneficiário")
		area = self._criar("Com Beneficiario")
		area.responsavel = associado

		with self.assertRaises(frappe.ValidationError):
			area.save(ignore_permissions=True)

	def test_adulto_ativo_pode_ser_responsavel(self):
		associado = self._criar_associado(categoria="Dirigente")
		area = self._criar("Com Dirigente")
		area.responsavel = associado
		area.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("Unidade Organizacional", area.name, "responsavel"), associado)

	def _criar_associado(self, categoria):
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": f"{PREFIXO} {categoria}",
				"cpf": frappe.generate_hash(length=32),
				"data_de_nascimento": "1990-01-01",
				"categoria": categoria,
				"status_no_grupo": "Ativo",
				"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
