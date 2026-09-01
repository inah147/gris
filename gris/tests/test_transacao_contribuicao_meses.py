"""Testes do detalhamento por mês de uma transação de contribuição mensal.

Cobrem o cenário que motivou o campo: um único pagamento que quita mais de um
mês (ex.: R$ 70 do mês em atraso + R$ 60 do mês em dia). O detalhamento precisa
aparecer na apuração por mês, vincular o(s) Pagamento Contribuicao Mensal
correspondente(s) à transação e ser editável pela ferramenta de serviço usada
pelo MCP.
"""

import datetime
import hashlib

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro import contribuicoes as servico

CPF_BENEFICIARIO = "99000000201"


def _nome_por_cpf(cpf: str) -> str:
	return hashlib.md5(cpf.encode("utf-8")).hexdigest()


def _criar_associado(cpf: str) -> str:
	nome = _nome_por_cpf(cpf)
	if frappe.db.exists("Associado", nome):
		return nome
	doc = frappe.get_doc(
		{
			"doctype": "Associado",
			"cpf": cpf,
			"nome_completo": "Beneficiário Meses",
			"data_de_nascimento": "2015-01-01",
			"categoria": "Beneficiário",
			"status_no_grupo": "Ativo",
			"status_cobranca": "Ativo",
			"valor_contribuicao": 60.0,
			"inicio_do_pagamento": "2026-01-01",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _criar_transacao(associado: str, valor: float) -> "frappe.model.document.Document":
	doc = frappe.get_doc(
		{
			"doctype": "Transacao Extrato Geral",
			"id": f"test-meses-{frappe.generate_hash(length=10)}",
			"descricao": "Contribuição mensal em atraso + em dia",
			"debito_credito": "Crédito",
			"valor": valor,
			"data_transacao": datetime.date(2026, 3, 15),
			"categoria": "Contribuição Mensal",
			"beneficiario": associado,
			"metodo": "Pix",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestDefinirCompetenciasTransacao(FrappeTestCase):
	def setUp(self):
		self.associado = _criar_associado(CPF_BENEFICIARIO)
		self.transacao = _criar_transacao(self.associado, 130.0)

	def test_recusa_soma_que_nao_bate_com_o_valor(self):
		with self.assertRaises(frappe.ValidationError):
			servico.definir_competencias_transacao(
				self.transacao.name,
				[
					{"mes": "2026-01", "valor": 70.0, "em_atraso": True},
					{"mes": "2026-02", "valor": 50.0, "em_atraso": False},
				],
			)

	def test_recusa_mes_duplicado(self):
		with self.assertRaises(frappe.ValidationError):
			servico.definir_competencias_transacao(
				self.transacao.name,
				[
					{"mes": "2026-01", "valor": 70.0, "em_atraso": True},
					{"mes": "2026-01", "valor": 60.0, "em_atraso": False},
				],
			)

	def test_recusa_transacao_sem_beneficiario(self):
		outra = frappe.get_doc(
			{
				"doctype": "Transacao Extrato Geral",
				"id": f"test-meses-{frappe.generate_hash(length=10)}",
				"valor": 60,
				"debito_credito": "Crédito",
				"categoria": "Contribuição Mensal",
			}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			servico.definir_competencias_transacao(outra.name, [{"mes": "2026-01", "valor": 60.0}])

	def test_grava_os_dois_meses_e_vincula_pagamentos(self):
		resultado = servico.definir_competencias_transacao(
			self.transacao.name,
			[
				{"mes": "2026-01", "valor": 70.0, "em_atraso": True},
				{"mes": "2026-02", "valor": 60.0, "em_atraso": False},
			],
		)

		self.assertEqual(len(resultado["competencias"]), 2)
		self.assertEqual(resultado["competencias"][0]["ym"], "2026-01")
		self.assertEqual(resultado["competencias"][0]["valor"], 70.0)
		self.assertTrue(resultado["competencias"][0]["em_atraso"])

		pagamento_jan = frappe.get_all(
			"Pagamento Contribuicao Mensal",
			filters={"associado": self.associado, "mes_de_referencia": "2026-01-01"},
			fields=["status", "valor", "atrasou", "transacao_extrato"],
		)[0]
		self.assertEqual(pagamento_jan.status, "Pago")
		self.assertEqual(pagamento_jan.valor, 70.0)
		self.assertEqual(pagamento_jan.atrasou, 1)
		self.assertEqual(pagamento_jan.transacao_extrato, self.transacao.name)

		pagamento_fev = frappe.get_all(
			"Pagamento Contribuicao Mensal",
			filters={"associado": self.associado, "mes_de_referencia": "2026-02-01"},
			fields=["status", "valor", "atrasou", "transacao_extrato"],
		)[0]
		self.assertEqual(pagamento_fev.status, "Pago")
		self.assertEqual(pagamento_fev.valor, 60.0)
		self.assertEqual(pagamento_fev.atrasou, 0)
		self.assertEqual(pagamento_fev.transacao_extrato, self.transacao.name)

	def test_apuracao_reparte_o_valor_pelos_meses_declarados(self):
		servico.definir_competencias_transacao(
			self.transacao.name,
			[
				{"mes": "2026-01", "valor": 70.0, "em_atraso": True},
				{"mes": "2026-02", "valor": 60.0, "em_atraso": False},
			],
		)

		recebimentos = servico.get_recebimentos_por_associado(
			datetime.date(2026, 1, 1), datetime.date(2026, 3, 1), [self.associado]
		)
		por_mes = recebimentos[self.associado]
		self.assertEqual(por_mes["2026-01"]["valor"], 70.0)
		self.assertEqual(por_mes["2026-02"]["valor"], 60.0)

	def test_lista_vazia_remove_o_detalhamento(self):
		servico.definir_competencias_transacao(
			self.transacao.name, [{"mes": "2026-01", "valor": 70.0}, {"mes": "2026-02", "valor": 60.0}]
		)
		resultado = servico.definir_competencias_transacao(self.transacao.name, [])
		self.assertEqual(resultado["competencias"], [])
