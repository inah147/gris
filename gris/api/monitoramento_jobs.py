# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""API do Monitor de Jobs (pagina do Desk em ``/app/monitor-de-jobs``).

Le o DocType "Log de Execucao de Job" alimentado por ``gris.utils.job_logger``
e o "Scheduled Job Type" do proprio Frappe, para mostrar o que cada job fez em
cada execucao, quanto tempo levou e quais erros apareceram.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, now_datetime, today

from gris.utils.job_logger import DOCTYPE as DOCTYPE_LOG
from gris.utils.job_logger import rotulo_do_metodo

PAPEL_EXIGIDO = "System Manager"
PREFIXO_DO_APP = "gris."
LIMITE_MAXIMO = 200
DIAS_MAXIMOS = 365

CAMPOS_DA_LISTA = (
	"name",
	"job",
	"metodo",
	"origem",
	"status",
	"inicio",
	"fim",
	"duracao",
	"resumo",
	"total_eventos",
	"total_avisos",
	"total_erros",
)

STATUS_DE_FALHA = ("Erro", "Concluido com Erros")


def _garantir_acesso() -> None:
	frappe.only_for(PAPEL_EXIGIDO)


def _normalizar_dias(dias: Any) -> int:
	dias = cint(dias) or 7
	return max(1, min(dias, DIAS_MAXIMOS))


def _data_de_corte(dias: int) -> str:
	return add_days(today(), -dias)


def _jobs_agendados() -> list[dict]:
	"""Jobs do GRIS registrados no scheduler, com frequencia e proxima execucao."""
	tipos = frappe.get_all(
		"Scheduled Job Type",
		filters={"method": ["like", f"{PREFIXO_DO_APP}%"]},
		fields=["name", "method", "frequency", "cron_format", "stopped", "last_execution"],
		order_by="method asc",
	)

	agendados = []
	for tipo in tipos:
		proxima = None
		try:
			proxima = frappe.get_doc("Scheduled Job Type", tipo.name).get_next_execution()
		except Exception:
			# Cron invalido ou tipo recem-criado: a agenda e informativa, nao pode
			# derrubar a pagina inteira.
			pass

		agendados.append(
			{
				"metodo": tipo.method,
				"frequencia": tipo.frequency,
				"cron": tipo.cron_format,
				"parado": bool(tipo.stopped),
				"ultima_execucao_scheduler": tipo.last_execution,
				"proxima_execucao": proxima,
			}
		)

	return agendados


def _estatisticas_por_metodo(desde: str) -> dict[str, dict]:
	linhas = frappe.db.sql(
		f"""
		SELECT metodo, status, COUNT(*) AS total, SUM(duracao) AS soma_duracao
		FROM `tab{DOCTYPE_LOG}`
		WHERE inicio >= %(desde)s
		GROUP BY metodo, status
		""",
		{"desde": desde},
		as_dict=True,
	)

	estatisticas: dict[str, dict] = {}
	for linha in linhas:
		dados = estatisticas.setdefault(
			linha.metodo,
			{"execucoes": 0, "falhas": 0, "soma_duracao": 0.0, "por_status": {}},
		)
		dados["execucoes"] += cint(linha.total)
		dados["soma_duracao"] += flt(linha.soma_duracao)
		dados["por_status"][linha.status] = cint(linha.total)
		if linha.status in STATUS_DE_FALHA:
			dados["falhas"] += cint(linha.total)

	for dados in estatisticas.values():
		dados["duracao_media"] = (
			round(dados["soma_duracao"] / dados["execucoes"], 3) if dados["execucoes"] else 0.0
		)
		dados.pop("soma_duracao")

	return estatisticas


def _ultima_execucao_por_metodo() -> dict[str, dict]:
	linhas = frappe.db.sql(
		f"""
		SELECT log.name, log.job, log.metodo, log.status, log.inicio, log.duracao,
			log.resumo, log.total_erros, log.total_avisos
		FROM `tab{DOCTYPE_LOG}` log
		INNER JOIN (
			SELECT metodo, MAX(inicio) AS inicio
			FROM `tab{DOCTYPE_LOG}`
			GROUP BY metodo
		) ultima ON ultima.metodo = log.metodo AND ultima.inicio = log.inicio
		""",
		as_dict=True,
	)

	ultimas: dict[str, dict] = {}
	for linha in linhas:
		# Execucoes empatadas no mesmo instante: fica a de nome maior, so para o
		# resultado ser estavel entre chamadas.
		atual = ultimas.get(linha.metodo)
		if not atual or (linha.name or "") > (atual.get("name") or ""):
			ultimas[linha.metodo] = dict(linha)

	return ultimas


@frappe.whitelist()
def listar_jobs(dias: Any = 7) -> dict:
	"""Lista os jobs conhecidos com a situacao da ultima execucao.

	Reune o que esta agendado no scheduler e o que ja apareceu no log — jobs
	apenas enfileirados (``frappe.enqueue``) tambem entram na lista.
	"""
	_garantir_acesso()

	dias = _normalizar_dias(dias)
	desde = _data_de_corte(dias)

	estatisticas = _estatisticas_por_metodo(desde)
	ultimas = _ultima_execucao_por_metodo()

	jobs: dict[str, dict] = {}
	for agendado in _jobs_agendados():
		jobs[agendado["metodo"]] = {**agendado, "agendado": True}

	for metodo in list(estatisticas) + list(ultimas):
		jobs.setdefault(
			metodo,
			{
				"metodo": metodo,
				"frequencia": None,
				"cron": None,
				"parado": False,
				"proxima_execucao": None,
				"agendado": False,
			},
		)

	resultado = []
	for metodo, job in jobs.items():
		numeros = estatisticas.get(
			metodo, {"execucoes": 0, "falhas": 0, "duracao_media": 0.0, "por_status": {}}
		)
		ultima = ultimas.get(metodo)
		resultado.append(
			{
				**job,
				"rotulo": (ultima or {}).get("job") or rotulo_do_metodo(metodo),
				"execucoes": numeros["execucoes"],
				"falhas": numeros["falhas"],
				"duracao_media": numeros["duracao_media"],
				"por_status": numeros["por_status"],
				"ultima": ultima,
			}
		)

	# Quem falhou aparece primeiro; depois quem rodou mais recentemente.
	resultado.sort(
		key=lambda job: (
			0 if job["falhas"] else 1,
			-(
				job["ultima"]["inicio"].timestamp()
				if job.get("ultima") and job["ultima"].get("inicio")
				else 0
			),
			job["rotulo"],
		)
	)

	return {"success": True, "dias": dias, "jobs": resultado}


@frappe.whitelist()
def listar_execucoes(
	metodo: str | None = None,
	status: str | None = None,
	somente_com_erro: Any = 0,
	dias: Any = 7,
	limite: Any = 50,
	inicio_em: Any = 0,
) -> dict:
	"""Lista execucoes do periodo, da mais recente para a mais antiga."""
	_garantir_acesso()

	dias = _normalizar_dias(dias)
	limite = max(1, min(cint(limite) or 50, LIMITE_MAXIMO))
	inicio_em = max(0, cint(inicio_em))

	filtros: dict[str, Any] = {"inicio": [">=", _data_de_corte(dias)]}
	if metodo:
		filtros["metodo"] = metodo
	if status:
		filtros["status"] = status
	if cint(somente_com_erro):
		filtros["status"] = ["in", list(STATUS_DE_FALHA)]

	execucoes = frappe.get_all(
		DOCTYPE_LOG,
		filters=filtros,
		fields=list(CAMPOS_DA_LISTA),
		order_by="inicio desc",
		limit_start=inicio_em,
		limit_page_length=limite + 1,
	)

	tem_mais = len(execucoes) > limite
	return {
		"success": True,
		"execucoes": execucoes[:limite],
		"tem_mais": tem_mais,
		"proximo_inicio": inicio_em + limite if tem_mais else None,
	}


@frappe.whitelist()
def obter_execucao(name: str) -> dict:
	"""Detalhe completo de uma execucao: linha do tempo, metricas e erro."""
	_garantir_acesso()

	if not name or not frappe.db.exists(DOCTYPE_LOG, name):
		frappe.throw(_("Execução não encontrada."), frappe.DoesNotExistError)

	doc = frappe.get_doc(DOCTYPE_LOG, name)

	return {
		"success": True,
		"execucao": {
			**{campo: doc.get(campo) for campo in CAMPOS_DA_LISTA},
			"usuario": doc.usuario,
			"fila": doc.fila,
			"job_id": doc.job_id,
			"parametros": doc.parametros,
			"erro": doc.erro,
			"error_log": doc.error_log,
			"eventos": doc.get_eventos(),
			"metricas": doc.get_metricas(),
		},
	}


@frappe.whitelist()
def resumo_geral(dias: Any = 7) -> dict:
	"""Numeros do periodo e serie diaria para o grafico do monitor."""
	_garantir_acesso()

	dias = _normalizar_dias(dias)
	desde = _data_de_corte(dias)

	linhas = frappe.db.sql(
		f"""
		SELECT DATE(inicio) AS dia, status, COUNT(*) AS total, SUM(duracao) AS soma_duracao
		FROM `tab{DOCTYPE_LOG}`
		WHERE inicio >= %(desde)s
		GROUP BY DATE(inicio), status
		ORDER BY dia ASC
		""",
		{"desde": desde},
		as_dict=True,
	)

	por_dia: dict[str, dict[str, int]] = {}
	totais: dict[str, int] = {}
	execucoes = 0
	soma_duracao = 0.0

	for linha in linhas:
		dia = str(linha.dia)
		por_dia.setdefault(dia, {})[linha.status] = cint(linha.total)
		totais[linha.status] = totais.get(linha.status, 0) + cint(linha.total)
		execucoes += cint(linha.total)
		soma_duracao += flt(linha.soma_duracao)

	falhas = sum(totais.get(status, 0) for status in STATUS_DE_FALHA)
	em_execucao = totais.get("Em Execucao", 0)

	return {
		"success": True,
		"dias": dias,
		"execucoes": execucoes,
		"falhas": falhas,
		"em_execucao": em_execucao,
		"taxa_de_sucesso": round((execucoes - falhas) / execucoes * 100, 1) if execucoes else None,
		"duracao_media": round(soma_duracao / execucoes, 3) if execucoes else 0.0,
		"por_status": totais,
		"serie": [{"dia": dia, **contagens} for dia, contagens in sorted(por_dia.items())],
		"atualizado_em": now_datetime(),
	}


@frappe.whitelist(methods=["POST"])
def executar_job_agora(metodo: str) -> dict:
	"""Reenfileira um job agendado do GRIS para rodar imediatamente.

	Só aceita métodos já cadastrados como "Scheduled Job Type" — a lista de
	jobs agendados é a allowlist, para a página nunca virar um executor de
	método arbitrário.
	"""
	_garantir_acesso()

	nome_do_tipo = frappe.db.get_value("Scheduled Job Type", {"method": metodo}, "name")
	if not nome_do_tipo:
		frappe.throw(_("Este job não está agendado no scheduler e não pode ser disparado por aqui."))

	if not str(metodo).startswith(PREFIXO_DO_APP):
		frappe.throw(_("Só é possível disparar jobs do próprio GRIS por esta página."))

	tipo = frappe.get_doc("Scheduled Job Type", nome_do_tipo)
	if tipo.stopped:
		frappe.throw(_("Este job está pausado no scheduler. Reative-o antes de executar."))

	enfileirado = tipo.enqueue(force=True)
	if not enfileirado:
		return {
			"success": False,
			"mensagem": _("O job já está na fila aguardando execução."),
		}

	return {
		"success": True,
		"mensagem": _("Job enviado para a fila. O resultado aparece aqui assim que a execução terminar."),
	}
