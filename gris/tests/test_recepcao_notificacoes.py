import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api import recepcao_notificacoes


def _configuracoes(**valores):
	"""Dublê de ``get_single_value`` que responde por fieldname.

	Os interruptores ``msg_*`` de Configurações de Recepção passam por aqui: um dublê que
	devolve o mesmo valor para qualquer campo faria o Check ler o JID do grupo e desligar
	a mensagem. Campo não informado volta ``None``, que conta como ligado.
	"""
	return lambda _doctype, fieldname, *args, **kwargs: valores.get(fieldname)


class TestRecepcaoNotificacoes(FrappeTestCase):
	def test_notificar_nova_manifestacao_envia_para_grupo_configurado(self):
		original_get_single_value = recepcao_notificacoes.frappe.db.get_single_value
		original_enviar_para_grupo = recepcao_notificacoes.enviar_para_grupo
		original_today = recepcao_notificacoes.today

		enviadas = []

		def _fake_enviar_para_grupo(grupo_jid, mensagem, mencionar_todos=False, contexto=None):
			enviadas.append(
				{
					"grupo_jid": grupo_jid,
					"mensagem": mensagem,
					"mencionar_todos": mencionar_todos,
				}
			)

		try:
			recepcao_notificacoes.frappe.db.get_single_value = _configuracoes(
				grupo_recepcao_whatsapp="120363408543428156@g.us"
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

		def _fake_enviar_para_grupo(grupo_jid, mensagem, mencionar_todos=False, contexto=None):
			enviadas.append(
				{
					"grupo_jid": grupo_jid,
					"mensagem": mensagem,
					"mencionar_todos": mencionar_todos,
				}
			)

		try:
			recepcao_notificacoes.frappe.db.get_single_value = _configuracoes()
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

		def _fake_enviar_para_grupo(grupo_jid, mensagem, mencionar_todos=False, contexto=None):
			enviadas.append(
				{
					"grupo_jid": grupo_jid,
					"mensagem": mensagem,
					"mencionar_todos": mencionar_todos,
				}
			)

		try:
			recepcao_notificacoes.frappe.db.get_single_value = _configuracoes(
				grupo_recepcao_whatsapp="120363408543428156@g.us"
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


class TestLembreteDeVisita(FrappeTestCase):
	"""O lembrete vai em texto: com botões (`sendButtons`) um terço nunca teve confirmação de entrega."""

	def test_vai_em_texto_e_pede_resposta(self):
		from unittest.mock import patch

		visita = frappe._dict(name="AV-1", jovem="NA-1", data_da_visita="2026-11-11")
		get_value = frappe.db.get_value

		def nome_do_jovem(doctype, *args, **kwargs):
			# `today()` também lê o fuso por get_value: só o nome do jovem é dublado.
			if doctype == "Novo Associado":
				return "Jovem Teste"
			return get_value(doctype, *args, **kwargs)

		with (
			patch.object(recepcao_notificacoes, "_mensagem_habilitada", return_value=True),
			patch.object(recepcao_notificacoes.frappe, "get_all", return_value=[visita]),
			patch.object(recepcao_notificacoes, "_buscar_telefone_responsavel", return_value="11999998888"),
			patch.object(recepcao_notificacoes.frappe.db, "get_value", side_effect=nome_do_jovem),
			patch.object(recepcao_notificacoes, "enviar_texto") as enviar_texto,
		):
			recepcao_notificacoes.enviar_lembretes_visita()

		enviar_texto.assert_called_once()
		numero, mensagem = enviar_texto.call_args[0]
		self.assertEqual(numero, "11999998888")
		self.assertIn("Jovem Teste", mensagem)
		self.assertIn("11/11", mensagem)
		self.assertIn("Responda esta mensagem", mensagem)
		self.assertEqual(enviar_texto.call_args.kwargs["contexto"]["assunto"], "Lembrete de visita")
		self.assertFalse(hasattr(recepcao_notificacoes, "enviar_mensagem_formatada"))
