# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.festas.doctype.compra_festa.test_compra_festa import _nova_festa
from gris.festas.doctype.convite_festa.convite_festa import enviar_qr_codes


def _opcao(festa_name: str):
	return frappe.get_doc(
		{
			"doctype": "Opcao Convite Festa",
			"festa": festa_name,
			"nome_convite": "Inteira",
			"valor": 50,
		}
	).insert(ignore_permissions=True)


def _convite(festa_name: str, opcao_name: str, *, pagador_recebe: bool, convidados):
	return frappe.get_doc(
		{
			"doctype": "Convite Festa",
			"festa": festa_name,
			"nome_pagador": "Pagador",
			"telefone_pagador": "11988887777",
			"email_pagador": "pagador@example.com",
			"pagador_recebe_qr_codes": 1 if pagador_recebe else 0,
			"itens": [
				{
					"eh_convite": 1,
					"opcao_convite": opcao_name,
					"descricao": "Inteira",
					"quantidade": len(convidados),
					"valor": 50,
				}
			],
			"convidados": convidados,
		}
	).insert(ignore_permissions=True)


def _marcar_cobranca_paga(cobranca_name: str) -> None:
	# bypass on_update para não disparar enqueue real durante setup
	frappe.db.set_value("Cobranca Infinitepay", cobranca_name, "status", "Pago")


class TestConviteEnvio(FrappeTestCase):
	def setUp(self):
		link_patcher = patch(
			"gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay.CobrancaInfinitepay._criar_link_pagamento",
			lambda self: None,
		)
		link_patcher.start()
		self.addCleanup(link_patcher.stop)

		gerar_patcher = patch(
			"gris.festas.utils.convite_qr.gerar_pdf_convite",
			return_value=b"%PDF-FAKE",
		)
		gerar_patcher.start()
		self.addCleanup(gerar_patcher.stop)

		sendmail_patcher = patch("frappe.sendmail")
		self.mock_sendmail = sendmail_patcher.start()
		self.addCleanup(sendmail_patcher.stop)

		whatsapp_patcher = patch("gris.utils.whatsapp.enviar_texto")
		self.mock_whatsapp = whatsapp_patcher.start()
		self.addCleanup(whatsapp_patcher.stop)

	def test_pagador_recebe_todos_um_email_com_n_anexos(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(
			festa.name,
			opcao.name,
			pagador_recebe=True,
			convidados=[
				{"nome": "X", "email": "x@example.com"},
				{"nome": "Y", "email": "y@example.com"},
				{"nome": "Z", "email": "z@example.com"},
			],
		)
		_marcar_cobranca_paga(convite.cobranca_infinitepay)

		enviar_qr_codes(convite.name)

		self.assertEqual(self.mock_sendmail.call_count, 1)
		kwargs = self.mock_sendmail.call_args.kwargs
		self.assertEqual(kwargs["recipients"], [convite.email_pagador])
		self.assertEqual(len(kwargs["attachments"]), 3)

		convite.reload()
		for c in convite.convidados:
			self.assertEqual(c.status_envio, "Enviado")

	def test_individual_n_emails(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(
			festa.name,
			opcao.name,
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice", "email": "alice@example.com"},
				{"nome": "Bob", "email": "bob@example.com"},
			],
		)
		_marcar_cobranca_paga(convite.cobranca_infinitepay)

		enviar_qr_codes(convite.name)

		self.assertEqual(self.mock_sendmail.call_count, 2)
		convite.reload()
		for c in convite.convidados:
			self.assertEqual(c.status_envio, "Enviado")

	def test_erro_em_um_convidado_notifica_portaria(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(
			festa.name,
			opcao.name,
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice", "email": "alice@example.com"},
				{"nome": "Bob", "email": "bob@example.com"},
			],
		)
		_marcar_cobranca_paga(convite.cobranca_infinitepay)

		chamadas = {"n": 0}

		def sendmail_side_effect(*args, **kwargs):
			chamadas["n"] += 1
			if chamadas["n"] == 1:
				raise Exception("smtp temporarily down")

		self.mock_sendmail.side_effect = sendmail_side_effect

		enviar_qr_codes(convite.name)

		convite.reload()
		erros = [c for c in convite.convidados if c.status_envio == "Erro"]
		enviados = [c for c in convite.convidados if c.status_envio == "Enviado"]
		self.assertEqual(len(erros), 1)
		self.assertEqual(len(enviados), 1)
		self.assertTrue(self.mock_whatsapp.called)

	def test_forcar_todos_reenvia_para_enviado(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(
			festa.name,
			opcao.name,
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice", "email": "alice@example.com"},
				{"nome": "Bob", "email": "bob@example.com"},
			],
		)
		_marcar_cobranca_paga(convite.cobranca_infinitepay)

		enviar_qr_codes(convite.name)
		self.assertEqual(self.mock_sendmail.call_count, 2)

		# Sem forcar_todos: idempotente
		enviar_qr_codes(convite.name)
		self.assertEqual(self.mock_sendmail.call_count, 2)

		# Com forcar_todos: reenvia para todos
		enviar_qr_codes(convite.name, forcar_todos=True)
		self.assertEqual(self.mock_sendmail.call_count, 4)

	def test_idempotencia_nao_reenvia_para_enviado(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(
			festa.name,
			opcao.name,
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice", "email": "alice@example.com"},
			],
		)
		_marcar_cobranca_paga(convite.cobranca_infinitepay)

		enviar_qr_codes(convite.name)
		primeira = self.mock_sendmail.call_count

		# Segunda chamada não deve enviar nada
		enviar_qr_codes(convite.name)
		self.assertEqual(self.mock_sendmail.call_count, primeira)
