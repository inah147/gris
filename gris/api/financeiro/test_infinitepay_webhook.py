# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro.infinitepay_checkout import webhook_infinitepay
from gris.festas.doctype.compra_festa.test_compra_festa import _nova_festa


def _opcao(festa_name: str, nome: str, valor: float):
	return frappe.get_doc(
		{
			"doctype": "Opcao Convite Festa",
			"festa": festa_name,
			"nome_convite": nome,
			"valor": valor,
		}
	).insert(ignore_permissions=True)


def _convite(festa_name: str, opcao_name: str, quantidade: int = 2):
	return frappe.get_doc(
		{
			"doctype": "Convite Festa",
			"festa": festa_name,
			"nome_pagador": "Pagador",
			"telefone_pagador": "11988887777",
			"email_pagador": "pagador@example.com",
			"pagador_recebe_qr_codes": 1,
			"itens": [
				{
					"eh_convite": 1,
					"opcao_convite": opcao_name,
					"descricao": "Inteira",
					"quantidade": quantidade,
					"valor": 50,
				}
			],
			"convidados": [{"nome": "p", "email": "p@example.com"} for _ in range(quantidade)],
		}
	).insert(ignore_permissions=True)


def _fake_request(payload: dict):
	class _Req:
		host = "dev.gris"

		def get_data(self, *, as_text: bool = False):
			return json.dumps(payload)

	frappe.local.request = _Req()


class TestInfinitepayWebhook(FrappeTestCase):
	def setUp(self):
		link_patcher = patch(
			"gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay.CobrancaInfinitepay._criar_link_pagamento",
			lambda self: None,
		)
		link_patcher.start()
		self.addCleanup(link_patcher.stop)

		enqueue_patcher = patch("frappe.enqueue")
		self.mock_enqueue = enqueue_patcher.start()
		self.addCleanup(enqueue_patcher.stop)

		# Mock em memória do handle (sem tocar no DB, evitando poluir o singleton
		# Configuracao infinitepay com um valor de teste).
		real_get_single = frappe.db.get_single_value

		def _fake_get_single(doctype, fieldname, *args, **kwargs):
			if doctype == "Configuracao infinitepay" and fieldname == "handle":
				return "test-handle"
			return real_get_single(doctype, fieldname, *args, **kwargs)

		handle_patcher = patch("frappe.db.get_single_value", side_effect=_fake_get_single)
		handle_patcher.start()
		self.addCleanup(handle_patcher.stop)

		# Mock da chamada server-to-server para confirmar o pagamento.
		def _verificacao_ok(handle, order_nsu, transaction_nsu=None, slug=None):
			esperado = sum(
				int(item.quantidade or 0) * round(float(item.preco) * 100)
				for item in frappe.get_doc("Cobranca Infinitepay", order_nsu).itens
			)
			return {
				"success": True,
				"paid": True,
				"amount": esperado,
				"paid_amount": esperado,
				"installments": 1,
				"capture_method": "credit_card",
			}

		verify_patcher = patch(
			"gris.api.financeiro.infinitepay_checkout._verificar_pagamento",
			side_effect=_verificacao_ok,
		)
		self.mock_verify = verify_patcher.start()
		self.addCleanup(verify_patcher.stop)

	def test_webhook_marca_cobranca_e_propaga_para_convite(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name, "Inteira", 50)
		convite = _convite(festa.name, opcao.name, quantidade=3)
		cobranca_name = convite.cobranca_infinitepay

		_fake_request(
			{
				"order_nsu": cobranca_name,
				"invoice_slug": "abc",
				"amount": 15000,
				"paid_amount": 15000,
				"installments": 1,
				"capture_method": "credit_card",
				"transaction_nsu": "t1",
				"receipt_url": "https://example.com/r",
			}
		)
		resposta = webhook_infinitepay()
		self.assertTrue(resposta["ok"])

		cobranca = frappe.get_doc("Cobranca Infinitepay", cobranca_name)
		self.assertEqual(cobranca.status, "Pago")

		opcao.reload()
		self.assertEqual(int(opcao.quantidade_vendida), 3)

		self.mock_enqueue.assert_called()
		chamadas_convite = {
			(call.args[0] if call.args else call.kwargs.get("method")): call.kwargs
			for call in self.mock_enqueue.call_args_list
			if call.kwargs.get("convite_name") == convite.name
		}
		self.assertIn(
			"gris.festas.doctype.convite_festa.convite_festa.enviar_qr_codes",
			chamadas_convite,
		)
		self.assertIn(
			"gris.festas.doctype.convite_festa.convite_festa.enviar_whatsapp_confirmacao_convite",
			chamadas_convite,
		)

	def test_webhook_para_cobranca_inexistente_retorna_400(self):
		_fake_request({"order_nsu": "CF-INEXISTENTE"})
		resposta = webhook_infinitepay()
		self.assertFalse(resposta["ok"])
		self.assertEqual(resposta["error"]["code"], "ORDER_NOT_FOUND")

	def test_segunda_chamada_no_mesmo_status_nao_dispara_envio(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name, "Inteira", 50)
		convite = _convite(festa.name, opcao.name, quantidade=1)
		cobranca_name = convite.cobranca_infinitepay

		payload = {"order_nsu": cobranca_name, "amount": 5000, "paid_amount": 5000}
		_fake_request(payload)
		webhook_infinitepay()
		self.mock_enqueue.reset_mock()

		# Segunda chamada: cobrança já está Pago, status_mudou_para retorna False
		_fake_request(payload)
		webhook_infinitepay()
		self.mock_enqueue.assert_not_called()
