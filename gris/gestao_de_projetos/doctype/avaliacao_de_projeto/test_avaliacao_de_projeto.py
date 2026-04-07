# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.gestao_de_projetos.doctype.avaliacao_de_projeto import (
	avaliacao_de_projeto as avaliacao_module,
)


class TestAvaliacaodeProjeto(FrappeTestCase):
	def test_get_all_reviewer_data_includes_phone_numbers(self):
		original_get_value = avaliacao_module.frappe.db.get_value

		def fake_get_value(doctype, name, fields=None, as_dict=False):
			if doctype == "Associado" and name == "PAD-1":
				return frappe._dict(
					{
						"nome_completo": "Padrinho Associado",
						"id_escoteiros": "pad@example.com",
						"email": "pad-alt@example.com",
						"telefone": "11911110000",
					}
				)
			if doctype == "Associado" and name == "ASSOC-1":
				return frappe._dict(
					{
						"nome_completo": "Outro Envolvido",
						"id_escoteiros": "outro@example.com",
						"email": "outro-alt@example.com",
						"telefone": "11922220000",
					}
				)
			return original_get_value(doctype, name, fields=fields, as_dict=as_dict)

		avaliacao_module.frappe.db.get_value = fake_get_value

		try:
			projeto_doc = frappe._dict(
				{
					"equipe_de_interesse": [
						frappe._dict(
							{
								"nome": "Equipe 1",
								"email": "equipe1@example.com",
								"telefone": "11933330000",
							}
						)
					],
					"tipo_padrinho_ou_orientador": "Associado",
					"padrinho_associado": "PAD-1",
					"padrinho_responsavel": "",
					"outros_envolvidos": [
						frappe._dict(
							{
								"associado": "ASSOC-1",
								"telefone": "11999999999",
							}
						)
					],
				}
			)

			reviewers = avaliacao_module._get_all_reviewer_data(projeto_doc)
			reviewers_by_name = {item["nome"]: item for item in reviewers}

			self.assertEqual(reviewers_by_name["Equipe 1"]["telefone"], "11933330000")
			self.assertEqual(reviewers_by_name["Padrinho Associado"]["telefone"], "11911110000")
			self.assertEqual(reviewers_by_name["Outro Envolvido"]["telefone"], "11922220000")
		finally:
			avaliacao_module.frappe.db.get_value = original_get_value
