# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt
"""Link público do convite (`/convite/<código>`) e a conferência dos 4 dígitos."""

import base64
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from gris.api.festas import convite_publico
from gris.festas.doctype.compra_festa.test_compra_festa import _nova_festa
from gris.festas.doctype.convite_festa.test_convite_envio import (
	_convite,
	_marcar_cobranca_paga,
	_opcao,
)


class TestConvitePublico(FrappeTestCase):
	def setUp(self):
		link_patcher = patch(
			"gris.financeiro.doctype.cobranca_infinitepay.cobranca_infinitepay.CobrancaInfinitepay._criar_link_pagamento",
			lambda self: None,
		)
		link_patcher.start()
		self.addCleanup(link_patcher.stop)

		self.festa = _nova_festa()
		self.opcao = _opcao(self.festa.name)

	def tearDown(self):
		frappe.db.rollback()

	def _convite_pago(self, convidados=None, *, pagar=True):
		convite = _convite(
			self.festa.name,
			self.opcao.name,
			pagador_recebe=False,
			convidados=convidados
			or [{"nome": "Ana Souza", "email": "ana@example.com", "telefone": "(11) 97777-1234"}],
		)
		if pagar:
			_marcar_cobranca_paga(convite.cobranca_infinitepay)
		convite.reload()
		return convite

	def _erro_de(self, funcao, *args, **kwargs):
		with self.assertRaises(frappe.PermissionError) as ctx:
			funcao(*args, **kwargs)
		return str(ctx.exception)

	# ---------- código ----------

	def test_codigo_nasce_com_o_convidado_e_e_unico(self):
		convite = self._convite_pago(
			[
				{"nome": "Ana Souza", "email": "ana@example.com", "telefone": "11977771234"},
				{"nome": "Bia Lima", "email": "bia@example.com", "telefone": "11966665678"},
			]
		)
		tokens = [c.token_link for c in convite.convidados]

		for token in tokens:
			self.assertTrue(convite_publico.token_valido(token))
		self.assertEqual(len(set(tokens)), 2)
		self.assertNotIn(convite.convidados[0].qr_code_payload, tokens)
		self.assertEqual(convite_publico.obter_token_link(convite.convidados[0].name), tokens[0])

	def test_codigo_gerado_sob_demanda_para_convidado_antigo(self):
		"""Convidados de antes do link não têm código: ele nasce no primeiro envio."""
		row = self._convite_pago().convidados[0]
		frappe.db.set_value("Convidado Convite Festa", row.name, "token_link", None)

		token = convite_publico.obter_token_link(row.name)

		self.assertTrue(convite_publico.token_valido(token))
		self.assertEqual(frappe.db.get_value("Convidado Convite Festa", row.name, "token_link"), token)
		self.assertEqual(convite_publico.obter_token_link(row.name), token)

	def test_url_aponta_para_a_rota_publica(self):
		row = self._convite_pago().convidados[0]

		self.assertTrue(convite_publico.url_convite(row.name).endswith(f"/convite/{row.token_link}"))

	# ---------- quando a página existe ----------

	def test_convite_pago_com_telefone_abre(self):
		row = self._convite_pago().convidados[0]

		dados = convite_publico.carregar_convite(row.token_link)

		self.assertIsNotNone(dados)
		self.assertEqual(dados.convidado.name, row.name)
		self.assertFalse(dados.expirado)

	def test_codigo_malformado_ou_inexistente_nao_abre(self):
		self._convite_pago()
		for token in (None, "", "abc", "../../etc/passwd", "A" * 32, frappe.generate_hash(length=32)):
			self.assertIsNone(convite_publico.carregar_convite(token), token)

	def test_pedido_nao_pago_nao_abre(self):
		row = self._convite_pago(pagar=False).convidados[0]

		self.assertIsNone(convite_publico.carregar_convite(row.token_link))

	def test_convidado_sem_telefone_nao_abre(self):
		"""Sem telefone não há dígitos a conferir, e o convite nem foi pelo WhatsApp."""
		row = self._convite_pago([{"nome": "Ana Souza", "email": "ana@example.com"}]).convidados[0]

		self.assertIsNone(convite_publico.carregar_convite(row.token_link))

	def test_venda_presencial_nao_abre(self):
		convite = frappe.get_doc(
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

		self.assertIsNone(convite_publico.carregar_convite(convite.convidados[0].token_link))

	def test_festa_que_ja_passou_expira(self):
		row = self._convite_pago().convidados[0]
		frappe.db.set_value("Festa", self.festa.name, "data", add_days(today(), -2))

		dados = convite_publico.carregar_convite(row.token_link)

		self.assertTrue(dados.expirado)
		self.assertIn("convite", self._erro_de(convite_publico.abrir_convite, row.token_link, "1234"))

	def test_festa_de_ontem_ainda_abre(self):
		"""Quem sai depois da meia-noite ainda precisa do convite."""
		row = self._convite_pago().convidados[0]
		frappe.db.set_value("Festa", self.festa.name, "data", add_days(today(), -1))

		self.assertFalse(convite_publico.carregar_convite(row.token_link).expirado)

	# ---------- 4 dígitos ----------

	def test_digitos_certos_mostram_o_qr(self):
		row = self._convite_pago().convidados[0]

		resposta = convite_publico.abrir_convite(token=row.token_link, digitos="1234")

		self.assertEqual(resposta["nome"], "Ana Souza")
		self.assertEqual(resposta["festa"], self.festa.nome_festa)
		self.assertTrue(base64.b64decode(resposta["qr_png_b64"]).startswith(b"\x89PNG"))
		self.assertNotIn("telefone", resposta)
		self.assertNotIn("email", resposta)

	def test_falhas_dao_sempre_a_mesma_mensagem(self):
		"""Quem tenta não descobre se errou o código, os dígitos ou se o pedido não está pago."""
		pago = self._convite_pago().convidados[0]
		nao_pago = self._convite_pago(
			[{"nome": "Bia Lima", "email": "bia@example.com", "telefone": "11966665678"}], pagar=False
		).convidados[0]

		mensagens = {
			self._erro_de(convite_publico.abrir_convite, pago.token_link, "9999"),
			self._erro_de(convite_publico.abrir_convite, pago.token_link, "123"),
			self._erro_de(convite_publico.abrir_convite, pago.token_link, ""),
			self._erro_de(convite_publico.abrir_convite, frappe.generate_hash(length=32), "1234"),
			self._erro_de(convite_publico.abrir_convite, "abc", "1234"),
			self._erro_de(convite_publico.abrir_convite, nao_pago.token_link, "5678"),
		}

		self.assertEqual(len(mensagens), 1)

	def test_pdf_exige_os_mesmos_digitos(self):
		row = self._convite_pago().convidados[0]

		with patch("gris.festas.utils.convite_qr.gerar_pdf_convite", return_value=b"%PDF-1.4 teste"):
			self._erro_de(convite_publico.baixar_convite_pdf, row.token_link, "0000")
			convite_publico.baixar_convite_pdf(token=row.token_link, digitos="1234")

		self.assertEqual(frappe.local.response.type, "pdf")
		self.assertTrue(frappe.local.response.filecontent.startswith(b"%PDF"))
		self.assertTrue(frappe.local.response.filename.endswith(".pdf"))

	# ---------- cabeçalhos ----------

	def test_resposta_da_rota_publica_nao_vaza_o_codigo(self):
		for caminho in ("/convite/abc", "/api/method/gris.api.festas.convite_publico.abrir_convite"):
			resposta = MagicMock(headers={})
			convite_publico.proteger_resposta(resposta, MagicMock(path=caminho))

			self.assertEqual(resposta.headers["Referrer-Policy"], "no-referrer")
			self.assertEqual(resposta.headers["X-Robots-Tag"], "noindex, nofollow")
			self.assertEqual(resposta.headers["Cache-Control"], "no-store")

	def test_outras_rotas_nao_sao_tocadas(self):
		resposta = MagicMock(headers={})
		convite_publico.proteger_resposta(resposta, MagicMock(path="/festas/venda_convite"))

		self.assertEqual(resposta.headers, {})
