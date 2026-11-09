"""Transporte do WhatsApp: fila única, desconexão, retry e o id que a Evolution devolve.

Em 24/10/2026 o WhatsApp desvinculou o aparelho da instância depois de uma rajada de ~150
PDFs, e por 16 dias tudo falhou com erros que não diziam o motivo (500 ``reading
'onWhatsApp'`` e 400 ``['[object Object]']``). Os testes daqui cobrem o que mudou por isso.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.utils import now_datetime

from gris.utils import whatsapp
from gris.utils.whatsapp_errors import (
	WhatsAppConfigurationError,
	WhatsAppDesconectadoError,
	WhatsAppRequestError,
)

# A leitura real, guardada antes de os testes trocarem `_ultimo_envio_em` por um dublê.
_ULTIMO_ENVIO_REAL = whatsapp._ultimo_envio_em

CONFIG = {"url_api": "http://evolution.falsa", "api_key": "chave", "nome_instancia": "instancia"}


def _resposta(status: int, corpo=None, texto: str = ""):
	resposta = MagicMock()
	resposta.status_code = status
	if isinstance(corpo, Exception):
		resposta.json.side_effect = corpo
	else:
		resposta.json.return_value = corpo
	resposta.text = texto
	return resposta


class _EnvioBase(TestCase):
	"""Isola o envio do banco e da rede; quem quiser observar algo troca o dublê."""

	def setUp(self):
		self.registrar = self._patch(whatsapp, "_registrar_log")
		for nome in ("_registrar_sucesso", "_registrar_erro", "_logger"):
			self._patch(whatsapp, nome)
		self.get_config = self._patch(whatsapp, "_get_config", return_value=CONFIG)
		self.post = self._patch(whatsapp, "_post", return_value={"key": {"id": "ABC", "remoteJid": "1@lid"}})
		self.sleep = self._patch(whatsapp.time, "sleep")
		# A leitura real comita; em teste isso gravaria o que o teste deixou no banco.
		self.ultimo_envio = self._patch(whatsapp, "_ultimo_envio_em", return_value=None)

	def _patch(self, alvo, nome, **kwargs):
		patcher = patch.object(alvo, nome, **kwargs)
		self.addCleanup(patcher.stop)
		return patcher.start()


class TestIdDaMensagem(_EnvioBase):
	"""Sem o `key.id` não há como perguntar depois se a mensagem chegou."""

	def test_guarda_id_e_jid_e_fica_aguardando_confirmacao(self):
		whatsapp._enviar_texto_sync("11999998888", "Oi")

		kwargs = self.registrar.call_args.kwargs
		self.assertEqual(kwargs["status"], "Enviada")
		self.assertEqual(kwargs["id_mensagem"], "ABC")
		self.assertEqual(kwargs["jid_destino"], "1@lid")
		self.assertEqual(kwargs["entrega"], whatsapp.ENTREGA_AGUARDANDO)

	def test_grupo_nao_e_rastreavel(self):
		whatsapp._enviar_para_grupo_sync("123@g.us", "Aviso")

		self.assertEqual(self.registrar.call_args.kwargs["entrega"], whatsapp.ENTREGA_GRUPO)

	def test_sem_id_na_resposta_nao_fica_aguardando(self):
		self.post.return_value = {}

		whatsapp._enviar_texto_sync("11999998888", "Oi")

		self.assertEqual(self.registrar.call_args.kwargs["entrega"], "")


class TestNadaSePerdeSemLog(_EnvioBase):
	"""Toda falha, mesmo antes do POST, deixa a linha "Falhou" na ficha."""

	def test_configuracao_falhando_dentro_do_job_registra_falhou(self):
		self.get_config.side_effect = WhatsAppConfigurationError("Integração desabilitada.")

		with self.assertRaises(WhatsAppConfigurationError):
			whatsapp._enviar_texto_sync("11999998888", "Oi", contexto={"assunto": "Teste"})

		self.post.assert_not_called()
		self.assertEqual(self.registrar.call_args.kwargs["status"], "Falhou")
		self.assertIn("desabilitada", self.registrar.call_args.kwargs["erro"])

	def test_tipo_de_midia_invalido_registra_falhou(self):
		with self.assertRaises(WhatsAppRequestError):
			whatsapp._enviar_midia_sync("11999998888", "sticker", "base64")

		self.post.assert_not_called()
		self.assertEqual(self.registrar.call_args.kwargs["status"], "Falhou")


class TestDesconexao(_EnvioBase):
	"""Com a sessão caída, a Evolution responde de um jeito que não diz isso."""

	def _falha_http(self, status: int, detalhe: str):
		self.post.side_effect = WhatsAppRequestError(
			f"Evolution API retornou HTTP {status}: {detalhe}", status_code=status
		)

	def test_instancia_fechada_vira_desconectado(self):
		self._falha_http(500, "Cannot read properties of undefined (reading 'onWhatsApp')")

		with patch.object(whatsapp, "estado_da_conexao", return_value="close"):
			with self.assertRaises(WhatsAppDesconectadoError) as ctx:
				whatsapp._enviar_texto_sync("11999998888", "Oi")

		self.assertIn("WhatsApp desconectado", str(ctx.exception))
		self.assertIn("reconectar", str(ctx.exception))
		self.assertIn("WhatsApp desconectado", self.registrar.call_args.kwargs["erro"])
		# Erro de sessão não tem por que ser tentado de novo.
		self.post.assert_called_once()

	def test_grupo_com_object_object_e_explicado(self):
		self._falha_http(400, "{'response': {'message': ['[object Object]']}}")

		with patch.object(whatsapp, "estado_da_conexao", return_value="open"):
			with self.assertRaises(WhatsAppRequestError) as ctx:
				whatsapp._enviar_para_grupo_sync("123@g.us", "Aviso")

		self.assertIn("não encontrou o grupo", str(ctx.exception))

	def test_on_whatsapp_com_estado_desconhecido_e_explicado(self):
		self._falha_http(500, "Cannot read properties of undefined (reading 'onWhatsApp')")

		with patch.object(whatsapp, "estado_da_conexao", side_effect=WhatsAppRequestError("fora")):
			with self.assertRaises(WhatsAppRequestError) as ctx:
				whatsapp._enviar_texto_sync("11999998888", "Oi")

		self.assertIn("sessão com o WhatsApp não está ativa", str(ctx.exception))

	def test_falha_que_nao_e_http_nao_consulta_a_conexao(self):
		self.post.side_effect = RuntimeError("timeout")

		with patch.object(whatsapp, "estado_da_conexao") as estado:
			with self.assertRaises(RuntimeError):
				whatsapp._enviar_texto_sync("11999998888", "Oi")

		estado.assert_not_called()

	def test_estado_da_conexao_le_a_resposta_da_evolution(self):
		with patch.object(
			whatsapp, "_get", return_value={"instance": {"instanceName": "x", "state": "close"}}
		):
			self.assertEqual(whatsapp.estado_da_conexao(CONFIG), "close")


class TestFilaUnica(_EnvioBase):
	"""Um envio por vez e nunca dois colados: foi uma rajada que derrubou o número."""

	def test_espera_o_que_falta_do_intervalo(self):
		self.ultimo_envio.return_value = now_datetime() - timedelta(seconds=1)
		with patch.object(whatsapp.random, "uniform", return_value=5.0):
			whatsapp._aguardar_intervalo()

		espera = self.sleep.call_args[0][0]
		self.assertGreater(espera, 3.5)
		self.assertLessEqual(espera, 4.0)

	def test_nao_espera_se_o_intervalo_ja_passou(self):
		self.ultimo_envio.return_value = now_datetime() - timedelta(minutes=1)
		whatsapp._aguardar_intervalo()

		self.sleep.assert_not_called()

	def test_nunca_enviou_nao_espera(self):
		whatsapp._aguardar_intervalo()

		self.sleep.assert_not_called()

	def test_fila_ocupada_falha_sem_enviar(self):
		with patch.object(whatsapp.frappe.db, "sql", return_value=((0,),)):
			with self.assertRaises(WhatsAppRequestError) as ctx:
				whatsapp._enviar_texto_sync("11999998888", "Oi")

		self.assertIn("fila de envio", str(ctx.exception))
		self.post.assert_not_called()
		self.assertEqual(self.registrar.call_args.kwargs["status"], "Falhou")

	def test_lock_e_solto_mesmo_quando_o_post_falha(self):
		self.post.side_effect = RuntimeError("boom")

		with self.assertRaises(RuntimeError):
			whatsapp._enviar_texto_sync("11999998888", "Oi")

		livre = frappe.db.sql("SELECT IS_FREE_LOCK(%s)", (whatsapp.LOCK_ENVIO,))[0][0]
		self.assertEqual(livre, 1)

	def test_leitura_comita_antes_para_ver_o_outro_worker(self):
		ordem = MagicMock()
		with (
			patch.object(whatsapp.frappe.db, "commit", ordem.commit),
			patch.object(whatsapp.frappe.db, "sql", ordem.sql),
		):
			ordem.sql.return_value = (("2026-11-09 09:00:00",),)
			ultimo = _ULTIMO_ENVIO_REAL()

		self.assertEqual([chamada[0] for chamada in ordem.mock_calls], ["commit", "sql"])
		self.assertEqual(ultimo, datetime(2026, 11, 9, 9, 0))

	def test_requisicao_web_espera_menos_que_job(self):
		with patch.object(whatsapp.frappe.local, "request", object(), create=True):
			self.assertEqual(whatsapp._lock_timeout(), whatsapp.LOCK_TIMEOUT_REQUISICAO)
		self.assertLess(whatsapp.LOCK_TIMEOUT_REQUISICAO, whatsapp.LOCK_TIMEOUT_JOB)

	def test_envio_enfileirado_espera_o_commit_e_tem_tempo_para_a_fila(self):
		with patch.object(whatsapp.frappe, "enqueue") as enfileirar:
			whatsapp.enviar_texto("11999998888", "Oi")

		kwargs = enfileirar.call_args.kwargs
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.assertEqual(kwargs["timeout"], whatsapp.TIMEOUT_JOB_ENVIO)


class TestRetry(TestCase):
	"""Repetir um POST que pode ter sido entregue manda a mensagem duas vezes."""

	def setUp(self):
		for nome in ("_logger",):
			patcher = patch.object(whatsapp, nome)
			self.addCleanup(patcher.stop)
			patcher.start()
		patcher = patch.object(whatsapp.time, "sleep")
		self.addCleanup(patcher.stop)
		patcher.start()

	def _post(self, *respostas):
		with patch.object(whatsapp.requests, "post", side_effect=list(respostas)) as post:
			try:
				return whatsapp._post("/x", {}, config=CONFIG), post
			except Exception as erro:
				erro.post = post
				raise

	def test_500_nao_e_repetido(self):
		with self.assertRaises(WhatsAppRequestError) as ctx:
			self._post(_resposta(500, {"error": "Internal Server Error"}))

		self.assertEqual(ctx.exception.status_code, 500)
		self.assertEqual(ctx.exception.post.call_count, 1)

	def test_502_e_repetido(self):
		resultado, post = self._post(_resposta(502, ValueError()), _resposta(201, {"key": {"id": "A"}}))

		self.assertEqual(resultado, {"key": {"id": "A"}})
		self.assertEqual(post.call_count, 2)

	def test_tempo_esgotado_nao_e_repetido_e_avisa(self):
		with self.assertRaises(WhatsAppRequestError) as ctx:
			self._post(requests.ReadTimeout("lento"))

		self.assertIn("pode ter sido entregue", str(ctx.exception))
		self.assertEqual(ctx.exception.post.call_count, 1)

	def test_aceite_com_corpo_ilegivel_nao_vira_falha(self):
		resultado, _post = self._post(_resposta(201, ValueError()))

		self.assertEqual(resultado, {})


class TestVezSoSaiDepoisDoRegistro(_EnvioBase):
	"""O próximo da fila mede o intervalo por `ultimo_envio_em`: ele precisa estar gravado antes."""

	def test_sucesso_e_registrado_ainda_com_a_vez(self):
		ordem = MagicMock()
		self._patch(whatsapp, "_registrar_sucesso", new=ordem.sucesso)

		def sql(consulta, *args, **kwargs):
			ordem.sql(consulta.split("(")[0])
			return ((1,),)

		self._patch(whatsapp.frappe.db, "sql", side_effect=sql)

		whatsapp._enviar_texto_sync("11999998888", "Oi")

		passos = [c.args[0] if c[0] == "sql" else c[0] for c in ordem.mock_calls]
		self.assertEqual(passos, ["SELECT GET_LOCK", "sucesso", "SELECT RELEASE_LOCK"])

	def test_falha_no_registro_nao_vira_falhou(self):
		self._patch(whatsapp, "_registrar_sucesso", side_effect=RuntimeError("banco"))

		with self.assertRaises(RuntimeError):
			whatsapp._enviar_texto_sync("11999998888", "Oi")

		self.assertEqual([c.kwargs["status"] for c in self.registrar.call_args_list], ["Enviada"])
