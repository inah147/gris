import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from gris.api.festas import (
	criar_contratacao,
	criar_contratacao_sem_previsao,
	excluir_contratacao,
	salvar_contratacao_sem_previsao,
	salvar_realizado_contratacao,
)


def _nova_festa():
	festa = frappe.get_doc(
		{
			"doctype": "Festa",
			"nome_festa": f"Festa Teste {frappe.generate_hash(length=8)}",
			"data": today(),
			"data_limite_vendas": today(),
			"status": "Em andamento",
		}
	).insert(ignore_permissions=True)
	portaria = frappe.get_doc("Area da Festa", f"{festa.name} - Portaria")
	portaria.nome_coord = "Coord Portaria"
	portaria.email_coord = "portaria@example.com"
	portaria.telefone_coord = "+5511999999999"
	portaria.save(ignore_permissions=True)
	return festa


class TestContratacaoFesta(FrappeTestCase):
	def test_sem_previsao_pode_ser_criada_editada_e_removida(self):
		festa = _nova_festa()
		r = criar_contratacao_sem_previsao(
			festa.name, json.dumps({"nome_item": "Som", "valor_total_realizado": 300, "cancelado": 1})
		)
		contr = r["contratacao"]
		self.assertFalse(contr["previsto"])
		self.assertTrue(contr["cancelado"])

		r2 = salvar_contratacao_sem_previsao(
			contr["name"],
			json.dumps({"nome_item": "Som e luz", "valor_total_realizado": 300, "cancelado": 0}),
		)
		self.assertEqual(r2["contratacao"]["nome_item"], "Som e luz")
		self.assertFalse(r2["contratacao"]["cancelado"])

		excluir_contratacao(contr["name"], festa.name)
		self.assertFalse(frappe.db.exists("Contratacao Festa", contr["name"]))

	def test_salvar_sem_previsao_recusa_item_previsto(self):
		festa = _nova_festa()
		contr = criar_contratacao(
			festa.name,
			json.dumps(
				{
					"nome_item": "Segurança",
					"cotacoes": [{"fornecedor": "A", "valor": 500, "escolhida": 1}],
				}
			),
		)["contratacao"]
		self.assertRaises(
			frappe.ValidationError,
			salvar_contratacao_sem_previsao,
			contr["name"],
			json.dumps({"nome_item": "Outro", "valor_total_realizado": 10}),
		)

	def test_realizado_grava_cancelado(self):
		festa = _nova_festa()
		contr = criar_contratacao(
			festa.name,
			json.dumps(
				{
					"nome_item": "Banheiros",
					"cotacoes": [{"fornecedor": "A", "valor": 400, "escolhida": 1}],
				}
			),
		)["contratacao"]
		salvar_realizado_contratacao(
			contr["name"], json.dumps({"valor_total_realizado": 400, "cancelado": 1})
		)
		self.assertEqual(frappe.db.get_value("Contratacao Festa", contr["name"], "cancelado"), 1)
