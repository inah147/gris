# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# See license.txt

import json
import unittest

import frappe


class TestLogdeExecucaodeJob(unittest.TestCase):
	def test_get_eventos_e_metricas_desserializam_json(self):
		doc = frappe.get_doc(
			{
				"doctype": "Log de Execucao de Job",
				"job": "Teste",
				"metodo": "gris.testes.metodo",
				"status": "Sucesso",
				"inicio": frappe.utils.now_datetime(),
				"eventos": json.dumps([{"nivel": "INFO", "mensagem": "ok"}]),
				"metricas": json.dumps({"criados": 2}),
			}
		)

		self.assertEqual(doc.get_eventos(), [{"nivel": "INFO", "mensagem": "ok"}])
		self.assertEqual(doc.get_metricas(), {"criados": 2})

	def test_get_eventos_tolera_conteudo_invalido(self):
		doc = frappe.get_doc(
			{
				"doctype": "Log de Execucao de Job",
				"job": "Teste",
				"metodo": "gris.testes.metodo",
				"status": "Sucesso",
				"inicio": frappe.utils.now_datetime(),
				"eventos": "isto nao e json",
				"metricas": "[]",
			}
		)

		self.assertEqual(doc.get_eventos(), [])
		self.assertEqual(doc.get_metricas(), {})
