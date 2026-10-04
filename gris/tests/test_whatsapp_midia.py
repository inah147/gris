"""Envio de mídia pelo WhatsApp (``enviar_midia``).

O convite da festa chega como documento PDF: sem ``fileName`` e ``mimetype`` a Evolution
entrega um arquivo sem nome nem extensão, que o celular não sabe abrir.
"""

from unittest import TestCase
from unittest.mock import patch

from gris.utils import whatsapp

CONFIG_FALSA = {"nome_instancia": "instancia", "api_key": "chave", "base_url": "http://exemplo"}


class TestEnviarMidia(TestCase):
	def _enviar(self, post=None, **kwargs):
		with (
			patch.object(whatsapp, "_get_config", return_value=CONFIG_FALSA),
			patch.object(whatsapp, "_post", **(post or {"return_value": {"key": {"id": "X"}}})) as post_,
			patch.object(whatsapp, "_registrar_sucesso"),
			patch.object(whatsapp, "_registrar_erro"),
			patch.object(whatsapp, "_logger"),
			patch.object(whatsapp, "_registrar_log") as registrar,
		):
			try:
				whatsapp._enviar_midia_sync("11988887777", "document", "JVBERi0=", **kwargs)
			finally:
				self.post = post_
				self.registrar = registrar

	def test_documento_leva_nome_e_tipo_do_arquivo(self):
		self._enviar(caption="Seu convite", nome_arquivo="convite.pdf", mimetype="application/pdf")

		rota, payload = self.post.call_args[0][:2]
		self.assertEqual(rota, "/message/sendMedia/instancia")
		self.assertEqual(payload["mediatype"], "document")
		self.assertEqual(payload["media"], "JVBERi0=")
		self.assertEqual(payload["fileName"], "convite.pdf")
		self.assertEqual(payload["mimetype"], "application/pdf")
		self.assertEqual(payload["caption"], "Seu convite")
		self.assertEqual(payload["number"], "5511988887777")

	def test_sem_nome_nem_tipo_o_payload_continua_como_antes(self):
		self._enviar()

		payload = self.post.call_args[0][1]
		self.assertNotIn("fileName", payload)
		self.assertNotIn("mimetype", payload)
		self.assertNotIn("caption", payload)

	def test_sucesso_registra_legenda_e_anexo(self):
		contexto = {"assunto": "Convite da festa", "destinatario_tipo": "Convidado de festa"}
		self._enviar(caption="Seu convite", nome_arquivo="convite.pdf", contexto=contexto)

		self.assertEqual(self.registrar.call_args[0][0], contexto)
		self.assertEqual(self.registrar.call_args.kwargs["status"], "Enviada")
		self.assertEqual(self.registrar.call_args.kwargs["numero"], "11988887777")
		conteudo = self.registrar.call_args.kwargs["conteudo"]
		self.assertIn("Seu convite", conteudo)
		self.assertIn("[anexo: convite.pdf]", conteudo)
		# O base64 do arquivo não vai para o log.
		self.assertNotIn("JVBERi0=", conteudo)

	def test_falha_registra_falhou_e_propaga(self):
		with self.assertRaises(RuntimeError):
			self._enviar(post={"side_effect": RuntimeError("timeout")}, nome_arquivo="convite.pdf")

		self.assertEqual(self.registrar.call_args.kwargs["status"], "Falhou")
		self.assertIn("timeout", self.registrar.call_args.kwargs["erro"])

	def test_contexto_e_arquivo_atravessam_a_fila(self):
		with patch.object(whatsapp.frappe, "enqueue") as enfileirar:
			whatsapp.enviar_midia(
				"11988887777",
				"document",
				"JVBERi0=",
				nome_arquivo="convite.pdf",
				mimetype="application/pdf",
				contexto={"assunto": "Teste"},
			)

		kwargs = enfileirar.call_args.kwargs
		self.assertEqual(kwargs["contexto"], {"assunto": "Teste"})
		self.assertEqual(kwargs["nome_arquivo"], "convite.pdf")
		self.assertEqual(kwargs["mimetype"], "application/pdf")
