# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.festas.doctype.compra_festa.test_compra_festa import _nova_festa
from gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay import (
	sincronizar_pagamento,
)


def _opcao(festa_name: str):
	return frappe.get_doc(
		{
			"doctype": "Opcao Convite Festa",
			"festa": festa_name,
			"nome_convite": "Inteira",
			"valor": 50,
		}
	).insert(ignore_permissions=True)


def _convite(festa_name: str, opcao_name: str):
	return frappe.get_doc(
		{
			"doctype": "Convite Festa",
			"festa": festa_name,
			"nome_pagador": "P",
			"telefone_pagador": "11988887777",
			"email_pagador": "p@example.com",
			"pagador_recebe_qr_codes": 1,
			"itens": [
				{
					"eh_convite": 1,
					"opcao_convite": opcao_name,
					"descricao": "Inteira",
					"quantidade": 1,
					"valor": 50,
				}
			],
		}
	).insert(ignore_permissions=True)


class TestSincronizarPagamento(FrappeTestCase):
	def setUp(self):
		link_patcher = patch(
			"gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay.CobrancaInfinitepay._criar_link_pagamento",
			lambda self: None,
		)
		link_patcher.start()
		self.addCleanup(link_patcher.stop)

		def _fake_get_single(doctype, fieldname, *args, **kwargs):
			if doctype == "Configuracao infinitepay" and fieldname == "handle":
				return "test-handle"
			return None

		handle_patcher = patch(
			"frappe.db.get_single_value", side_effect=_fake_get_single
		)
		handle_patcher.start()
		self.addCleanup(handle_patcher.stop)

		enqueue_patcher = patch("frappe.enqueue")
		enqueue_patcher.start()
		self.addCleanup(enqueue_patcher.stop)

	def test_sincronizar_marca_como_pago_quando_aprovado(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(festa.name, opcao.name)

		with patch(
			"gris.api.financeiro.infinitepay_checkout._verificar_pagamento",
			return_value={
				"success": True,
				"paid": True,
				"amount": 5000,
				"paid_amount": 5000,
				"installments": 1,
				"capture_method": "credit_card",
			},
		):
			resultado = sincronizar_pagamento(convite.cobranca_infinitepay)

		self.assertTrue(resultado["ok"])
		cobranca = frappe.get_doc("Cobranca Infinitepay", convite.cobranca_infinitepay)
		self.assertEqual(cobranca.status, "Pago")
		self.assertEqual(cobranca.paid_amount, 5000)

	def test_sincronizar_retorna_nao_pago_quando_infinitepay_nega(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(festa.name, opcao.name)

		with patch(
			"gris.api.financeiro.infinitepay_checkout._verificar_pagamento",
			return_value={"success": True, "paid": False, "paid_amount": 0},
		):
			resultado = sincronizar_pagamento(convite.cobranca_infinitepay)

		self.assertFalse(resultado["ok"])
		cobranca = frappe.get_doc("Cobranca Infinitepay", convite.cobranca_infinitepay)
		self.assertEqual(cobranca.status, "Pendente")

	def test_sincronizar_bloqueia_quando_valor_insuficiente(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(festa.name, opcao.name)

		with patch(
			"gris.api.financeiro.infinitepay_checkout._verificar_pagamento",
			return_value={"success": True, "paid": True, "paid_amount": 1000},
		):
			self.assertRaises(
				frappe.ValidationError,
				sincronizar_pagamento,
				convite.cobranca_infinitepay,
			)
