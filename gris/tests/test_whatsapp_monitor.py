"""Alerta por e-mail quando o WhatsApp cai — e silêncio quando está tudo certo."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.utils import whatsapp_monitor
from gris.utils.whatsapp_errors import WhatsAppRequestError

CONFIG = {"url_api": "http://evolution.falsa", "api_key": "chave", "nome_instancia": "gepim-principal"}

INSTANCIA_CAIDA = [
	{
		"name": "gepim-principal",
		"connectionStatus": "close",
		"disconnectionReasonCode": 401,
		"disconnectionAt": "2026-10-24T15:23:05.251Z",
		"token": "nao-pode-ir-no-email",
	}
]


def _configuracoes(**valores):
	return lambda _doctype, fieldname, *args, **kwargs: valores.get(fieldname)


class TestVerificarConexao(FrappeTestCase):
	def _verificar(self, *, habilitada=1, estado="close", emails="alerta@exemplo.com", instancias=None):
		estado_kwargs = {"side_effect": estado} if isinstance(estado, Exception) else {"return_value": estado}
		with (
			patch.object(
				whatsapp_monitor.frappe.db,
				"get_single_value",
				side_effect=_configuracoes(habilitar_integracao=habilitada, emails_alerta_desconexao=emails),
			),
			patch.object(whatsapp_monitor, "_get_config", return_value=CONFIG),
			patch.object(whatsapp_monitor, "estado_da_conexao", **estado_kwargs),
			patch.object(whatsapp_monitor, "_get", return_value=instancias or []),
			patch.object(whatsapp_monitor.frappe, "sendmail") as sendmail,
		):
			whatsapp_monitor.verificar_conexao_whatsapp()
		return sendmail

	def test_conectado_nao_manda_nada(self):
		self._verificar(estado="open").assert_not_called()

	def test_integracao_desligada_nao_manda_nada(self):
		self._verificar(habilitada=0).assert_not_called()

	def test_desconectado_avisa_com_desde_quando_e_motivo(self):
		sendmail = self._verificar(instancias=INSTANCIA_CAIDA)

		sendmail.assert_called_once()
		kwargs = sendmail.call_args.kwargs
		self.assertEqual(kwargs["recipients"], ["alerta@exemplo.com"])
		self.assertIn("desconectado", kwargs["subject"])
		corpo = kwargs["message"]
		self.assertIn("gepim-principal", corpo)
		self.assertIn("24/10/2026", corpo)
		self.assertIn("desvinculou o aparelho", corpo)
		self.assertIn("Aparelhos conectados", corpo)
		self.assertNotIn("nao-pode-ir-no-email", corpo)

	def test_evolution_sem_resposta_tambem_avisa(self):
		sendmail = self._verificar(estado=WhatsAppRequestError("Falha de conexão"))

		sendmail.assert_called_once()
		self.assertIn("não respondeu", sendmail.call_args.kwargs["message"])


class TestDestinatarios(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_emails_configurados_separados_por_linha_virgula_e_sem_invalidos(self):
		with patch.object(
			whatsapp_monitor.frappe.db,
			"get_single_value",
			return_value="a@exemplo.com, b@exemplo.com\ninvalido\na@exemplo.com",
		):
			self.assertEqual(whatsapp_monitor.destinatarios_do_alerta(), ["a@exemplo.com", "b@exemplo.com"])

	def test_sem_emails_vao_os_system_managers_ativos(self):
		ativo = self._usuario("e2e-alerta-ativo@exemplo.com", enabled=1)
		inativo = self._usuario("e2e-alerta-inativo@exemplo.com", enabled=0)

		with patch.object(whatsapp_monitor.frappe.db, "get_single_value", return_value=""):
			destinatarios = whatsapp_monitor.destinatarios_do_alerta()

		self.assertIn(ativo, destinatarios)
		self.assertNotIn(inativo, destinatarios)
		self.assertNotIn("admin@example.com", destinatarios)

	def _usuario(self, email: str, *, enabled: int) -> str:
		usuario = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "E2E Alerta",
				"send_welcome_email": 0,
				"enabled": enabled,
				"roles": [{"role": "System Manager"}],
			}
		)
		usuario.flags.no_welcome_mail = True
		usuario.insert(ignore_permissions=True)
		return email
