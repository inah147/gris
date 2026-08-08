# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today


class TestNovoAssociado(FrappeTestCase):
	def _criar_novo_associado(self, **kwargs) -> "frappe.model.document.Document":
		doc = frappe.get_doc(
			{
				"doctype": "Novo Associado",
				"nome_completo": "Jovem de Teste",
				"cpf": kwargs.pop("cpf", "111.111.111-11"),
				"data_de_nascimento": "2015-04-14",
				"status": "Acompanhamento",
				"tipo_de_registro": "Provisório",
				**kwargs,
			}
		)
		doc.insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "Novo Associado", doc.name, force=True)
		return doc

	def test_data_de_ativacao_fica_vazia_enquanto_registro_provisorio_nao_efetivado(self):
		doc = self._criar_novo_associado(cpf="222.222.222-22")

		self.assertFalse(doc.registro_provisorio_efetivado)
		self.assertIsNone(doc.data_registro_provisorio_efetivado)

	def test_data_de_ativacao_e_gravada_ao_efetivar_registro_provisorio(self):
		doc = self._criar_novo_associado(cpf="333.333.333-33")

		doc.registro_provisorio_efetivado = 1
		doc.save(ignore_permissions=True)

		self.assertEqual(str(doc.data_registro_provisorio_efetivado), today())

	def test_data_de_ativacao_e_preservada_em_salvamentos_seguintes(self):
		doc = self._criar_novo_associado(
			cpf="444.444.444-44",
			registro_provisorio_efetivado=1,
		)
		doc.db_set("data_registro_provisorio_efetivado", "2026-01-10")
		doc.reload()

		doc.nome_completo = "Jovem de Teste Renomeado"
		doc.save(ignore_permissions=True)

		self.assertEqual(str(doc.data_registro_provisorio_efetivado), "2026-01-10")

	def test_desmarcar_registro_provisorio_limpa_data_e_controle_de_aviso(self):
		doc = self._criar_novo_associado(
			cpf="555.555.555-55",
			registro_provisorio_efetivado=1,
		)
		doc.db_set("data_aviso_seguimento_provisorio", today())
		doc.reload()
		self.assertIsNotNone(doc.data_registro_provisorio_efetivado)

		doc.registro_provisorio_efetivado = 0
		doc.save(ignore_permissions=True)

		self.assertIsNone(doc.data_registro_provisorio_efetivado)
		self.assertIsNone(doc.data_aviso_seguimento_provisorio)
