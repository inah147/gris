# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt
"""Reenvio do convite por e-mail e WhatsApp (Desk, painel da festa e portaria)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.festas import convites, portaria
from gris.festas.doctype.compra_festa.test_compra_festa import _nova_festa
from gris.festas.doctype.convite_festa.convite_festa import (
	_criar_lista_entrada,
	enfileirar_envio_convite,
	reenviar_qr_codes,
)
from gris.festas.doctype.convite_festa.test_convite_envio import (
	_convite,
	_marcar_cobranca_paga,
	_opcao,
)

MODULO = "gris.festas.doctype.convite_festa.convite_festa."
JOB_EMAIL = MODULO + "enviar_qr_codes"
JOB_WHATSAPP = MODULO + "enviar_convites_whatsapp"


class TestReenvioConvite(FrappeTestCase):
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

		self.festa = _nova_festa()
		self.opcao = _opcao(self.festa.name)
		self.mock_enqueue.reset_mock()

	def tearDown(self):
		frappe.db.rollback()

	def _convite_pago(self, *, pagador_recebe=False, convidados=None):
		convite = _convite(
			self.festa.name,
			self.opcao.name,
			pagador_recebe=pagador_recebe,
			convidados=convidados
			or [{"nome": "Ana Souza", "email": "ana@example.com", "telefone": "11977771234"}],
		)
		_marcar_cobranca_paga(convite.cobranca_infinitepay)
		convite.reload()
		self.mock_enqueue.reset_mock()
		return convite

	def _contato(self, row_name, **valores):
		frappe.db.set_value("Convidado Convite Festa", row_name, valores)

	def _jobs(self, metodo):
		return [c for c in self.mock_enqueue.call_args_list if c.args and c.args[0] == metodo]

	# ---------- helper ----------

	def test_convidado_com_email_e_telefone_vai_pelos_dois_canais(self):
		row = self._convite_pago().convidados[0]

		canais = enfileirar_envio_convite(row.parent, convidado_row_name=row.name, forcar_todos=True)

		self.assertEqual(canais, {"email": True, "whatsapp": True})
		(email,) = self._jobs(JOB_EMAIL)
		(whatsapp,) = self._jobs(JOB_WHATSAPP)
		self.assertEqual(email.kwargs["convidado_row_name"], row.name)
		self.assertTrue(email.kwargs["forcar_todos"])
		self.assertEqual(whatsapp.kwargs["convidado_row_name"], row.name)
		self.assertTrue(whatsapp.kwargs["forcar"])

	def test_convidado_so_com_telefone_vai_so_pelo_whatsapp(self):
		row = self._convite_pago().convidados[0]
		self._contato(row.name, email=None)

		canais = enfileirar_envio_convite(row.parent, convidado_row_name=row.name, forcar_todos=True)

		self.assertEqual(canais, {"email": False, "whatsapp": True})
		self.assertEqual(self._jobs(JOB_EMAIL), [])
		self.assertEqual(len(self._jobs(JOB_WHATSAPP)), 1)

	def test_convidado_so_com_email_vai_so_pelo_email(self):
		row = self._convite_pago().convidados[0]
		self._contato(row.name, telefone=None)

		canais = enfileirar_envio_convite(row.parent, convidado_row_name=row.name, forcar_todos=True)

		self.assertEqual(canais, {"email": True, "whatsapp": False})
		self.assertEqual(self._jobs(JOB_WHATSAPP), [])

	def test_convidado_sem_contato_nenhum_e_recusado(self):
		row = self._convite_pago().convidados[0]
		self._contato(row.name, email=None, telefone=None)

		with self.assertRaises(frappe.ValidationError):
			enfileirar_envio_convite(row.parent, convidado_row_name=row.name, forcar_todos=True)
		self.mock_enqueue.assert_not_called()

	# ---------- endpoints ----------

	def test_desk_reenvia_o_pedido_pelos_dois_canais(self):
		convite = self._convite_pago(pagador_recebe=True, convidados=[{"nome": "X"}, {"nome": "Y"}])

		resposta = reenviar_qr_codes(convite.name, forcar_todos=0)

		self.assertTrue(resposta["ok"])
		self.assertIn("WhatsApp", resposta["mensagem"])
		(email,) = self._jobs(JOB_EMAIL)
		(whatsapp,) = self._jobs(JOB_WHATSAPP)
		self.assertFalse(email.kwargs["forcar_todos"])
		self.assertIsNone(whatsapp.kwargs["convidado_row_name"])
		self.assertFalse(whatsapp.kwargs["forcar"])

	def test_painel_reenvia_convidado_que_so_tem_telefone(self):
		row = self._convite_pago().convidados[0]
		self._contato(row.name, email=None)

		resposta = convites.reenviar_convite_convidado(row.name)

		self.assertTrue(resposta["ok"])
		self.assertEqual(resposta["mensagem"], "Convite reenviado pelo WhatsApp.")
		self.assertEqual(self._jobs(JOB_WHATSAPP)[0].kwargs["convidado_row_name"], row.name)

	def test_portaria_reenvia_convidado_que_so_tem_telefone(self):
		convite = self._convite_pago()
		row = convite.convidados[0]
		_criar_lista_entrada(convite.name)
		entrada = frappe.db.get_value("Lista Entrada Festa", {"convidado_row": row.name}, "name")
		self.mock_enqueue.reset_mock()
		self._contato(row.name, email=None)
		frappe.db.set_value("Lista Entrada Festa", entrada, "email", None)

		resposta = portaria.reenviar_convite(entrada)

		self.assertTrue(resposta["ok"])
		self.assertEqual(resposta["mensagem"], "Convite reenviado pelo WhatsApp.")
		self.assertEqual(self._jobs(JOB_EMAIL), [])
		self.assertEqual(self._jobs(JOB_WHATSAPP)[0].kwargs["convidado_row_name"], row.name)

	def test_portaria_recusa_convidado_sem_contato(self):
		convite = self._convite_pago()
		row = convite.convidados[0]
		_criar_lista_entrada(convite.name)
		entrada = frappe.db.get_value("Lista Entrada Festa", {"convidado_row": row.name}, "name")
		self.mock_enqueue.reset_mock()
		self._contato(row.name, email=None, telefone=None)

		with self.assertRaises(frappe.ValidationError):
			portaria.reenviar_convite(entrada)
		self.mock_enqueue.assert_not_called()
