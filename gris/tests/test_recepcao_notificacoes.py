import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api import recepcao_notificacoes


class TestRecepcaoNotificacoes(FrappeTestCase):
	def test_notificar_nova_manifestacao_envia_para_grupo_configurado(self):
		original_get_single_value = recepcao_notificacoes.frappe.db.get_single_value
		original_enviar_para_grupo = recepcao_notificacoes.enviar_para_grupo
		original_today = recepcao_notificacoes.today

		enviadas = []

		def _fake_enviar_para_grupo(grupo_jid, mensagem, mencionar_todos=False):
			enviadas.append(
				{
					"grupo_jid": grupo_jid,
					"mensagem": mensagem,
					"mencionar_todos": mencionar_todos,
				}
			)

		try:
			recepcao_notificacoes.frappe.db.get_single_value = lambda *args, **kwargs: (
				"120363408543428156@g.us"
			)
			recepcao_notificacoes.enviar_para_grupo = _fake_enviar_para_grupo
			recepcao_notificacoes.today = lambda: "2026-04-14"

			recepcao_notificacoes.notificar_nova_manifestacao_no_grupo_recepcao(
				nome_jovem="Joao da Silva",
				nome_responsavel="Maria da Silva",
				data_nascimento_jovem="2015-04-14",
				contexto="teste",
			)

			self.assertEqual(len(enviadas), 1)
			self.assertEqual(enviadas[0]["grupo_jid"], "120363408543428156@g.us")
			self.assertTrue(enviadas[0]["mencionar_todos"])
			self.assertIn("@todos", enviadas[0]["mensagem"])
			self.assertIn("Joao da Silva", enviadas[0]["mensagem"])
			self.assertIn("Maria da Silva", enviadas[0]["mensagem"])
			self.assertIn("11 anos", enviadas[0]["mensagem"])
		finally:
			recepcao_notificacoes.frappe.db.get_single_value = original_get_single_value
			recepcao_notificacoes.enviar_para_grupo = original_enviar_para_grupo
			recepcao_notificacoes.today = original_today

	def test_notificar_nova_manifestacao_nao_envia_sem_grupo_configurado(self):
		original_get_single_value = recepcao_notificacoes.frappe.db.get_single_value
		original_enviar_para_grupo = recepcao_notificacoes.enviar_para_grupo

		enviadas = []

		def _fake_enviar_para_grupo(grupo_jid, mensagem, mencionar_todos=False):
			enviadas.append(
				{
					"grupo_jid": grupo_jid,
					"mensagem": mensagem,
					"mencionar_todos": mencionar_todos,
				}
			)

		try:
			recepcao_notificacoes.frappe.db.get_single_value = lambda *args, **kwargs: ""
			recepcao_notificacoes.enviar_para_grupo = _fake_enviar_para_grupo

			recepcao_notificacoes.notificar_nova_manifestacao_no_grupo_recepcao(
				nome_jovem="Joao",
				nome_responsavel="Maria",
				data_nascimento_jovem="2015-04-14",
				contexto="teste",
			)

			self.assertEqual(enviadas, [])
		finally:
			recepcao_notificacoes.frappe.db.get_single_value = original_get_single_value
			recepcao_notificacoes.enviar_para_grupo = original_enviar_para_grupo

	def test_notificar_nova_manifestacao_usa_fallback_sem_data_valida(self):
		original_get_single_value = recepcao_notificacoes.frappe.db.get_single_value
		original_enviar_para_grupo = recepcao_notificacoes.enviar_para_grupo

		enviadas = []

		def _fake_enviar_para_grupo(grupo_jid, mensagem, mencionar_todos=False):
			enviadas.append(
				{
					"grupo_jid": grupo_jid,
					"mensagem": mensagem,
					"mencionar_todos": mencionar_todos,
				}
			)

		try:
			recepcao_notificacoes.frappe.db.get_single_value = lambda *args, **kwargs: (
				"120363408543428156@g.us"
			)
			recepcao_notificacoes.enviar_para_grupo = _fake_enviar_para_grupo

			recepcao_notificacoes.notificar_nova_manifestacao_no_grupo_recepcao(
				nome_jovem="Joao",
				nome_responsavel="Maria",
				data_nascimento_jovem="invalida",
				contexto="teste",
			)

			self.assertEqual(len(enviadas), 1)
			self.assertTrue(enviadas[0]["mencionar_todos"])
			self.assertIn("*Idade do jovem*: não informada.", enviadas[0]["mensagem"])
		finally:
			recepcao_notificacoes.frappe.db.get_single_value = original_get_single_value
			recepcao_notificacoes.enviar_para_grupo = original_enviar_para_grupo
