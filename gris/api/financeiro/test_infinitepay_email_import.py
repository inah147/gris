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

	def __init__(self, email_account=None, remetente_contem=None, assunto_contem=None):
		self.email_account = email_account
		self.remetente_contem = remetente_contem
		self.assunto_contem = assunto_contem


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


class TestBuscaClassificacaoEMarcador(FrappeTestCase):
	def _criar_email_account(self, prefixo):
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
		conta = self._criar_email_account("fechamento-teste-busca")
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

	def test_anexos_de_uma_comunicacao_classifica_os_tres_e_ignora_o_resto(self):
		conta = self._criar_email_account("fechamento-teste-anexos")
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

		anexos = job._anexos_de_uma_comunicacao(comunicacao.name)

		self.assertEqual(set(anexos.keys()), {TIPO_EXTRATO, TIPO_VENDAS, TIPO_RECEBIMENTOS})
		for caminho in anexos.values():
			self.assertTrue(os.path.exists(caminho))

	def test_marcador_de_importado(self):
		conta = self._criar_email_account("fechamento-teste-marcador")
		comunicacao = self._criar_comunicacao(
			conta, "contato@infinitepay.com.br", "Fechamento de agosto", datetime.datetime(2026, 8, 7, 9, 0)
		)

		self.assertFalse(job._ja_importada(comunicacao.name))
		job._marcar_importada(comunicacao.name, "resumo de teste")
		self.assertTrue(job._ja_importada(comunicacao.name))


class TestRunInfinitepayEmailImport(FrappeTestCase):
	"""Roda o job de ponta a ponta, fixando "hoje" para não depender do relógio real.

	`run_infinitepay_email_import` dá um `frappe.db.commit()` explícito ao marcar
	cada e-mail como importado (para o marcador sobreviver a um rollback do job) —
	o que, sem cuidado, também comitaria os dados do teste. Por isso todo teste
	aqui roda com `frappe.db.commit` neutralizado, preservando o rollback
	automático do `FrappeTestCase` no fim do teste.
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

	def _criar_comunicacao(self, conta, assunto, quando, anexos=()):
		comunicacao = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_medium": "Email",
				"sent_or_received": "Received",
				"status": "Open",
				"email_account": conta,
				"sender": "contato@infinitepay.com.br",
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

	def test_sem_anexos_completos_nao_marca_como_importado(self):
		conta = self._criar_email_account("fechamento-run-incompleto")
		self._configurar(email_account=conta, remetente_contem=None, assunto_contem=None)
		comunicacao = self._criar_comunicacao(
			conta, "Fechamento de agosto", datetime.datetime(2026, 8, 7, 9, 0)
		)

		# 07/08/2026 é o 5º dia útil de agosto/2026 (ver TestDiaUtil).
		with patch.object(job, "getdate", return_value=datetime.date(2026, 8, 7)):
			job.run_infinitepay_email_import()

		self.assertFalse(job._ja_importada(comunicacao.name))

	def test_com_os_tres_anexos_insere_e_marca_como_importado(self):
		conta = self._criar_email_account("fechamento-run-completo")
		self._configurar(email_account=conta, remetente_contem=None, assunto_contem=None)
		antes = {
			dt: frappe.db.count(dt)
			for dt in (
				"Transacao Infinitepay extrato",
				"Transacao Infinitepay vendas",
				"Transacao Infinitepay recebimento",
			)
		}
		comunicacao = self._criar_comunicacao(
			conta,
			"Fechamento de agosto",
			datetime.datetime(2026, 8, 7, 9, 0),
			anexos=[
				("extrato.ofx", EXTRATO_HTML),
				("vendas.xml", VENDAS_XML),
				("recebimentos.xml", RECEBIMENTOS_XML),
			],
		)

		with patch.object(job, "getdate", return_value=datetime.date(2026, 8, 7)):
			job.run_infinitepay_email_import()

		self.assertTrue(job._ja_importada(comunicacao.name))
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

		# Rodar de novo não reabre o mesmo e-mail (já está marcado) — nada muda.
		with patch.object(job, "getdate", return_value=datetime.date(2026, 8, 20)):
			job.run_infinitepay_email_import()
		self.assertEqual(
			frappe.db.count("Transacao Infinitepay extrato") - antes["Transacao Infinitepay extrato"], 4
		)

	def test_dois_emails_pendentes_no_mesmo_dia_sao_importados_e_marcados_juntos(self):
		conta = self._criar_email_account("fechamento-run-dois-emails")
		self._configurar(email_account=conta, remetente_contem=None, assunto_contem=None)
		anexos = [
			("extrato.ofx", EXTRATO_HTML),
			("vendas.xml", VENDAS_XML),
			("recebimentos.xml", RECEBIMENTOS_XML),
		]
		# Simula um reenvio: dois e-mails de fechamento chegaram sem serem
		# processados ainda (ex.: a conta ficou sem configuração por alguns dias).
		primeiro = self._criar_comunicacao(
			conta, "Fechamento de agosto (1)", datetime.datetime(2026, 8, 7, 9, 0), anexos=anexos
		)
		segundo = self._criar_comunicacao(
			conta, "Fechamento de agosto (2)", datetime.datetime(2026, 8, 10, 9, 0), anexos=anexos
		)

		with patch.object(job, "getdate", return_value=datetime.date(2026, 8, 20)):
			job.run_infinitepay_email_import()

		self.assertTrue(job._ja_importada(primeiro.name))
		self.assertTrue(job._ja_importada(segundo.name))
