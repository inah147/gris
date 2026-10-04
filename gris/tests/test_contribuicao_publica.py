"""Página pública /contribuicao/<código> e o link da InfinitePay que ela entrega."""

import datetime
import hashlib
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro import cobranca_contribuicao as cobranca
from gris.api.financeiro import contribuicao_publica as publica
from gris.api.financeiro import contribuicao_token as tokens
from gris.financeiro.doctype.cobranca_infinitepay import cobranca_infinitepay as cobranca_doctype

HOJE = datetime.date(2026, 10, 14)
CPF = "99000000501"


def _apagar(doctype: str, filtros: dict) -> None:
	for nome in frappe.get_all(doctype, filters=filtros, pluck="name"):
		frappe.delete_doc(doctype, nome, force=True, ignore_permissions=True)


class _BaseContribuicaoPublica(FrappeTestCase):
	"""Associado, pagamentos e InfinitePay simulada, sem testes próprios."""

	def setUp(self):
		nome = hashlib.md5(CPF.encode("utf-8")).hexdigest()
		if not frappe.db.exists("Associado", nome):
			frappe.get_doc(
				{
					"doctype": "Associado",
					"cpf": CPF,
					"nome_completo": "Beneficiário Público",
					"data_de_nascimento": "2015-01-01",
					"categoria": "Beneficiário",
					"status_no_grupo": "Ativo",
					"status_cobranca": "Ativo",
					"valor_contribuicao": 60.0,
					"inicio_do_pagamento": "2026-01-01",
					"telefone_cobranca": "11999990000",
				}
			).insert(ignore_permissions=True)
		self.associado = nome
		_apagar("Cobranca Infinitepay", {"associado": self.associado})
		_apagar("Pagamento Contribuicao Mensal", {"associado": self.associado})
		frappe.db.set_single_value("Configuracao infinitepay", "handle", "grupo-teste")
		frappe.db.set_single_value(
			"Configuracoes Contribuicao Mensal",
			{"valor_base": 60, "valor_atraso": 70, "dia_vencimento": 10},
		)
		self.token = tokens.obter_token(self.associado)

	def _pagamento(self, mes: str, status: str, valor: float = 60.0, **campos) -> None:
		frappe.get_doc(
			{
				"doctype": "Pagamento Contribuicao Mensal",
				"associado": self.associado,
				"mes_de_referencia": f"{mes}-01",
				"status": status,
				"valor": valor,
				**campos,
			}
		).insert(ignore_permissions=True)

	def _sem_rede(self, link: str = "https://pag.exemplo/teste"):
		resposta = mock.Mock()
		resposta.json.return_value = {"checkout_url": link}
		resposta.raise_for_status.return_value = None
		return mock.patch.object(cobranca_doctype.requests, "post", return_value=resposta)


class TestContribuicaoPublica(_BaseContribuicaoPublica):
	# ── código ──────────────────────────────────────────────────────────────

	def test_token_e_fixo_e_so_muda_ao_regenerar(self):
		self.assertEqual(tokens.obter_token(self.associado), self.token)
		self.assertEqual(len(self.token), 32)
		self.assertEqual(tokens.associado_do_token(self.token), self.associado)

		with mock.patch.object(tokens.frappe, "get_roles", return_value=[tokens.ROLE_GESTOR]):
			novo = tokens.regenerar_token(self.associado)
		self.assertNotEqual(novo, self.token)
		self.assertIsNone(tokens.associado_do_token(self.token))
		self.assertEqual(tokens.associado_do_token(novo), self.associado)

	def test_regenerar_exige_gestor(self):
		with mock.patch.object(tokens.frappe, "get_roles", return_value=["Guest"]):
			with self.assertRaises(frappe.PermissionError):
				tokens.regenerar_token(self.associado)

	def test_codigo_invalido_nao_acha_ninguem(self):
		for ruim in (None, "", "abc", "x" * 32, self.token.upper() + "!", "' or 1=1 --"):
			self.assertIsNone(tokens.associado_do_token(ruim))
			self.assertIsNone(publica.montar_pagina(ruim, HOJE))

	# ── página ──────────────────────────────────────────────────────────────

	def test_pagina_em_aberto_dentro_do_prazo(self):
		self._pagamento("2026-10", "Em Aberto")
		pagina = publica.montar_pagina(self.token, datetime.date(2026, 10, 5))
		self.assertEqual(pagina["estado"], "em_aberto")
		self.assertEqual(pagina["total_pendente"], 60)
		self.assertEqual(pagina["vencimento"], datetime.date(2026, 10, 13))

	def test_pagina_vencida_mostra_o_acrescimo(self):
		self._pagamento("2026-09", "Atrasado", valor=70, acrescimo_atraso=10)
		self._pagamento("2026-10", "Em Aberto")
		pagina = publica.montar_pagina(self.token, HOJE)
		self.assertEqual(pagina["estado"], "vencido")
		self.assertEqual(pagina["total_pendente"], 130)
		self.assertEqual(pagina["acrescimo_pendente"], 10)
		self.assertEqual(pagina["meses_em_atraso"], 1)

	def test_pagina_tudo_pago_e_meses_nao_gerados_nao_aparecem(self):
		self._pagamento("2026-10", "Pago")
		pagina = publica.montar_pagina(self.token, HOJE)
		self.assertEqual(pagina["estado"], "pago")
		self.assertEqual([m["ym"] for m in pagina["meses"]], ["2026-10"])

	def test_meses_do_mais_recente_ao_mais_antigo(self):
		self._pagamento("2026-08", "Pago")
		self._pagamento("2026-10", "Em Aberto")
		pagina = publica.montar_pagina(self.token, HOJE)
		self.assertEqual([m["ym"] for m in pagina["meses"]], ["2026-10", "2026-08"])

	def test_pagina_nao_expoe_contato(self):
		self._pagamento("2026-10", "Em Aberto")
		texto = frappe.as_json(publica.montar_pagina(self.token, HOJE))
		for proibido in ("11999990000", CPF, "telefone", "email"):
			self.assertNotIn(proibido, texto)

	# ── pagamento ───────────────────────────────────────────────────────────

	def test_reaproveita_o_link_quando_nada_mudou(self):
		self._pagamento("2026-10", "Em Aberto")
		with self._sem_rede():
			primeira = cobranca.cobranca_vigente(self.associado, HOJE)
			segunda = cobranca.cobranca_vigente(self.associado, HOJE)
		self.assertFalse(primeira["reaproveitada"])
		self.assertTrue(segunda["reaproveitada"])
		self.assertEqual(primeira["name"], segunda["name"])

	def test_reemite_quando_o_valor_mudou_e_herda_os_carimbos(self):
		self._pagamento("2026-10", "Em Aberto")
		with self._sem_rede():
			primeira = cobranca.cobranca_vigente(self.associado, HOJE)
			frappe.db.set_value(
				"Cobranca Infinitepay",
				primeira["name"],
				{
					"origem": "Automática",
					"lembretes_enviados": 1,
					"ultimo_envio_whatsapp": "2026-10-01 09:00:00",
				},
			)
			frappe.db.set_value(
				"Pagamento Contribuicao Mensal",
				{"associado": self.associado, "mes_de_referencia": "2026-10-01"},
				{"valor": 70, "status": "Atrasado"},
			)
			segunda = cobranca.cobranca_vigente(self.associado, HOJE)

		self.assertFalse(segunda["reaproveitada"])
		self.assertNotEqual(primeira["name"], segunda["name"])
		self.assertEqual(
			frappe.db.get_value("Cobranca Infinitepay", primeira["name"], "status"), "Substituída"
		)
		nova = frappe.db.get_value(
			"Cobranca Infinitepay",
			segunda["name"],
			["origem", "lembretes_enviados", "ultimo_envio_whatsapp", "redirect_url", "status"],
			as_dict=True,
		)
		self.assertEqual(nova.origem, "Automática")
		self.assertEqual(nova.lembretes_enviados, 1)
		self.assertIsNotNone(nova.ultimo_envio_whatsapp)
		self.assertEqual(nova.status, "Pendente")
		self.assertTrue(nova.redirect_url.endswith(f"/contribuicao/{self.token}"))

	def test_sem_nada_em_aberto_nao_emite(self):
		self._pagamento("2026-10", "Pago")
		self.assertIsNone(cobranca.cobranca_vigente(self.associado, HOJE))
		self.assertEqual(frappe.db.count("Cobranca Infinitepay", {"associado": self.associado}), 0)

	def test_endpoint_so_devolve_o_link(self):
		self._pagamento("2026-10", "Em Aberto")
		with self._sem_rede("https://pag.exemplo/abc"):
			resposta = publica.iniciar_pagamento(self.token)
		self.assertEqual(resposta, {"link_pagamento": "https://pag.exemplo/abc"})

	def test_endpoint_com_codigo_invalido_da_404(self):
		with self.assertRaises(frappe.PageDoesNotExistError):
			publica.iniciar_pagamento("0" * 32)

	def test_headers_de_protecao_so_na_rota_publica(self):
		resposta = mock.Mock(headers={})
		publica.proteger_resposta(resposta, mock.Mock(path=f"/contribuicao/{self.token}"))
		self.assertEqual(resposta.headers["Referrer-Policy"], "no-referrer")
		outra = mock.Mock(headers={})
		publica.proteger_resposta(outra, mock.Mock(path="/inicio"))
		self.assertEqual(outra.headers, {})


class TestComprovante(_BaseContribuicaoPublica):
	"""Confirmação por WhatsApp e comprovante na página, para quem pagou pelo link."""

	def _cobranca_paga(self, receipt_url: str = "https://recibo.infinitepay.io/abc") -> str:
		self._pagamento("2026-10", "Em Aberto")
		with self._sem_rede():
			emitida = cobranca.cobranca_vigente(self.associado, HOJE)
		doc = frappe.get_doc("Cobranca Infinitepay", emitida["name"])
		doc.status = "Pago"
		doc.paid_amount = 6000
		doc.receipt_url = receipt_url
		with self._sem_rede():
			doc.save(ignore_permissions=True)
		return doc.name

	def test_baixa_agenda_a_confirmacao_depois_do_commit(self):
		self._pagamento("2026-10", "Em Aberto")
		with self._sem_rede():
			emitida = cobranca.cobranca_vigente(self.associado, HOJE)
		doc = frappe.get_doc("Cobranca Infinitepay", emitida["name"])
		doc.status = "Pago"
		doc.paid_amount = 6000
		with mock.patch.object(cobranca.frappe, "enqueue") as enfileirar, self._sem_rede():
			doc.save(ignore_permissions=True)
		enfileirar.assert_called_once()
		self.assertTrue(enfileirar.call_args.kwargs["enqueue_after_commit"])
		self.assertEqual(enfileirar.call_args.kwargs["cobranca"], doc.name)

	def test_falha_ao_agendar_nao_derruba_a_baixa(self):
		self._pagamento("2026-10", "Em Aberto")
		with self._sem_rede():
			emitida = cobranca.cobranca_vigente(self.associado, HOJE)
		doc = frappe.get_doc("Cobranca Infinitepay", emitida["name"])
		doc.status = "Pago"
		doc.paid_amount = 6000
		with (
			mock.patch.object(cobranca.frappe, "enqueue", side_effect=RuntimeError("fila fora")),
			mock.patch.object(cobranca.frappe, "log_error"),
			self._sem_rede(),
		):
			doc.save(ignore_permissions=True)
		self.assertTrue(frappe.db.get_value("Cobranca Infinitepay", doc.name, "transacao_extrato"))

	def test_confirmacao_sai_uma_vez_so(self):
		nome = self._cobranca_paga()
		with mock.patch("gris.utils.whatsapp.enviar_texto") as enviar:
			primeira = cobranca.enviar_confirmacao(nome)
			segunda = cobranca.enviar_confirmacao(nome)
		self.assertTrue(primeira["enviado"])
		self.assertFalse(segunda["enviado"])
		enviar.assert_called_once()
		texto = enviar.call_args.args[1]
		self.assertIn(f"/contribuicao/{self.token}", texto)
		self.assertNotIn("infinitepay", texto.lower())
		self.assertTrue(frappe.db.get_value("Cobranca Infinitepay", nome, "comprovante_enviado_em"))

	def test_whatsapp_que_falha_nao_marca_como_enviada(self):
		from gris.utils.whatsapp_errors import WhatsAppRequestError

		nome = self._cobranca_paga()
		with (
			mock.patch("gris.utils.whatsapp.enviar_texto", side_effect=WhatsAppRequestError("fora")),
			mock.patch.object(cobranca.frappe, "log_error"),
		):
			resultado = cobranca.enviar_confirmacao(nome)
		self.assertFalse(resultado["enviado"])
		self.assertFalse(frappe.db.get_value("Cobranca Infinitepay", nome, "comprovante_enviado_em"))

	def test_pagina_mostra_comprovante_do_mes_pago_por_link(self):
		self._cobranca_paga("https://recibo.infinitepay.io/abc")
		pagina = publica.montar_pagina(self.token, HOJE)
		self.assertEqual(pagina["estado"], "pago")
		self.assertEqual(pagina["comprovante"], "https://recibo.infinitepay.io/abc")
		self.assertEqual(pagina["meses"][0]["comprovante"], "https://recibo.infinitepay.io/abc")

	def test_receipt_url_inseguro_nao_vira_link(self):
		self._cobranca_paga("https://evil.example/recibo")
		pagina = publica.montar_pagina(self.token, HOJE)
		self.assertIsNone(pagina["comprovante"])
		self.assertIsNone(pagina["meses"][0]["comprovante"])

	def test_mes_pago_por_outro_meio_nao_tem_comprovante(self):
		self._pagamento("2026-10", "Pago")
		pagina = publica.montar_pagina(self.token, HOJE)
		self.assertIsNone(pagina["meses"][0]["comprovante"])
