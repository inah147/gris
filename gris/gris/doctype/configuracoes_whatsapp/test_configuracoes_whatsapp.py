# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.utils import whatsapp as whatsapp_utils


class TestConfiguracoesWhatsApp(FrappeTestCase):
	def test_enviar_para_grupo_com_mencao_de_todos_no_payload(self):
		original_get_config = whatsapp_utils._get_config
		original_post = whatsapp_utils._post
		original_registrar_sucesso = whatsapp_utils._registrar_sucesso
		original_logger = whatsapp_utils._logger

		capturado = {}

		class _DummyLogger:
			def info(self, *args, **kwargs):
				return None

		try:
			whatsapp_utils._get_config = lambda: {
				"url_api": "https://evolution.example",
				"api_key": "secret",
				"nome_instancia": "instancia-1",
			}

			def _fake_post(endpoint, payload, config=None):
				capturado["endpoint"] = endpoint
				capturado["payload"] = payload
				return {"status": "PENDING"}

			whatsapp_utils._post = _fake_post
			whatsapp_utils._registrar_sucesso = lambda: None
			whatsapp_utils._logger = lambda: _DummyLogger()

			resposta = whatsapp_utils.enviar_para_grupo(
				"120363408543428156@g.us",
				"@todos Mensagem de teste",
				mencionar_todos=True,
				enqueue=False,
			)

			self.assertEqual(resposta, {"status": "PENDING"})
			self.assertEqual(capturado["endpoint"], "/message/sendText/instancia-1")
			self.assertEqual(capturado["payload"]["number"], "120363408543428156@g.us")
			self.assertEqual(capturado["payload"]["text"], "@todos Mensagem de teste")
			self.assertTrue(capturado["payload"]["mentionsEveryOne"])
		finally:
			whatsapp_utils._get_config = original_get_config
			whatsapp_utils._post = original_post
			whatsapp_utils._registrar_sucesso = original_registrar_sucesso
			whatsapp_utils._logger = original_logger

	def test_enviar_para_grupo_com_mencao_individual_no_payload(self):
		capturado, restaurar = self._interceptar_post()

		try:
			whatsapp_utils.enviar_para_grupo(
				"120363408543428156@g.us",
				"@5511999998888 confira os dados",
				mencionar=["(11) 99999-8888", "11999998888", ""],
				enqueue=False,
			)

			payload = capturado["payload"]
			# Números normalizados e sem repetição; menção geral fica fora do payload.
			self.assertEqual(payload["mentioned"], ["5511999998888"])
			self.assertNotIn("mentionsEveryOne", payload)
		finally:
			restaurar()

	def test_adicionar_participantes_no_grupo_usa_group_jid_na_query(self):
		capturado, restaurar = self._interceptar_post()

		try:
			whatsapp_utils.adicionar_participantes_no_grupo(
				"120363408543428156@g.us",
				["+55 11 99999-8888"],
				enqueue=False,
			)

			self.assertEqual(capturado["endpoint"], "/group/updateParticipant/instancia-1")
			self.assertEqual(capturado["params"], {"groupJid": "120363408543428156@g.us"})
			self.assertEqual(
				capturado["payload"],
				{"action": "add", "participants": ["5511999998888"]},
			)
		finally:
			restaurar()

	def _interceptar_post(self):
		"""Substitui config, `_post`, logger e marcador de sucesso; devolve o que foi enviado."""
		originais = {
			"_get_config": whatsapp_utils._get_config,
			"_post": whatsapp_utils._post,
			"_registrar_sucesso": whatsapp_utils._registrar_sucesso,
			"_logger": whatsapp_utils._logger,
		}
		capturado = {}

		class _DummyLogger:
			def info(self, *args, **kwargs):
				return None

		def _fake_post(endpoint, payload, params=None, config=None):
			capturado["endpoint"] = endpoint
			capturado["payload"] = payload
			capturado["params"] = params
			return {"status": "PENDING"}

		whatsapp_utils._get_config = lambda: {
			"url_api": "https://evolution.example",
			"api_key": "secret",
			"nome_instancia": "instancia-1",
		}
		whatsapp_utils._post = _fake_post
		whatsapp_utils._registrar_sucesso = lambda: None
		whatsapp_utils._logger = lambda: _DummyLogger()

		def _restaurar():
			for nome, valor in originais.items():
				setattr(whatsapp_utils, nome, valor)

		return capturado, _restaurar

	def test_listar_grupos_whatsapp_ordena_e_filtra_retorno(self):
		original_get = whatsapp_utils._get
		original_get_config = whatsapp_utils._get_config

		try:
			whatsapp_utils._get_config = lambda: {
				"url_api": "https://evolution.example",
				"api_key": "secret",
				"nome_instancia": "instancia-1",
			}
			whatsapp_utils._get = lambda endpoint, params=None, config=None: [
				{"id": "120363423777366208@g.us", "subject": "Contatos Santer"},
				{"id": "120363408543428156@g.us", "subject": "Recepção"},
				{"id": "", "subject": "Sem id"},
			]

			grupos = whatsapp_utils.listar_grupos_whatsapp()

			self.assertEqual(
				grupos,
				[
					{"id": "120363423777366208@g.us", "subject": "Contatos Santer"},
					{"id": "120363408543428156@g.us", "subject": "Recepção"},
				],
			)
		finally:
			whatsapp_utils._get = original_get
			whatsapp_utils._get_config = original_get_config

	def test_listar_grupos_whatsapp_para_select_retorna_label_e_valor(self):
		original_has_permission = whatsapp_utils.frappe.has_permission
		original_listar_grupos_whatsapp = whatsapp_utils.listar_grupos_whatsapp

		try:
			whatsapp_utils.frappe.has_permission = lambda *args, **kwargs: True
			whatsapp_utils.listar_grupos_whatsapp = lambda get_participants=False: [
				{"id": "120363408543428156@g.us", "subject": "Recepção"}
			]

			opcoes = whatsapp_utils.listar_grupos_whatsapp_para_select()

			self.assertEqual(
				opcoes,
				[
					{
						"label": "Recepção (120363408543428156@g.us)",
						"value": "120363408543428156@g.us",
					}
				],
			)
		finally:
			whatsapp_utils.frappe.has_permission = original_has_permission
			whatsapp_utils.listar_grupos_whatsapp = original_listar_grupos_whatsapp

	def test_listar_grupos_whatsapp_para_select_exige_permissao(self):
		original_has_permission = whatsapp_utils.frappe.has_permission

		try:
			whatsapp_utils.frappe.has_permission = lambda *args, **kwargs: False

			with self.assertRaises(frappe.PermissionError):
				whatsapp_utils.listar_grupos_whatsapp_para_select()
		finally:
			whatsapp_utils.frappe.has_permission = original_has_permission
