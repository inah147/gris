# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Testes das funções internas do Associado (a grade que alimenta o organograma)."""

import frappe
from frappe.tests.utils import FrappeTestCase

PREFIXO = "ZZ Teste Funcoes"


class TestFuncoesInternasDoAssociado(FrappeTestCase):
	def setUp(self):
		self.area = self._criar_area()
		self.funcao_a = self._criar_funcao("A")
		self.funcao_b = self._criar_funcao("B")
		self.associado = self._criar_associado()

	def tearDown(self):
		# FrappeTestCase faz rollback por classe; sem isto o próximo teste
		# esbarra em DuplicateEntryError nos registros criados no setUp.
		frappe.db.rollback()

	def test_uma_funcao_principal_e_aceita(self):
		doc = frappe.get_doc("Associado", self.associado)
		doc.append("funcoes_internas", {"funcao": self.funcao_a, "principal": 1})
		doc.append("funcoes_internas", {"funcao": self.funcao_b, "principal": 0})
		doc.save(ignore_permissions=True)

		self.assertEqual(len(doc.funcoes_internas), 2)

	def test_duas_principais_sao_barradas(self):
		doc = frappe.get_doc("Associado", self.associado)
		doc.append("funcoes_internas", {"funcao": self.funcao_a, "principal": 1})
		doc.append("funcoes_internas", {"funcao": self.funcao_b, "principal": 1})

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_data_fim_antes_do_inicio_e_barrada(self):
		doc = frappe.get_doc("Associado", self.associado)
		doc.append(
			"funcoes_internas",
			{"funcao": self.funcao_a, "data_inicio": "2024-01-01", "data_fim": "2023-01-01"},
		)

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_area_vem_da_funcao(self):
		"""`fetch_from` preenche a área para o organograma não precisar de join."""
		doc = frappe.get_doc("Associado", self.associado)
		doc.append("funcoes_internas", {"funcao": self.funcao_a})
		doc.save(ignore_permissions=True)
		doc.reload()

		self.assertEqual(doc.funcoes_internas[0].area, self.area)

	def _criar_area(self):
		nome = f"{PREFIXO} Area"
		if not frappe.db.exists("Unidade Organizacional", nome):
			frappe.get_doc({"doctype": "Unidade Organizacional", "area": nome}).insert(
				ignore_permissions=True
			)
		return nome

	def _criar_funcao(self, sufixo):
		titulo = f"{PREFIXO} Funcao {sufixo}"
		if not frappe.db.exists("Funcao Voluntario", titulo):
			frappe.get_doc(
				{
					"doctype": "Funcao Voluntario",
					"titulo": titulo,
					"categoria": "Dirigente",
					"area": self.area,
					"responsabilidades": [{"responsabilidade": f"Responsabilidade {sufixo}"}],
				}
			).insert(ignore_permissions=True)
		return titulo

	def _criar_associado(self):
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"nome_completo": f"{PREFIXO} Pessoa",
				"cpf": frappe.generate_hash(length=32),
				"data_de_nascimento": "1990-01-01",
				"categoria": "Dirigente",
				"status_no_grupo": "Ativo",
				"area": self.area,
				"historico_no_grupo": [{"data_de_ingresso": "2020-01-01"}],
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
