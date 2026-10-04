# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt

import base64
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.festas.doctype.compra_festa.test_compra_festa import _nova_festa
from gris.festas.doctype.convite_festa.convite_festa import (
	ConviteFesta,
	enviar_convites_whatsapp,
	enviar_whatsapp_confirmacao_convite,
)
from gris.utils.whatsapp_errors import WhatsAppConfigurationError, WhatsAppNumberNotFoundError

JOB_PDFS = "gris.festas.doctype.convite_festa.convite_festa.enviar_convites_whatsapp"
TELEFONE_PAGADOR = "11988887777"
PDF_FALSO = b"%PDF-FAKE"


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
			"telefone_pagador": TELEFONE_PAGADOR,
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


def _whatsapp_do_convidado(row_name: str) -> frappe._dict:
	return frappe.db.get_value(
		"Convidado Convite Festa",
		row_name,
		["status_envio_whatsapp", "descricao_erro_whatsapp", "whatsapp_notificado_em", "token_link"],
		as_dict=True,
	)


class _BaseWhatsApp(FrappeTestCase):
	def setUp(self):
		for alvo, kwargs in (
			(
				"gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay.CobrancaInfinitepay._criar_link_pagamento",
				{"new": lambda self: None},
			),
			("gris.utils.whatsapp.enviar_texto", {}),
			("gris.utils.whatsapp.enviar_midia", {}),
			("gris.festas.utils.convite_qr.gerar_pdf_convite", {"return_value": PDF_FALSO}),
			("frappe.enqueue", {}),
		):
			patcher = patch(alvo, **kwargs)
			mock = patcher.start()
			self.addCleanup(patcher.stop)
			if alvo.endswith("enviar_texto"):
				self.mock_texto = mock
			elif alvo.endswith("enviar_midia"):
				self.mock_midia = mock
			elif alvo.endswith("gerar_pdf_convite"):
				self.mock_pdf = mock
			elif alvo == "frappe.enqueue":
				self.mock_enqueue = mock

		# O job comita por convidado; no teste isso gravaria os dados de verdade no site.
		commit_patcher = patch.object(frappe.db, "commit")
		commit_patcher.start()
		self.addCleanup(commit_patcher.stop)

		self.festa = _nova_festa()
		self.opcao = _opcao(self.festa.name)

	def tearDown(self):
		frappe.db.rollback()

	def _convite_pago(self, *, pagador_recebe: bool, convidados, pagar: bool = True):
		convite = _convite(
			self.festa.name, self.opcao.name, pagador_recebe=pagador_recebe, convidados=convidados
		)
		if pagar:
			_marcar_cobranca_paga(convite.cobranca_infinitepay)
		convite.reload()
		return convite

	def _enfileirados(self, metodo: str) -> list:
		return [c for c in self.mock_enqueue.call_args_list if c.args and c.args[0] == metodo]


class TestConfirmacaoWhatsApp(_BaseWhatsApp):
	"""Texto ao pagador e, depois dele, o job que manda os PDFs."""

	def test_so_envia_quando_cobranca_esta_paga(self):
		convite = self._convite_pago(
			pagador_recebe=True,
			convidados=[{"nome": "Caio Bernardo", "email": "caio@example.com"}],
			pagar=False,
		)

		enviar_whatsapp_confirmacao_convite(convite.name)

		self.mock_texto.assert_not_called()
		self.assertEqual(self._enfileirados(JOB_PDFS), [])

	def test_pagador_recebe_tudo_avisa_que_os_pdfs_chegam_no_whatsapp(self):
		convite = self._convite_pago(
			pagador_recebe=True,
			convidados=[{"nome": "Caio Bernardo"}, {"nome": "Dora Bernardo"}],
		)

		enviar_whatsapp_confirmacao_convite(convite.name)

		self.assertEqual(self.mock_texto.call_count, 1)
		numero, mensagem = self.mock_texto.call_args.args
		self.assertEqual(numero, TELEFONE_PAGADOR)
		self.assertIn("Caio", mensagem)
		self.assertIn("WhatsApp", mensagem)
		# Não deve vazar e-mail completo
		self.assertNotIn("caio@example.com", mensagem)
		self.assertIn("c***@example.com", mensagem)
		# Link assinado presente
		self.assertIn("/festas/convite_confirmado?c=", mensagem)

		convite.reload()
		self.assertTrue(convite.whatsapp_notificado_em)

	def test_pdfs_sao_enfileirados_depois_do_texto_do_pagador(self):
		convite = self._convite_pago(
			pagador_recebe=True,
			convidados=[{"nome": "Caio Bernardo"}],
		)

		enviar_whatsapp_confirmacao_convite(convite.name)

		jobs = self._enfileirados(JOB_PDFS)
		self.assertEqual(len(jobs), 1)
		self.assertEqual(jobs[0].kwargs["convite_name"], convite.name)
		self.assertEqual(jobs[0].kwargs["queue"], "long")
		# O texto sai dentro deste job, não noutra fila: só assim chega antes dos PDFs.
		self.assertFalse(self.mock_texto.call_args.kwargs["enqueue"])
		self.assertEqual(self.mock_texto.call_args.kwargs["contexto"]["destinatario_nome"], "Caio Bernardo")
		# O job dos PDFs não manda nada por conta própria aqui.
		self.mock_midia.assert_not_called()

	def test_individual_nao_manda_mais_texto_aos_convidados(self):
		"""O texto "você receberá no e-mail" deu lugar ao PDF, que já se apresenta."""
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice", "email": "alice@example.com", "telefone": "11911111111"},
				{"nome": "Bob", "email": "bob@example.com", "telefone": "11922222222"},
			],
		)

		enviar_whatsapp_confirmacao_convite(convite.name)

		self.assertEqual(self.mock_texto.call_count, 1)
		self.assertEqual(self.mock_texto.call_args.args[0], TELEFONE_PAGADOR)
		self.assertEqual(len(self._enfileirados(JOB_PDFS)), 1)

	def test_idempotencia_do_texto_do_pagador(self):
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[{"nome": "Alice", "email": "alice@example.com", "telefone": "11911111111"}],
		)

		enviar_whatsapp_confirmacao_convite(convite.name)
		enviar_whatsapp_confirmacao_convite(convite.name)

		# O job dos PDFs é idempotente por convidado; o texto do pagador, pelo timestamp.
		self.assertEqual(self.mock_texto.call_count, 1)


class TestEnvioConvitesWhatsApp(_BaseWhatsApp):
	"""O PDF de cada convite, com o link `/convite/<código>` na legenda."""

	def test_pagador_recebe_tudo_ganha_um_pdf_por_convidado(self):
		convite = self._convite_pago(
			pagador_recebe=True,
			convidados=[{"nome": "Caio Bernardo"}, {"nome": "Dora Bernardo"}],
		)

		enviar_convites_whatsapp(convite.name)

		self.assertEqual(self.mock_midia.call_count, 2)
		for chamada, convidado in zip(self.mock_midia.call_args_list, convite.convidados, strict=True):
			numero, tipo, conteudo = chamada.args
			self.assertEqual(numero, TELEFONE_PAGADOR)
			self.assertEqual(tipo, "document")
			self.assertEqual(base64.b64decode(conteudo), PDF_FALSO)
			self.assertEqual(chamada.kwargs["mimetype"], "application/pdf")
			self.assertTrue(chamada.kwargs["nome_arquivo"].endswith(".pdf"))
			self.assertFalse(chamada.kwargs["enqueue"])
			self.assertEqual(chamada.kwargs["contexto"]["destinatario_tipo"], "Convidado de festa")
			self.assertEqual(chamada.kwargs["contexto"]["destinatario_nome"], convidado.nome)

			legenda = chamada.kwargs["caption"]
			self.assertIn(convidado.nome, legenda)
			self.assertIn(self.festa.nome_festa, legenda)
			self.assertIn(f"/convite/{convidado.token_link}", legenda)
			self.assertIn("4 últimos dígitos", legenda)

			estado = _whatsapp_do_convidado(convidado.name)
			self.assertEqual(estado.status_envio_whatsapp, "Enviado")
			self.assertTrue(estado.whatsapp_notificado_em)
		self.mock_texto.assert_not_called()

	def test_individual_manda_o_proprio_pdf_e_marca_quem_nao_tem_telefone(self):
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice Prado", "email": "alice@example.com", "telefone": "11911111111"},
				{"nome": "Bob Lima", "email": "bob@example.com", "telefone": "11922222222"},
				{"nome": "Carol Reis", "email": "carol@example.com"},  # sem telefone
			],
		)

		enviar_convites_whatsapp(convite.name)

		numeros = [c.args[0] for c in self.mock_midia.call_args_list]
		self.assertEqual(numeros, ["11911111111", "11922222222"])
		legenda_alice = self.mock_midia.call_args_list[0].kwargs["caption"]
		self.assertTrue(legenda_alice.startswith("Olá, Alice!"))
		self.assertIn("comprado em seu nome", legenda_alice)
		# Nada do pagador na mensagem do convidado.
		self.assertNotIn(TELEFONE_PAGADOR, legenda_alice)
		self.assertNotIn("caio@example.com", legenda_alice)

		carol = convite.convidados[2]
		self.assertEqual(_whatsapp_do_convidado(carol.name).status_envio_whatsapp, "Sem telefone")
		self.assertEqual(self.mock_pdf.call_count, 2)

	def test_falha_do_pdf_cai_para_texto_com_o_link(self):
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[{"nome": "Alice Prado", "email": "alice@example.com", "telefone": "11911111111"}],
		)
		self.mock_midia.side_effect = RuntimeError("arquivo grande demais")

		enviar_convites_whatsapp(convite.name)

		self.assertEqual(self.mock_texto.call_count, 1)
		numero, mensagem = self.mock_texto.call_args.args
		self.assertEqual(numero, "11911111111")
		alice = convite.convidados[0]
		self.assertIn(f"/convite/{alice.token_link}", mensagem)
		self.assertNotIn("deste PDF", mensagem)
		self.assertFalse(self.mock_texto.call_args.kwargs["enqueue"])

		estado = _whatsapp_do_convidado(alice.name)
		self.assertEqual(estado.status_envio_whatsapp, "Enviado")
		self.assertIn("só o link", estado.descricao_erro_whatsapp)

	def test_falha_na_geracao_do_pdf_tambem_cai_para_o_link(self):
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[{"nome": "Alice Prado", "email": "alice@example.com", "telefone": "11911111111"}],
		)
		self.mock_pdf.side_effect = OSError("wkhtmltopdf falhou")

		enviar_convites_whatsapp(convite.name)

		self.mock_midia.assert_not_called()
		self.assertEqual(self.mock_texto.call_count, 1)

	def test_falha_dupla_marca_erro_e_nao_interrompe_os_demais(self):
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice Prado", "email": "alice@example.com", "telefone": "11911111111"},
				{"nome": "Bob Lima", "email": "bob@example.com", "telefone": "11922222222"},
			],
		)

		def falha_para_alice(numero, *args, **kwargs):
			if numero == "11911111111":
				raise RuntimeError("Network down")

		self.mock_midia.side_effect = falha_para_alice
		self.mock_texto.side_effect = falha_para_alice

		enviar_convites_whatsapp(convite.name)

		alice, bob = convite.convidados
		estado_alice = _whatsapp_do_convidado(alice.name)
		self.assertEqual(estado_alice.status_envio_whatsapp, "Erro")
		self.assertIn("Network down", estado_alice.descricao_erro_whatsapp)
		self.assertFalse(estado_alice.whatsapp_notificado_em)
		self.assertEqual(_whatsapp_do_convidado(bob.name).status_envio_whatsapp, "Enviado")

	def test_numero_sem_whatsapp_nao_tenta_o_texto(self):
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[{"nome": "Alice Prado", "email": "alice@example.com", "telefone": "11911111111"}],
		)
		self.mock_midia.side_effect = WhatsAppNumberNotFoundError("não existe")

		enviar_convites_whatsapp(convite.name)

		self.mock_texto.assert_not_called()
		self.assertEqual(_whatsapp_do_convidado(convite.convidados[0].name).status_envio_whatsapp, "Erro")

	def test_whatsapp_desligado_para_tudo_sem_gerar_os_outros_pdfs(self):
		convite = self._convite_pago(
			pagador_recebe=True,
			convidados=[{"nome": "Caio Bernardo"}, {"nome": "Dora Bernardo"}, {"nome": "Eva Bernardo"}],
		)
		self.mock_midia.side_effect = WhatsAppConfigurationError("Integração desabilitada")

		enviar_convites_whatsapp(convite.name)

		self.assertEqual(self.mock_pdf.call_count, 1)
		self.mock_texto.assert_not_called()
		for convidado in convite.convidados:
			estado = _whatsapp_do_convidado(convidado.name)
			self.assertEqual(estado.status_envio_whatsapp, "Erro")
			self.assertIn("desabilitada", estado.descricao_erro_whatsapp)

	def test_idempotencia_e_reenvio_forcado(self):
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[{"nome": "Alice Prado", "email": "alice@example.com", "telefone": "11911111111"}],
		)

		enviar_convites_whatsapp(convite.name)
		enviar_convites_whatsapp(convite.name)
		self.assertEqual(self.mock_midia.call_count, 1)

		enviar_convites_whatsapp(convite.name, forcar=True)
		self.assertEqual(self.mock_midia.call_count, 2)

	def test_reenvio_de_um_convidado_so(self):
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[
				{"nome": "Alice Prado", "email": "alice@example.com", "telefone": "11911111111"},
				{"nome": "Bob Lima", "email": "bob@example.com", "telefone": "11922222222"},
			],
		)
		enviar_convites_whatsapp(convite.name)
		self.mock_midia.reset_mock()

		enviar_convites_whatsapp(convite.name, convidado_row_name=convite.convidados[1].name)

		self.assertEqual([c.args[0] for c in self.mock_midia.call_args_list], ["11922222222"])

	def test_convidado_antigo_ganha_codigo_no_envio(self):
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[{"nome": "Alice Prado", "email": "alice@example.com", "telefone": "11911111111"}],
		)
		alice = convite.convidados[0]
		frappe.db.set_value("Convidado Convite Festa", alice.name, "token_link", None)

		enviar_convites_whatsapp(convite.name)

		token = _whatsapp_do_convidado(alice.name).token_link
		self.assertTrue(token)
		self.assertIn(f"/convite/{token}", self.mock_midia.call_args.kwargs["caption"])

	def test_nao_pago_e_presencial_nao_enviam(self):
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[{"nome": "Alice Prado", "email": "alice@example.com", "telefone": "11911111111"}],
			pagar=False,
		)
		presencial = frappe.get_doc(
			{
				"doctype": "Convite Festa",
				"festa": self.festa.name,
				"nome_pagador": "Pagador na Porta",
				"telefone_pagador": "11955554321",
				"presencial": 1,
				"meio_pagamento": "Dinheiro",
				"pagador_recebe_qr_codes": 1,
				"itens": [{"eh_convite": 1, "opcao_convite": self.opcao.name, "quantidade": 1}],
				"convidados": [{"nome": "Carlos Dias"}],
			}
		).insert(ignore_permissions=True)

		enviar_convites_whatsapp(convite.name)
		enviar_convites_whatsapp(presencial.name)

		self.mock_midia.assert_not_called()
		self.mock_texto.assert_not_called()

	def test_nao_salva_o_convite(self):
		"""Salvar o pedido reescreveria os valores dos itens a partir da Opção atual."""
		convite = self._convite_pago(
			pagador_recebe=False,
			convidados=[{"nome": "Alice Prado", "email": "alice@example.com", "telefone": "11911111111"}],
		)

		with patch.object(ConviteFesta, "save") as salvar:
			enviar_convites_whatsapp(convite.name)

		salvar.assert_not_called()
		self.assertEqual(self.mock_midia.call_count, 1)
