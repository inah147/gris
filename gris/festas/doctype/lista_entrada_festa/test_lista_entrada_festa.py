# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# See license.txt

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.festas.doctype.lista_entrada_festa.lista_entrada_festa import (
	STATUS_ENTROU,
	STATUS_NAO_ENTROU,
	ListaEntradaFesta,
)


class TestListaEntradaFesta(FrappeTestCase):
	def setUp(self):
		# Festa mínima para satisfazer link reqd.
		if not frappe.db.exists("Festa", "Festa Teste Portaria"):
			festa = frappe.get_doc(
				{
					"doctype": "Festa",
					"nome_festa": "Festa Teste Portaria",
					"data": "2030-01-01",
					"data_limite_vendas": "2029-12-31",
					"status": "Em andamento",
				}
			)
			festa.insert(ignore_permissions=True)

	def _criar_entrada(self, codigo: str) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Lista Entrada Festa",
				"festa": "Festa Teste Portaria",
				"convite": "CF-2026-00001",  # dummy; FK validado em produção
				"convidado_row": f"row-{codigo}",
				"codigo_convite": codigo,
				"nome_convidado": "Convidado Teste",
				"email": "teste@example.com",
				"telefone": "11999990000",
				"status": STATUS_NAO_ENTROU,
			}
		)
		# Insere sem validar Link de convite (teste isolado).
		doc.flags.ignore_links = True
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_sanitiza_email_e_telefone(self):
		name = self._criar_entrada("teste-sanitize")
		doc = frappe.get_doc("Lista Entrada Festa", name)
		self.assertEqual(doc.email, "teste@example.com")
		self.assertEqual(doc.telefone, "11999990000")

	def test_marcar_entrada_atomico(self):
		name = self._criar_entrada("teste-atomico")
		resultado = ListaEntradaFesta.marcar_entrada(name, user="Administrator")
		self.assertTrue(resultado["ok"])
		self.assertFalse(resultado["ja_entrou_antes"])

		# Segunda chamada deve retornar ja_entrou_antes=True.
		resultado2 = ListaEntradaFesta.marcar_entrada(name, user="Administrator")
		self.assertTrue(resultado2["ok"])
		self.assertTrue(resultado2["ja_entrou_antes"])

		# Confirma persistência.
		doc = frappe.get_doc("Lista Entrada Festa", name)
		self.assertEqual(doc.status, STATUS_ENTROU)
		self.assertIsNotNone(doc.hora_entrada)
