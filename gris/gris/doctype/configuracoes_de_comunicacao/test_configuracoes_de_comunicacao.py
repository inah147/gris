# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestConfiguracoesdeComunicacao(FrappeTestCase):
	def tearDown(self):
		# FrappeTestCase faz rollback por classe, não por método.
		frappe.db.rollback()

	def test_link_de_google_docs_valido_e_aceito(self):
		doc = frappe.get_single("Configuracoes de Comunicacao")
		doc.link_papel_timbrado = (
			"https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit"
		)
		doc.save(ignore_permissions=True)

		self.assertTrue(doc.link_papel_timbrado)

	def test_link_fora_do_google_docs_e_rejeitado(self):
		doc = frappe.get_single("Configuracoes de Comunicacao")
		doc.link_papel_timbrado = "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrSt"

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_campo_vazio_nao_e_validado(self):
		doc = frappe.get_single("Configuracoes de Comunicacao")
		doc.link_papel_timbrado = "   "
		doc.save(ignore_permissions=True)

		self.assertEqual(doc.link_papel_timbrado, "")
