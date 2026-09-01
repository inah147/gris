# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestConfiguracoesdeRecepcao(FrappeTestCase):
	def tearDown(self):
		# FrappeTestCase faz rollback por classe, não por método.
		frappe.db.rollback()

	def _config(self):
		doc = frappe.get_single("Configuracoes de Recepcao")
		# O bloco do Drive tem regras próprias; estes testes olham só o modelo da declaração.
		doc.habilitar_documentos_drive = 0
		return doc

	def test_modelo_da_declaracao_aceita_link_do_google_docs(self):
		doc = self._config()
		doc.link_template_declaracao_idoneidade = (
			"https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit"
		)
		doc.save(ignore_permissions=True)

		self.assertTrue(doc.link_template_declaracao_idoneidade)

	def test_modelo_da_declaracao_rejeita_link_fora_do_google_docs(self):
		doc = self._config()
		doc.link_template_declaracao_idoneidade = (
			"https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrSt"
		)

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_modelo_da_declaracao_vazio_nao_e_validado(self):
		doc = self._config()
		doc.link_template_declaracao_idoneidade = "   "
		doc.save(ignore_permissions=True)

		self.assertEqual(doc.link_template_declaracao_idoneidade, "")

	def test_drive_habilitado_exige_pastas_e_drive(self):
		doc = frappe.get_single("Configuracoes de Recepcao")
		doc.habilitar_documentos_drive = 1
		doc.drive_compartilhado_acesso_restrito = ""

		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
