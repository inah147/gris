# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from gris.festas.doctype.compra_festa.test_compra_festa import _nova_festa


def _opcao(festa_name: str, nome: str = "Inteira", valor: float = 50) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Opcao Convite Festa",
			"festa": festa_name,
			"nome_convite": nome,
			"valor": valor,
		}
	).insert(ignore_permissions=True)
	return doc.name


def _convite_payload(festa_name: str, opcao_name: str, **overrides):
	payload = {
		"doctype": "Convite Festa",
		"festa": festa_name,
		"nome_pagador": "João Pagador",
		"telefone_pagador": "11988887777",
		"email_pagador": "joao@example.com",
		"pagador_recebe_qr_codes": 1,
		"itens": [
			{
				"eh_convite": 1,
				"opcao_convite": opcao_name,
				"descricao": "Inteira",
				"quantidade": 2,
				"valor": 50,
			}
		],
		"convidados": [
			{"nome": "ph", "email": "ph@example.com"},
			{"nome": "ph", "email": "ph@example.com"},
		],
	}
	payload.update(overrides)
	return payload


class TestConviteFesta(FrappeTestCase):
	def setUp(self):
		patcher = patch(
			"gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay.CobrancaInfinitepay._criar_link_pagamento",
			lambda self: None,
		)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_valor_total_calculado(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name, valor=75)
		payload = _convite_payload(festa.name, opcao)
		payload["itens"][0]["valor"] = 75
		doc = frappe.get_doc(payload).insert(ignore_permissions=True)
		self.assertEqual(float(doc.valor_total), 150.0)

	def test_pagador_recebe_qr_codes_sobrescreve_convidados(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		doc = frappe.get_doc(
			_convite_payload(
				festa.name,
				opcao,
				convidados=[
					{"nome": "X", "email": "x@example.com"},
					{"nome": "Y", "email": "y@example.com"},
				],
			)
		).insert(ignore_permissions=True)
		for convidado in doc.convidados:
			self.assertEqual(convidado.nome, "João Pagador")
			self.assertEqual(convidado.email, "joao@example.com")
			self.assertEqual(convidado.telefone, "11988887777")

	def test_individual_exige_dados_dos_convidados(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		doc = frappe.get_doc(
			_convite_payload(
				festa.name,
				opcao,
				pagador_recebe_qr_codes=0,
				convidados=[
					{"nome": "Alice", "email": "alice@example.com"},
					{"nome": "", "email": "bob@example.com"},
				],
			)
		)
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_convidados_devem_bater_com_quantidade_quando_individual(self):
		"""Sem pagador_recebe_qr_codes, a contagem precisa bater manualmente."""
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		payload = _convite_payload(festa.name, opcao, pagador_recebe_qr_codes=0)
		payload["convidados"] = [{"nome": "ph", "email": "ph@example.com"}]
		doc = frappe.get_doc(payload)
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_pagador_recebe_qr_codes_autogera_lista(self):
		"""Quando o pagador recebe todos, o servidor cria as linhas faltantes."""
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		payload = _convite_payload(festa.name, opcao)
		payload["convidados"] = []  # usuário não preencheu nada
		doc = frappe.get_doc(payload).insert(ignore_permissions=True)
		self.assertEqual(len(doc.convidados), 2)
		for convidado in doc.convidados:
			self.assertEqual(convidado.nome, "João Pagador")
			self.assertEqual(convidado.email, "joao@example.com")
			self.assertEqual(convidado.telefone, "11988887777")

	def test_pagador_recebe_qr_codes_ajusta_quando_quantidade_muda(self):
		"""Mudar a quantidade do item recria a lista de convidados."""
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		doc = frappe.get_doc(_convite_payload(festa.name, opcao)).insert(
			ignore_permissions=True
		)
		self.assertEqual(len(doc.convidados), 2)

		doc.reload()
		doc.itens[0].quantidade = 4
		doc.save(ignore_permissions=True)
		self.assertEqual(len(doc.convidados), 4)
		for convidado in doc.convidados:
			self.assertEqual(convidado.nome, "João Pagador")

	def test_item_doacao_bloqueado_quando_festa_nao_aceita(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		payload = _convite_payload(festa.name, opcao)
		payload["itens"].append(
			{
				"eh_convite": 0,
				"descricao": "Doação",
				"quantidade": 1,
				"valor": 20,
			}
		)
		doc = frappe.get_doc(payload)
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_item_doacao_aceito_quando_festa_aceita(self):
		festa = _nova_festa()
		festa.aceitar_doacoes = 1
		festa.save(ignore_permissions=True)
		opcao = _opcao(festa.name)
		payload = _convite_payload(festa.name, opcao)
		payload["itens"].append(
			{
				"eh_convite": 0,
				"descricao": "Doação",
				"quantidade": 1,
				"valor": 20,
			}
		)
		doc = frappe.get_doc(payload).insert(ignore_permissions=True)
		self.assertEqual(float(doc.valor_total), 100 + 20)

	def test_periodo_de_vendas_encerrado(self):
		festa = _nova_festa()
		festa.data = add_days(today(), 1)
		festa.data_limite_vendas = add_days(today(), -1)
		festa.save(ignore_permissions=True)
		opcao = _opcao(festa.name)
		doc = frappe.get_doc(_convite_payload(festa.name, opcao))
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_opcao_inativa_bloqueada(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		frappe.db.set_value("Opcao Convite Festa", opcao, "ativo", 0)
		doc = frappe.get_doc(_convite_payload(festa.name, opcao))
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_opcao_de_outra_festa_bloqueada(self):
		festa_a = _nova_festa()
		festa_b = _nova_festa()
		opcao_a = _opcao(festa_a.name)
		doc = frappe.get_doc(_convite_payload(festa_b.name, opcao_a))
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_after_insert_cria_cobranca_com_itens(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		doc = frappe.get_doc(_convite_payload(festa.name, opcao)).insert(
			ignore_permissions=True
		)
		self.assertTrue(doc.cobranca_infinitepay)
		cobranca = frappe.get_doc("Cobranca Infinitepay", doc.cobranca_infinitepay)
		self.assertEqual(len(cobranca.itens), 1)
		self.assertEqual(int(cobranca.itens[0].quantidade), 2)
		self.assertEqual(float(cobranca.itens[0].preco), 50.0)
		self.assertEqual(cobranca.customer_email, "joao@example.com")

	def test_virtual_field_status_pagamento_le_da_cobranca(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		doc = frappe.get_doc(_convite_payload(festa.name, opcao)).insert(
			ignore_permissions=True
		)
		self.assertEqual(doc.status_pagamento, "Pendente")
		frappe.db.set_value(
			"Cobranca Infinitepay", doc.cobranca_infinitepay, "status", "Pago"
		)
		doc.reload()
		self.assertEqual(doc.status_pagamento, "Pago")

	def test_email_invalido_bloqueado(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		payload = _convite_payload(festa.name, opcao)
		payload["email_pagador"] = "nao-eh-email"
		doc = frappe.get_doc(payload)
		self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)

	def test_payload_qr_code_gerado_para_cada_convidado(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		doc = frappe.get_doc(_convite_payload(festa.name, opcao)).insert(
			ignore_permissions=True
		)
		payloads = {c.qr_code_payload for c in doc.convidados}
		self.assertEqual(len(payloads), 2)
		self.assertTrue(all(p for p in payloads))
