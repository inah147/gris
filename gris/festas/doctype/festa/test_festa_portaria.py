# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today


class TestFestaPortaria(FrappeTestCase):
	def _criar_festa(self):
		return frappe.get_doc(
			{
				"doctype": "Festa",
				"nome_festa": f"Festa Portaria {frappe.generate_hash(length=8)}",
				"data": add_days(today(), 30),
				"data_limite_vendas": add_days(today(), 20),
				"status": "Em andamento",
			}
		).insert(ignore_permissions=True)

	def test_portaria_auto_criada(self):
		festa = self._criar_festa()
		self.assertTrue(frappe.db.exists("Area da Festa", f"{festa.name} - Portaria"))

	def test_save_festa_sem_coordenador_portaria_falha(self):
		festa = self._criar_festa()
		festa.expectativa_publico_max = 99
		self.assertRaises(frappe.ValidationError, festa.save, ignore_permissions=True)

	def test_save_festa_apos_preencher_portaria_funciona(self):
		festa = self._criar_festa()
		portaria = frappe.get_doc("Area da Festa", f"{festa.name} - Portaria")
		portaria.nome_coord = "Coord"
		portaria.email_coord = "coord@example.com"
		portaria.telefone_coord = "+5511988887777"
		portaria.save(ignore_permissions=True)

		festa.expectativa_publico_max = 99
		festa.save(ignore_permissions=True)
		self.assertEqual(int(festa.expectativa_publico_max), 99)

	def test_deletar_portaria_eh_bloqueado(self):
		festa = self._criar_festa()
		portaria = frappe.get_doc("Area da Festa", f"{festa.name} - Portaria")
		self.assertRaises(frappe.ValidationError, portaria.delete, ignore_permissions=True)

	def test_deletar_festa_remove_portaria_automaticamente(self):
		festa = self._criar_festa()
		self.assertTrue(frappe.db.exists("Area da Festa", f"{festa.name} - Portaria"))

		frappe.delete_doc("Festa", festa.name, ignore_permissions=True)

		self.assertFalse(frappe.db.exists("Festa", festa.name))
		self.assertFalse(frappe.db.exists("Area da Festa", f"{festa.name} - Portaria"))

	def test_portaria_sem_coordenador_falha_no_save_direto(self):
		festa = self._criar_festa()
		portaria = frappe.get_doc("Area da Festa", f"{festa.name} - Portaria")
		portaria.descricao = "ajuste"
		self.assertRaises(frappe.ValidationError, portaria.save, ignore_permissions=True)
