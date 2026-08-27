# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.festas.doctype.compra_festa.test_compra_festa import _nova_festa


class TestOpcaoConviteFesta(FrappeTestCase):
	def test_nome_convite_unico_por_festa(self):
		festa = _nova_festa()
		frappe.get_doc(
			{
				"doctype": "Opcao Convite Festa",
				"festa": festa.name,
				"nome_convite": "Inteira",
				"valor": 50,
			}
		).insert(ignore_permissions=True)

		duplicada = frappe.get_doc(
			{
				"doctype": "Opcao Convite Festa",
				"festa": festa.name,
				"nome_convite": "Inteira",
				"valor": 80,
			}
		)
		self.assertRaises(frappe.ValidationError, duplicada.insert, ignore_permissions=True)

	def test_ativo_default_true(self):
		festa = _nova_festa()
		opcao = frappe.get_doc(
			{
				"doctype": "Opcao Convite Festa",
				"festa": festa.name,
				"nome_convite": "VIP",
				"valor": 120,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(int(opcao.ativo), 1)
		self.assertEqual(int(opcao.quantidade_vendida or 0), 0)
