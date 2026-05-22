# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.festas.doctype.compra_festa.test_compra_festa import _nova_festa
from gris.festas.doctype.convite_festa.convite_festa import (
	enviar_whatsapp_confirmacao_convite,
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


def _convite(festa_name: str, opcao_name: str, *, pagador_recebe: bool, convidados):
	return frappe.get_doc(
		{
			"doctype": "Convite Festa",
			"festa": festa_name,
			"nome_pagador": "Caio Bernardo",
			"telefone_pagador": "11988887777",
			"email_pagador": "caio@example.com",
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
	frappe.db.set_value("Cobranca Infinitepay", cobranca_name, "status", "Pago")


class TestConfirmacaoWhatsApp(FrappeTestCase):
	def setUp(self):
		link_patcher = patch(
			"gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay.CobrancaInfinitepay._criar_link_pagamento",
			lambda self: None,
		)
		link_patcher.start()
		self.addCleanup(link_patcher.stop)

		whatsapp_patcher = patch("gris.utils.whatsapp.enviar_texto")
		self.mock_whatsapp = whatsapp_patcher.start()
		self.addCleanup(whatsapp_patcher.stop)

	def test_so_envia_quando_cobranca_esta_paga(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(
			festa.name,
			opcao.name,
			pagador_recebe=True,
			convidados=[{"nome": "Caio Bernardo", "email": "caio@example.com"}],
		)
		# Cobrança ainda Pendente
		enviar_whatsapp_confirmacao_convite(convite.name)
		self.mock_whatsapp.assert_not_called()

	def test_pagador_recebe_tudo_envia_apenas_para_pagador(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(
			festa.name,
			opcao.name,
			pagador_recebe=True,
			convidados=[
				{"nome": "Caio Bernardo", "email": "caio@example.com"},
				{"nome": "Caio Bernardo", "email": "caio@example.com"},
			],
		)
		_marcar_cobranca_paga(convite.cobranca_infinitepay)

		enviar_whatsapp_confirmacao_convite(convite.name)

		self.assertEqual(self.mock_whatsapp.call_count, 1)
		numero, mensagem = self.mock_whatsapp.call_args.args
		self.assertEqual(numero, "11988887777")
		self.assertIn("Caio", mensagem)
		# Não deve vazar e-mail completo
		self.assertNotIn("caio@example.com", mensagem)
		self.assertIn("c***@example.com", mensagem)
		# Link assinado presente
		self.assertIn("/festas/convite_confirmado?c=", mensagem)

		convite.reload()
		self.assertTrue(convite.whatsapp_notificado_em)

	def test_individual_envia_uma_para_cada_convidado_com_telefone(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(
			festa.name,
			opcao.name,
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice", "email": "alice@example.com", "telefone": "11911111111"},
				{"nome": "Bob", "email": "bob@example.com", "telefone": "11922222222"},
				{"nome": "Carol", "email": "carol@example.com"},  # sem telefone
			],
		)
		_marcar_cobranca_paga(convite.cobranca_infinitepay)

		enviar_whatsapp_confirmacao_convite(convite.name)

		# 1 pagador + 2 convidados com telefone = 3 chamadas
		self.assertEqual(self.mock_whatsapp.call_count, 3)
		numeros = [c.args[0] for c in self.mock_whatsapp.call_args_list]
		self.assertIn("11988887777", numeros)
		self.assertIn("11911111111", numeros)
		self.assertIn("11922222222", numeros)

		# Convidados não recebem o link assinado
		mensagens_convidados = [
			c.args[1] for c in self.mock_whatsapp.call_args_list if c.args[0] != "11988887777"
		]
		for msg in mensagens_convidados:
			self.assertNotIn("/festas/convite_confirmado?c=", msg)
			self.assertNotIn("11988887777", msg)
			self.assertNotIn("caio@example.com", msg)

	def test_idempotencia_nao_reenvia(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(
			festa.name,
			opcao.name,
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice", "email": "alice@example.com", "telefone": "11911111111"},
			],
		)
		_marcar_cobranca_paga(convite.cobranca_infinitepay)

		enviar_whatsapp_confirmacao_convite(convite.name)
		self.assertEqual(self.mock_whatsapp.call_count, 2)

		# Segunda execução não deve disparar nada (idempotência via timestamp)
		enviar_whatsapp_confirmacao_convite(convite.name)
		self.assertEqual(self.mock_whatsapp.call_count, 2)

	def test_falha_em_um_convidado_nao_interrompe_os_demais(self):
		festa = _nova_festa()
		opcao = _opcao(festa.name)
		convite = _convite(
			festa.name,
			opcao.name,
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice", "email": "alice@example.com", "telefone": "11911111111"},
				{"nome": "Bob", "email": "bob@example.com", "telefone": "11922222222"},
			],
		)
		_marcar_cobranca_paga(convite.cobranca_infinitepay)

		chamadas = {"n": 0}

		def side_effect(numero, mensagem, **kwargs):
			chamadas["n"] += 1
			if numero == "11911111111":
				raise RuntimeError("Network down")
			return None

		self.mock_whatsapp.side_effect = side_effect

		enviar_whatsapp_confirmacao_convite(convite.name)

		# pagador + 2 convidados (1 com erro)
		self.assertEqual(self.mock_whatsapp.call_count, 3)
