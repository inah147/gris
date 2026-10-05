# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# See license.txt

"""Testes da API do Monitor de Jobs (gris/api/monitoramento_jobs.py)."""

import json
from contextlib import contextmanager

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from gris.api import monitoramento_jobs
from gris.utils import job_logger

METODO_AGENDADO = "gris.api.calendario.sync_feriados.sync_feriados"
METODO_SOB_DEMANDA = "gris.tests.job_de_teste.rodar"


@contextmanager
def _sem_bypass_de_teste():
	"""Desliga o atalho que faz ``frappe.only_for`` nao checar nada em testes."""
	anterior = frappe.local.flags.in_test
	frappe.local.flags.in_test = False
	try:
		yield
	finally:
		frappe.local.flags.in_test = anterior


def _criar_log(metodo, status, inicio=None, **extras):
	doc = frappe.get_doc(
		{
			"doctype": job_logger.DOCTYPE,
			"job": job_logger.rotulo_do_metodo(metodo),
			"metodo": metodo,
			"origem": job_logger.ORIGEM_FILA,
			"status": status,
			"inicio": inicio or now_datetime(),
			"fim": now_datetime(),
			"duracao": 1.5,
			"eventos": json.dumps([{"nivel": "INFO", "mensagem": "rodou", "contexto": {}}]),
			"metricas": json.dumps({"criados": 1}),
			**extras,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestMonitoramentoJobs(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete(job_logger.DOCTYPE, {"metodo": ["in", [METODO_AGENDADO, METODO_SOB_DEMANDA]]})

	def tearDown(self):
		frappe.set_user("Administrator")

	# ------------------------------------------------------------------ leitura

	def test_resumo_geral_conta_execucoes_e_falhas(self):
		_criar_log(METODO_AGENDADO, job_logger.STATUS_SUCESSO)
		_criar_log(METODO_AGENDADO, job_logger.STATUS_ERRO, erro="boom")

		resumo = monitoramento_jobs.resumo_geral(dias=7)

		self.assertTrue(resumo["success"])
		self.assertGreaterEqual(resumo["execucoes"], 2)
		self.assertGreaterEqual(resumo["falhas"], 1)
		self.assertTrue(resumo["serie"])

	def test_listar_jobs_traz_agendados_e_sob_demanda(self):
		_criar_log(METODO_SOB_DEMANDA, job_logger.STATUS_SUCESSO)

		jobs = monitoramento_jobs.listar_jobs(dias=7, limite=monitoramento_jobs.LIMITE_MAXIMO)["jobs"]
		por_metodo = {job["metodo"]: job for job in jobs}

		self.assertIn(METODO_SOB_DEMANDA, por_metodo)
		self.assertFalse(por_metodo[METODO_SOB_DEMANDA]["agendado"])
		self.assertEqual(por_metodo[METODO_SOB_DEMANDA]["execucoes"], 1)
		self.assertIsNotNone(por_metodo[METODO_SOB_DEMANDA]["ultima"])

		self.assertIn(METODO_AGENDADO, por_metodo)
		self.assertTrue(por_metodo[METODO_AGENDADO]["agendado"])

	def test_listar_jobs_coloca_falhas_no_topo(self):
		_criar_log(METODO_SOB_DEMANDA, job_logger.STATUS_ERRO, erro="boom")
		_criar_log(METODO_AGENDADO, job_logger.STATUS_SUCESSO)

		jobs = monitoramento_jobs.listar_jobs(dias=7, limite=monitoramento_jobs.LIMITE_MAXIMO)["jobs"]

		self.assertEqual(jobs[0]["metodo"], METODO_SOB_DEMANDA)

	def test_listar_execucoes_filtra_por_metodo_e_por_erro(self):
		_criar_log(METODO_SOB_DEMANDA, job_logger.STATUS_SUCESSO)
		_criar_log(METODO_SOB_DEMANDA, job_logger.STATUS_ERRO, erro="boom")

		todas = monitoramento_jobs.listar_execucoes(metodo=METODO_SOB_DEMANDA, dias=7)
		self.assertEqual(len(todas["execucoes"]), 2)

		com_erro = monitoramento_jobs.listar_execucoes(metodo=METODO_SOB_DEMANDA, somente_com_erro=1, dias=7)
		self.assertEqual(len(com_erro["execucoes"]), 1)
		self.assertEqual(com_erro["execucoes"][0]["status"], job_logger.STATUS_ERRO)

	def test_listar_execucoes_respeita_o_periodo(self):
		_criar_log(
			METODO_SOB_DEMANDA,
			job_logger.STATUS_SUCESSO,
			inicio=add_to_date(now_datetime(), days=-30),
		)

		recentes = monitoramento_jobs.listar_execucoes(metodo=METODO_SOB_DEMANDA, dias=7)
		antigas = monitoramento_jobs.listar_execucoes(metodo=METODO_SOB_DEMANDA, dias=90)

		self.assertEqual(len(recentes["execucoes"]), 0)
		self.assertEqual(len(antigas["execucoes"]), 1)

	def test_listar_execucoes_pagina(self):
		for _ in range(3):
			_criar_log(METODO_SOB_DEMANDA, job_logger.STATUS_SUCESSO)

		pagina = monitoramento_jobs.listar_execucoes(metodo=METODO_SOB_DEMANDA, dias=7, limite=2)

		self.assertEqual(len(pagina["execucoes"]), 2)
		self.assertTrue(pagina["tem_mais"])
		self.assertEqual(pagina["proximo_inicio"], 2)
		self.assertEqual(pagina["total"], 3)

		segunda = monitoramento_jobs.listar_execucoes(
			metodo=METODO_SOB_DEMANDA, dias=7, limite=2, inicio_em=2
		)
		self.assertEqual(len(segunda["execucoes"]), 1)
		self.assertFalse(segunda["tem_mais"])

	def test_listar_jobs_pagina(self):
		completo = monitoramento_jobs.listar_jobs(dias=7, limite=monitoramento_jobs.LIMITE_MAXIMO)
		self.assertEqual(completo["total"], len(completo["jobs"]))
		if completo["total"] < 2:
			return

		primeira = monitoramento_jobs.listar_jobs(dias=7, limite=1)
		segunda = monitoramento_jobs.listar_jobs(dias=7, limite=1, inicio_em=1)

		self.assertEqual(primeira["total"], completo["total"])
		self.assertEqual(primeira["jobs"][0]["metodo"], completo["jobs"][0]["metodo"])
		self.assertEqual(segunda["jobs"][0]["metodo"], completo["jobs"][1]["metodo"])

	def test_listar_metodos_dos_jobs_inclui_agendados_e_ja_vistos(self):
		_criar_log(METODO_SOB_DEMANDA, job_logger.STATUS_SUCESSO)

		metodos = {job["metodo"] for job in monitoramento_jobs.listar_metodos_dos_jobs()["jobs"]}

		self.assertIn(METODO_AGENDADO, metodos)
		self.assertIn(METODO_SOB_DEMANDA, metodos)

	def test_obter_execucao_devolve_linha_do_tempo_e_metricas(self):
		log = _criar_log(METODO_SOB_DEMANDA, job_logger.STATUS_SUCESSO)

		detalhe = monitoramento_jobs.obter_execucao(log.name)["execucao"]

		self.assertEqual(detalhe["metodo"], METODO_SOB_DEMANDA)
		self.assertEqual(detalhe["eventos"][0]["mensagem"], "rodou")
		self.assertEqual(detalhe["metricas"], {"criados": 1})

	def test_obter_execucao_inexistente_falha(self):
		with self.assertRaises(frappe.DoesNotExistError):
			monitoramento_jobs.obter_execucao("nao-existe")

	# --------------------------------------------------------------- seguranca

	def test_leitura_exige_system_manager(self):
		# `frappe.only_for` e desligado sob `in_test`; aqui a guarda real precisa valer.
		with _sem_bypass_de_teste():
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				monitoramento_jobs.listar_jobs(dias=7)

	def test_executar_job_agora_recusa_metodo_fora_do_scheduler(self):
		with self.assertRaises(frappe.ValidationError):
			monitoramento_jobs.executar_job_agora("gris.api.qualquer_coisa.perigosa")

		with self.assertRaises(frappe.ValidationError):
			monitoramento_jobs.executar_job_agora("os.system")

	def test_executar_job_agora_exige_system_manager(self):
		with _sem_bypass_de_teste():
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				monitoramento_jobs.executar_job_agora(METODO_AGENDADO)

	def test_executar_job_agora_enfileira_job_agendado(self):
		chamadas = []
		tipo = frappe.get_doc("Scheduled Job Type", {"method": METODO_AGENDADO})
		original_get_doc = monitoramento_jobs.frappe.get_doc

		class TipoFalso:
			stopped = 0

			def enqueue(self, force=False):
				chamadas.append(force)
				return True

		def _get_doc(doctype, *args, **kwargs):
			if doctype == "Scheduled Job Type":
				return TipoFalso()
			return original_get_doc(doctype, *args, **kwargs)

		try:
			monitoramento_jobs.frappe.get_doc = _get_doc
			resposta = monitoramento_jobs.executar_job_agora(tipo.method)
		finally:
			monitoramento_jobs.frappe.get_doc = original_get_doc

		self.assertTrue(resposta["success"])
		self.assertEqual(chamadas, [True])


class TestPararExecucao(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.delete(job_logger.DOCTYPE, {"metodo": METODO_AGENDADO})

	def test_listar_em_execucao_traz_so_o_que_esta_rodando(self):
		rodando = _criar_log(METODO_AGENDADO, "Em Execucao", inicio=add_to_date(now_datetime(), days=-30))
		_criar_log(METODO_AGENDADO, "Sucesso")

		resposta = monitoramento_jobs.listar_em_execucao()

		nomes = [execucao.name for execucao in resposta["execucoes"]]
		self.assertIn(rodando.name, nomes)
		self.assertEqual(
			{execucao.status for execucao in resposta["execucoes"]},
			{"Em Execucao"},
		)

	def test_parar_execucao_sem_job_na_fila_encerra_o_log_preso(self):
		log = _criar_log(METODO_AGENDADO, "Em Execucao", job_id=None)

		resposta = monitoramento_jobs.parar_execucao(log.name)

		self.assertTrue(resposta["success"])
		self.assertEqual(resposta["resultado"], "ausente")
		log.reload()
		self.assertEqual(log.status, "Erro")
		self.assertTrue(log.fim)
		self.assertIn("Administrator", log.erro)

	def test_parar_execucao_recusa_execucao_ja_finalizada(self):
		log = _criar_log(METODO_AGENDADO, "Sucesso")

		with self.assertRaises(frappe.ValidationError):
			monitoramento_jobs.parar_execucao(log.name)

	def test_parar_execucao_recusa_metodo_fora_do_gris(self):
		log = _criar_log("frappe.utils.qualquer", "Em Execucao")
		try:
			with self.assertRaises(frappe.ValidationError):
				monitoramento_jobs.parar_execucao(log.name)
		finally:
			frappe.delete_doc(job_logger.DOCTYPE, log.name, force=True)

	def test_parar_execucao_exige_system_manager(self):
		log = _criar_log(METODO_AGENDADO, "Em Execucao")

		with _sem_bypass_de_teste():
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				monitoramento_jobs.parar_execucao(log.name)
