# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.gestao_de_projetos.doctype.avaliacao_de_projeto import (
	avaliacao_de_projeto as avaliacao_module,
)


class TestAvaliacaodeProjeto(FrappeTestCase):
	def test_get_all_reviewer_data_includes_phone_numbers(self):
		projeto_doc = frappe._dict(
			{
				"envolvidos": [
					frappe._dict(
						{
							"nome": "Equipe 1",
							"email": "equipe1@example.com",
							"telefone": "11933330000",
							"participa_avaliacao": 1,
						}
					),
					frappe._dict(
						{
							"nome": "Padrinho Associado",
							"email": "pad@example.com",
							"telefone": "11911110000",
							"participa_avaliacao": 1,
						}
					),
					frappe._dict(
						{
							"nome": "Nao Participa",
							"email": "nao.participa@example.com",
							"telefone": "11900000000",
							"participa_avaliacao": 0,
						}
					),
				],
			}
		)

		reviewers = avaliacao_module._get_all_reviewer_data(projeto_doc)
		reviewers_by_name = {item["nome"]: item for item in reviewers}

		self.assertEqual(reviewers_by_name["Equipe 1"]["telefone"], "11933330000")
		self.assertEqual(reviewers_by_name["Padrinho Associado"]["telefone"], "11911110000")
		self.assertNotIn("Nao Participa", reviewers_by_name)
