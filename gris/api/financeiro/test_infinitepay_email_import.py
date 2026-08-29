# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and Contributors
# See license.txt
"""Testes do job de importação do fechamento Infinitepay recebido por e-mail."""

import datetime
import os
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro import infinitepay_email_import as job
from gris.api.financeiro.infinitepay import TIPO_EXTRATO, TIPO_RECEBIMENTOS, TIPO_VENDAS
from gris.api.financeiro.test_infinitepay_import import (
	EXTRATO_HTML,
	RECEBIMENTOS_XML,
	VENDAS_XML,
)


class _ConfigFake:
	"""Dublê de 'Configuracao infinitepay', só com os campos que o job lê."""

	def __init__(
		self, email_account=None, remetente_contem=None, assunto_contem=None, ultimo_mes_importado=None
	):
		self.email_account = email_account
		self.remetente_contem = remetente_contem
		self.assunto_contem = assunto_contem
		self.ultimo_mes_importado = ultimo_mes_importado


class TestDiaUtil(FrappeTestCase):
	def test_fim_de_semana_nao_e_dia_util(self):
		sabado = datetime.date(2026, 8, 1)
		domingo = datetime.date(2026, 8, 2)
		self.assertFalse(job._e_dia_util(sabado))
		self.assertFalse(job._e_dia_util(domingo))

	def test_dia_de_semana_sem_feriado_e_dia_util(self):
		self.assertTrue(job._e_dia_util(datetime.date(2026, 8, 5)))

	def test_feriado_cadastrado_nao_e_dia_util(self):
		dia = datetime.date(2026, 8, 5)  # quarta-feira
		doc = frappe.get_doc(
			{
				"doctype": "Feriados",
				"id": "teste-feriado-infinitepay-email",
				"nome": "Feriado de teste",
				"data": dia,
				"tipo": "Municipal",
			}
		)
		doc.insert(ignore_permissions=True)
		self.assertFalse(job._e_dia_util(dia))

	def test_enesimo_dia_util_pula_fim_de_semana(self):
		# Agosto/2026: 01/08 sábado, 02/08 domingo -> dias úteis começam em 03/08 (2ª).
		mes = datetime.date(2026, 8, 15)
		self.assertEqual(job._enesimo_dia_util_do_mes(mes, 1), datetime.date(2026, 8, 3))
		self.assertEqual(job._enesimo_dia_util_do_mes(mes, 5), datetime.date(2026, 8, 7))


class TestDeveImportar(FrappeTestCase):
	def test_sem_email_account_configurada(self):
		deve, _mes, motivo = job._deve_importar(_ConfigFake(), datetime.date(2026, 8, 10))
		self.assertFalse(deve)
		self.assertIn("Conta de e-mail", motivo)

	def test_antes_do_quinto_dia_util(self):
		config = _ConfigFake(email_account="conta@example.com")
		# 03/08/2026 é o 1º dia útil de agosto/2026.
		deve, _mes, motivo = job._deve_importar(config, datetime.date(2026, 8, 3))
		self.assertFalse(deve)
		self.assertIn("dia útil", motivo)

	def test_mes_ja_importado(self):
		config = _ConfigFake(
			email_account="conta@example.com",
			ultimo_mes_importado=datetime.date(2026, 8, 1),
		)
		deve, mes, motivo = job._deve_importar(config, datetime.date(2026, 8, 20))
		self.assertFalse(deve)
		self.assertEqual(mes, datetime.date(2026, 8, 1))
		self.assertIn("já foi importado", motivo)

	def test_deve_importar_a_partir_do_quinto_dia_util(self):
		config = _ConfigFake(email_account="conta@example.com")
		# 07/08/2026 é o 5º dia útil de agosto/2026.
		deve, mes, motivo = job._deve_importar(config, datetime.date(2026, 8, 7))
		self.assertTrue(deve)
		self.assertIsNone(motivo)
		self.assertEqual(mes, datetime.date(2026, 8, 1))


class TestBuscaEClassificacaoDeAnexos(FrappeTestCase):
	def _criar_email_account(self, email_id):
		existente = frappe.db.exists("Email Account", {"email_id": email_id})
		if existente:
			return existente
		doc = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_account_name": email_id,
				"email_id": email_id,
				"enable_incoming": 0,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _criar_comunicacao(self, conta, remetente, assunto, quando, anexos=()):
		comunicacao = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Received",
				"status": "Open",
				"email_account": conta,
				"sender": remetente,
				"subject": assunto,
				"communication_date": quando,
				"content": "corpo do e-mail de teste",
			}
		)
		comunicacao.insert(ignore_permissions=True)
		for nome_arquivo, conteudo in anexos:
			frappe.get_doc(
				{
					"doctype": "File",
					"file_name": nome_arquivo,
					"attached_to_doctype": "Communication",
					"attached_to_name": comunicacao.name,
					"is_private": 1,
					"content": conteudo,
				}
			).insert(ignore_permissions=True)
		return comunicacao

	def test_busca_filtra_por_remetente_assunto_e_data(self):
		conta = self._criar_email_account("fechamento-teste-busca@example.com")
		config = _ConfigFake(email_account=conta, remetente_contem="infinitepay", assunto_contem="Fechamento")
		desde = datetime.date(2026, 8, 7)

		# Antes da data de corte: não entra.
		self._criar_comunicacao(
			conta, "contato@infinitepay.com.br", "Fechamento de julho", datetime.datetime(2026, 8, 6, 9, 0)
		)
		# Remetente não bate com o filtro: não entra.
		self._criar_comunicacao(
			conta, "outraempresa@example.com", "Fechamento de agosto", datetime.datetime(2026, 8, 7, 9, 0)
		)
		# Candidata válida.
		valida = self._criar_comunicacao(
			conta, "contato@infinitepay.com.br", "Fechamento de agosto", datetime.datetime(2026, 8, 7, 9, 0)
		)

		encontradas = job._buscar_comunicacoes_candidatas(config, desde)

		self.assertEqual([c["name"] for c in encontradas], [valida.name])

	def test_coleta_classifica_os_tres_anexos_e_ignora_o_resto(self):
		conta = self._criar_email_account("fechamento-teste-anexos@example.com")
		comunicacao = self._criar_comunicacao(
			conta,
			"contato@infinitepay.com.br",
			"Fechamento de agosto",
			datetime.datetime(2026, 8, 7, 9, 0),
			anexos=[
				("extrato.ofx", EXTRATO_HTML),
				("vendas.xml", VENDAS_XML),
				("recebimentos.xml", RECEBIMENTOS_XML),
				("assinatura.txt", "Atenciosamente, equipe Infinitepay"),
			],
		)

		anexos = job._coletar_anexos_classificados([{"name": comunicacao.name}])

		self.assertEqual(set(anexos.keys()), {TIPO_EXTRATO, TIPO_VENDAS, TIPO_RECEBIMENTOS})
		for caminho in anexos.values():
			self.assertTrue(os.path.exists(caminho))


class TestRunInfinitepayEmailImport(FrappeTestCase):
	"""Roda o job de ponta a ponta, fixando "hoje" para não depender do relógio real.

	`run_infinitepay_email_import` dá um `frappe.db.commit()` explícito ao marcar o
	mês como importado (para o marcador sobreviver a um rollback do job) — o que,
	sem cuidado, também comitaria os dados do teste. Por isso todo teste aqui roda
	com `frappe.db.commit` neutralizado, preservando o rollback automático do
	`FrappeTestCase` no fim do teste.
	"""

	def setUp(self):
		self._commit_patcher = patch.object(frappe.db, "commit", lambda: None)
		self._commit_patcher.start()
		self.addCleanup(self._commit_patcher.stop)

	def _criar_email_account(self, prefixo):
		# Nome único por chamada: evita colidir com sobras de execuções anteriores
		# (o commit explícito do job, neutralizado acima, existe justamente para
		# persistir de verdade fora dos testes — então pode haver sobra no banco).
		email_id = f"{prefixo}-{frappe.generate_hash(length=8)}@example.com"
		doc = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_account_name": email_id,
				"email_id": email_id,
				"enable_incoming": 0,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _configurar(self, **campos):
		config = frappe.get_single("Configuracao infinitepay")
		if not config.handle:
			config.handle = "grupo-teste"
		for campo, valor in campos.items():
			config.set(campo, valor)
		config.save(ignore_permissions=True)
		return config

	def test_sem_anexos_completos_nao_marca_o_mes_como_importado(self):
		conta = self._criar_email_account("fechamento-run-incompleto")
		self._configurar(
			email_account=conta, remetente_contem=None, assunto_contem=None, ultimo_mes_importado=None
		)

		frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Received",
				"status": "Open",
				"email_account": conta,
				"sender": "contato@infinitepay.com.br",
				"subject": "Fechamento de agosto",
				"communication_date": datetime.datetime(2026, 8, 7, 9, 0),
				"content": "corpo do e-mail de teste",
			}
		).insert(ignore_permissions=True)

		# 07/08/2026 é o 5º dia útil de agosto/2026 (ver TestDiaUtil).
		with patch.object(job, "getdate", return_value=datetime.date(2026, 8, 7)):
			job.run_infinitepay_email_import()

		config_final = frappe.get_single("Configuracao infinitepay")
		self.assertFalse(config_final.ultimo_mes_importado)

	def test_com_os_tres_anexos_insere_e_marca_o_mes_como_importado(self):
		conta = self._criar_email_account("fechamento-run-completo")
		self._configurar(
			email_account=conta, remetente_contem=None, assunto_contem=None, ultimo_mes_importado=None
		)
		antes = {
			dt: frappe.db.count(dt)
			for dt in (
				"Transacao Infinitepay extrato",
				"Transacao Infinitepay vendas",
				"Transacao Infinitepay recebimento",
			)
		}

		frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Received",
				"status": "Open",
				"email_account": conta,
				"sender": "contato@infinitepay.com.br",
				"subject": "Fechamento de agosto",
				"communication_date": datetime.datetime(2026, 8, 7, 9, 0),
				"content": "corpo do e-mail de teste",
			}
		).insert(ignore_permissions=True)
		comunicacao = frappe.get_last_doc("Communication", filters={"email_account": conta})
		for nome_arquivo, conteudo in (
			("extrato.ofx", EXTRATO_HTML),
			("vendas.xml", VENDAS_XML),
			("recebimentos.xml", RECEBIMENTOS_XML),
		):
			frappe.get_doc(
				{
					"doctype": "File",
					"file_name": nome_arquivo,
					"attached_to_doctype": "Communication",
					"attached_to_name": comunicacao.name,
					"is_private": 1,
					"content": conteudo,
				}
			).insert(ignore_permissions=True)

		with patch.object(job, "getdate", return_value=datetime.date(2026, 8, 7)):
			job.run_infinitepay_email_import()

		config_final = frappe.get_single("Configuracao infinitepay")
		self.assertEqual(frappe.utils.getdate(config_final.ultimo_mes_importado), datetime.date(2026, 8, 1))
		self.assertEqual(
			frappe.db.count("Transacao Infinitepay extrato") - antes["Transacao Infinitepay extrato"], 4
		)
		self.assertEqual(
			frappe.db.count("Transacao Infinitepay vendas") - antes["Transacao Infinitepay vendas"], 3
		)
		self.assertEqual(
			frappe.db.count("Transacao Infinitepay recebimento") - antes["Transacao Infinitepay recebimento"],
			1,
		)

		# Rodar de novo no mesmo mês não busca o e-mail outra vez (nada muda).
		with patch.object(job, "getdate", return_value=datetime.date(2026, 8, 20)):
			job.run_infinitepay_email_import()
		self.assertEqual(
			frappe.db.count("Transacao Infinitepay extrato") - antes["Transacao Infinitepay extrato"], 4
		)
