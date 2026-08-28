# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# See license.txt

"""Testes do registro de execucoes de jobs (gris/utils/job_logger.py)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.utils import job_logger

METODO_DO_APP = "gris.tests.job_de_teste.rodar"
METODO_AGENDADO = "gris.api.calendario.sync_feriados.sync_feriados"
METODO_DE_FORA = "frappe.email.queue.flush"


class TestJobLogger(FrappeTestCase):
	def setUp(self):
		frappe.db.delete(job_logger.DOCTYPE, {"metodo": ["in", [METODO_DO_APP, METODO_AGENDADO]]})
		setattr(frappe.local, job_logger.ATRIBUTO_LOCAL, None)

	def tearDown(self):
		setattr(frappe.local, job_logger.ATRIBUTO_LOCAL, None)

	def _ultimo_log(self, metodo):
		name = frappe.db.get_value(job_logger.DOCTYPE, {"metodo": metodo}, "name", order_by="creation desc")
		self.assertIsNotNone(name, f"Nenhum log gravado para {metodo}")
		return frappe.get_doc(job_logger.DOCTYPE, name)

	# ------------------------------------------------------------- hooks do job

	def test_job_enfileirado_com_sucesso_grava_linha_do_tempo(self):
		job_logger.before_job(method=METODO_DO_APP, kwargs={"associado": "ASSOC-1"})
		logger = job_logger.obter_logger("teste_job")
		logger.info("Processando 2 associados")
		job_logger.metrica("criados", 2)
		job_logger.definir_resumo("2 associados criados")
		job_logger.after_job(method=METODO_DO_APP, kwargs={}, result=None)

		log = self._ultimo_log(METODO_DO_APP)
		self.assertEqual(log.status, job_logger.STATUS_SUCESSO)
		self.assertEqual(log.origem, job_logger.ORIGEM_FILA)
		self.assertEqual(log.resumo, "2 associados criados")
		self.assertEqual(log.get_metricas(), {"criados": 2})
		self.assertIn("Processando 2 associados", json.dumps(log.get_eventos(), ensure_ascii=False))
		self.assertIsNotNone(log.fim)

	def test_aviso_no_job_muda_o_status(self):
		job_logger.before_job(method=METODO_DO_APP, kwargs={})
		job_logger.obter_logger("teste_job").warning("Associado sem telefone")
		job_logger.after_job(method=METODO_DO_APP, kwargs={}, result=None)

		log = self._ultimo_log(METODO_DO_APP)
		self.assertEqual(log.status, job_logger.STATUS_SUCESSO_COM_AVISOS)
		self.assertEqual(log.total_avisos, 1)

	def test_erro_registrado_pelo_job_marca_conclusao_com_erros(self):
		job_logger.before_job(method=METODO_DO_APP, kwargs={})
		job_logger.obter_logger("teste_job").error("Falhou o envio para ASSOC-9")
		job_logger.after_job(method=METODO_DO_APP, kwargs={}, result=None)

		log = self._ultimo_log(METODO_DO_APP)
		self.assertEqual(log.status, job_logger.STATUS_CONCLUIDO_COM_ERROS)
		self.assertEqual(log.total_erros, 1)

	def test_excecao_em_curso_vira_status_de_erro_com_traceback(self):
		job_logger.before_job(method=METODO_DO_APP, kwargs={})
		try:
			raise ValueError("estourou")
		except ValueError:
			# after_job roda dentro do `finally` do Frappe, com a excecao ativa.
			job_logger.after_job(method=METODO_DO_APP, kwargs={}, result=None)

		log = self._ultimo_log(METODO_DO_APP)
		self.assertEqual(log.status, job_logger.STATUS_ERRO)
		self.assertIn("ValueError", log.erro)
		self.assertIn("estourou", log.erro)

	def test_job_agendado_resolve_o_metodo_real_e_a_origem(self):
		job_logger.before_job(
			method=job_logger.METODO_JOB_AGENDADO,
			kwargs={"job_type": METODO_AGENDADO},
		)
		job_logger.after_job(method=job_logger.METODO_JOB_AGENDADO, kwargs={}, result=None)

		log = self._ultimo_log(METODO_AGENDADO)
		self.assertEqual(log.origem, job_logger.ORIGEM_AGENDADO)
		self.assertEqual(log.job, "Sincronização de feriados")

	def test_falha_de_job_agendado_e_lida_do_scheduled_job_log(self):
		# `run_scheduled_job` engole a excecao, entao a falha so aparece no log do
		# scheduler — o `after_job` precisa buscar o status por la.
		nome_do_tipo = frappe.db.get_value("Scheduled Job Type", {"method": METODO_AGENDADO}, "name")
		self.assertIsNotNone(nome_do_tipo, "Scheduled Job Type do job de feriados nao encontrado")

		job_logger.before_job(
			method=job_logger.METODO_JOB_AGENDADO,
			kwargs={"job_type": METODO_AGENDADO},
		)
		frappe.get_doc(
			{
				"doctype": "Scheduled Job Log",
				"scheduled_job_type": nome_do_tipo,
				"status": "Failed",
				"details": "Traceback: a API de feriados respondeu 500",
			}
		).insert(ignore_permissions=True)
		job_logger.after_job(method=job_logger.METODO_JOB_AGENDADO, kwargs={}, result=None)

		log = self._ultimo_log(METODO_AGENDADO)
		self.assertEqual(log.status, job_logger.STATUS_ERRO)
		self.assertIn("respondeu 500", log.erro)

	def test_retorno_do_job_vira_metrica_e_resumo(self):
		job_logger.before_job(method=METODO_DO_APP, kwargs={})
		job_logger.after_job(method=METODO_DO_APP, kwargs={}, result={"atualizadas": 4})

		log = self._ultimo_log(METODO_DO_APP)
		self.assertEqual(log.get_metricas(), {"atualizadas": 4})
		self.assertIn("atualizadas: 4", log.resumo)

	# ----------------------------------------------------------------- ruido

	def test_job_de_fora_do_app_so_e_gravado_quando_falha(self):
		frappe.db.delete(job_logger.DOCTYPE, {"metodo": METODO_DE_FORA})

		job_logger.before_job(method=METODO_DE_FORA, kwargs={})
		job_logger.after_job(method=METODO_DE_FORA, kwargs={}, result=None)
		self.assertFalse(frappe.db.exists(job_logger.DOCTYPE, {"metodo": METODO_DE_FORA}))

		job_logger.before_job(method=METODO_DE_FORA, kwargs={})
		try:
			raise RuntimeError("falha do framework")
		except RuntimeError:
			job_logger.after_job(method=METODO_DE_FORA, kwargs={}, result=None)

		log = self._ultimo_log(METODO_DE_FORA)
		self.assertEqual(log.status, job_logger.STATUS_ERRO)
		frappe.db.delete(job_logger.DOCTYPE, {"metodo": METODO_DE_FORA})

	# ------------------------------------------------------------ seguranca

	def test_parametros_sensiveis_sao_mascarados(self):
		job_logger.before_job(
			method=METODO_DO_APP,
			kwargs={"usuario": "maria", "api_token": "abc123", "senha": "x"},
		)
		job_logger.after_job(method=METODO_DO_APP, kwargs={}, result=None)

		log = self._ultimo_log(METODO_DO_APP)
		self.assertIn('"usuario": "maria"', log.parametros)
		self.assertNotIn("abc123", log.parametros)
		self.assertIn('"api_token": "***"', log.parametros)

	# ------------------------------------------------------------- utilitarios

	def test_logger_do_job_nao_duplica_eventos(self):
		job_logger.before_job(method=METODO_DO_APP, kwargs={})
		job_logger.obter_logger("teste_job").error("mensagem unica")
		execucao = job_logger.execucao_atual()
		mensagens = [evento["mensagem"] for evento in execucao.eventos]
		job_logger.after_job(method=METODO_DO_APP, kwargs={}, result=None)

		self.assertEqual(mensagens.count("mensagem unica"), 1)

	def test_logger_do_job_aceita_interpolacao_do_logging(self):
		job_logger.before_job(method=METODO_DO_APP, kwargs={})
		job_logger.obter_logger("teste_job").info("associado=%s drive=%s", "ASSOC-1", "DRV-2")
		job_logger.after_job(method=METODO_DO_APP, kwargs={}, result=None)

		log = self._ultimo_log(METODO_DO_APP)
		self.assertIn("associado=ASSOC-1 drive=DRV-2", json.dumps(log.get_eventos()))

	def test_limite_de_eventos_trunca_e_avisa(self):
		job_logger.before_job(method=METODO_DO_APP, kwargs={})
		execucao = job_logger.execucao_atual()
		for indice in range(job_logger.LIMITE_DE_EVENTOS + 5):
			execucao.registrar(f"evento {indice}")
		job_logger.after_job(method=METODO_DO_APP, kwargs={}, result=None)

		log = self._ultimo_log(METODO_DO_APP)
		eventos = log.get_eventos()
		self.assertEqual(len(eventos), job_logger.LIMITE_DE_EVENTOS + 1)
		self.assertIn("não foram gravados", eventos[-1]["mensagem"])

	def test_funcoes_de_registro_sao_no_op_fora_de_um_job(self):
		setattr(frappe.local, job_logger.ATRIBUTO_LOCAL, None)

		job_logger.registrar("nada acontece")
		job_logger.metrica("nada")
		job_logger.definir_resumo("nada")

		self.assertIsNone(job_logger.execucao_atual())

	# --------------------------------------------------- gerenciador de contexto

	def test_registrar_execucao_grava_sucesso(self):
		with job_logger.registrar_execucao(METODO_DO_APP, rotulo="Job de teste") as execucao:
			execucao.registrar("passo 1")
			execucao.metrica("processados", 3)

		log = self._ultimo_log(METODO_DO_APP)
		self.assertEqual(log.status, job_logger.STATUS_SUCESSO)
		self.assertEqual(log.origem, job_logger.ORIGEM_MANUAL)
		self.assertEqual(log.job, "Job de teste")
		self.assertEqual(log.get_metricas(), {"processados": 3})

	def test_registrar_execucao_grava_erro_e_repropaga(self):
		with self.assertRaises(ValueError):
			with job_logger.registrar_execucao(METODO_DO_APP):
				raise ValueError("quebrou")

		log = self._ultimo_log(METODO_DO_APP)
		self.assertEqual(log.status, job_logger.STATUS_ERRO)
		self.assertIn("quebrou", log.erro)
		self.assertIsNone(job_logger.execucao_atual())

	def test_registrar_execucao_nao_duplica_log_aninhado(self):
		job_logger.before_job(method=METODO_DO_APP, kwargs={})
		with job_logger.registrar_execucao(METODO_DO_APP) as execucao:
			self.assertIs(execucao, job_logger.execucao_atual())
		job_logger.after_job(method=METODO_DO_APP, kwargs={}, result=None)

		total = frappe.db.count(job_logger.DOCTYPE, {"metodo": METODO_DO_APP})
		self.assertEqual(total, 1)

	def test_rotulo_derivado_quando_o_metodo_nao_esta_mapeado(self):
		self.assertEqual(job_logger.rotulo_do_metodo(METODO_DO_APP), "Rodar")
		self.assertEqual(
			job_logger.rotulo_do_metodo(METODO_AGENDADO),
			"Sincronização de feriados",
		)
