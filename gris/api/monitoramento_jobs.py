# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""API do Monitor de Jobs (pagina do Desk em ``/app/monitor-de-jobs``).

Le o DocType "Log de Execucao de Job" alimentado por ``gris.utils.job_logger``
e o "Scheduled Job Type" do proprio Frappe, para mostrar o que cada job fez em
cada execucao, quanto tempo levou e quais erros apareceram.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Date, Max, Sum
from frappe.utils import add_days, cint, flt, now_datetime, time_diff_in_seconds, today

from gris.utils.job_logger import DOCTYPE as DOCTYPE_LOG
from gris.utils.job_logger import rotulo_do_metodo

PAPEL_EXIGIDO = "System Manager"
PREFIXO_DO_APP = "gris."
LIMITE_MAXIMO = 200
LIMITE_PADRAO_DE_JOBS = 10
LIMITE_PADRAO_DE_EXECUCOES = 25
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
STATUS_EM_EXECUCAO = "Em Execucao"


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


def _jobs_agendados_sem_proxima() -> list[dict]:
	"""Versao barata de ``_jobs_agendados``: sem calcular a proxima execucao."""
	return frappe.get_all(
		"Scheduled Job Type",
		filters={"method": ["like", f"{PREFIXO_DO_APP}%"]},
		fields=["method as metodo"],
	)


def _estatisticas_por_metodo(desde: str) -> dict[str, dict]:
	log = frappe.qb.DocType(DOCTYPE_LOG)
	linhas = (
		frappe.qb.from_(log)
		.select(
			log.metodo,
			log.status,
			Count(log.name).as_("total"),
			Sum(log.duracao).as_("soma_duracao"),
		)
		.where(log.inicio >= desde)
		.groupby(log.metodo, log.status)
	).run(as_dict=True)

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
	log = frappe.qb.DocType(DOCTYPE_LOG)
	agrupado = frappe.qb.DocType(DOCTYPE_LOG).as_("agrupado")

	# Uma passada só: o subselect acha o `inicio` mais recente de cada método e o
	# join traz a linha inteira daquela execução, sem N+1 por job.
	mais_recentes = (
		frappe.qb.from_(agrupado)
		.select(agrupado.metodo, Max(agrupado.inicio).as_("inicio"))
		.groupby(agrupado.metodo)
	)

	linhas = (
		frappe.qb.from_(log)
		.inner_join(mais_recentes)
		.on((mais_recentes.metodo == log.metodo) & (mais_recentes.inicio == log.inicio))
		.select(
			log.name,
			log.job,
			log.metodo,
			log.status,
			log.inicio,
			log.duracao,
			log.resumo,
			log.total_erros,
			log.total_avisos,
		)
	).run(as_dict=True)

	ultimas: dict[str, dict] = {}
	for linha in linhas:
		# Execucoes empatadas no mesmo instante: fica a de nome maior, so para o
		# resultado ser estavel entre chamadas.
		atual = ultimas.get(linha.metodo)
		if not atual or (linha.name or "") > (atual.get("name") or ""):
			ultimas[linha.metodo] = dict(linha)

	return ultimas


@frappe.whitelist()
def listar_jobs(dias: Any = 7, limite: Any = LIMITE_PADRAO_DE_JOBS, inicio_em: Any = 0) -> dict:
	"""Lista os jobs conhecidos com a situacao da ultima execucao, paginados.

	Reune o que esta agendado no scheduler e o que ja apareceu no log — jobs
	apenas enfileirados (``frappe.enqueue``) tambem entram na lista.
	"""
	_garantir_acesso()

	dias = _normalizar_dias(dias)
	desde = _data_de_corte(dias)
	limite = max(1, min(cint(limite) or LIMITE_PADRAO_DE_JOBS, LIMITE_MAXIMO))
	inicio_em = max(0, cint(inicio_em))

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

	return {
		"success": True,
		"dias": dias,
		"jobs": resultado[inicio_em : inicio_em + limite],
		"total": len(resultado),
		"limite": limite,
		"inicio_em": inicio_em,
	}


@frappe.whitelist()
def listar_metodos_dos_jobs() -> dict:
	"""Todos os jobs conhecidos (agendados ou ja vistos no log), so nome e metodo.

	Alimenta o filtro "Job" da tela de execucoes sem carregar estatisticas.
	"""
	_garantir_acesso()

	log = frappe.qb.DocType(DOCTYPE_LOG)
	vistos = (frappe.qb.from_(log).select(log.metodo).distinct()).run(pluck="metodo")
	metodos = {agendado["metodo"] for agendado in _jobs_agendados_sem_proxima()} | set(vistos)

	return {
		"success": True,
		"jobs": sorted(
			({"metodo": metodo, "rotulo": rotulo_do_metodo(metodo)} for metodo in metodos if metodo),
			key=lambda job: job["rotulo"],
		),
	}


@frappe.whitelist()
def listar_execucoes(
	metodo: str | None = None,
	status: str | None = None,
	somente_com_erro: Any = 0,
	dias: Any = 7,
	limite: Any = LIMITE_PADRAO_DE_EXECUCOES,
	inicio_em: Any = 0,
) -> dict:
	"""Lista execucoes do periodo, da mais recente para a mais antiga, paginadas."""
	_garantir_acesso()

	dias = _normalizar_dias(dias)
	limite = max(1, min(cint(limite) or LIMITE_PADRAO_DE_EXECUCOES, LIMITE_MAXIMO))
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
		"total": frappe.db.count(DOCTYPE_LOG, filtros),
		"limite": limite,
		"inicio_em": inicio_em,
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

	log = frappe.qb.DocType(DOCTYPE_LOG)
	linhas = (
		frappe.qb.from_(log)
		.select(
			Date(log.inicio).as_("dia"),
			log.status,
			Count(log.name).as_("total"),
			Sum(log.duracao).as_("soma_duracao"),
		)
		.where(log.inicio >= desde)
		.groupby(Date(log.inicio), log.status)
		.orderby(Date(log.inicio))
	).run(as_dict=True)

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


@frappe.whitelist()
def listar_em_execucao() -> dict:
	"""Execucoes ainda em andamento, de qualquer data.

	Nao respeita o periodo do monitor: um job que travou ha dias continua
	precisando aparecer (e poder ser parado) mesmo com o filtro em 24 horas.
	"""
	_garantir_acesso()

	execucoes = frappe.get_all(
		DOCTYPE_LOG,
		filters={"status": STATUS_EM_EXECUCAO},
		fields=[*CAMPOS_DA_LISTA, "job_id", "fila"],
		order_by="inicio asc",
		limit_page_length=LIMITE_MAXIMO,
	)

	return {"success": True, "execucoes": execucoes, "atualizado_em": now_datetime()}


def _encerrar_job_no_rq(job_id: str | None) -> str:
	"""Para o job na fila do RQ. Devolve o que foi feito, para a mensagem ao usuario.

	- ``parado``: estava rodando e recebeu o comando de parada;
	- ``cancelado``: ainda estava na fila e foi removido;
	- ``ausente``: o RQ nao conhece mais o job (worker caiu, job expirou ou ja
	  terminou) — o log ficou preso em "Em Execucao" sem processo por tras.
	"""
	if not job_id:
		return "ausente"

	from frappe.utils.background_jobs import get_redis_conn
	from rq.command import send_stop_job_command
	from rq.exceptions import InvalidJobOperation, NoSuchJobError
	from rq.job import Job, JobStatus

	conexao = get_redis_conn()
	try:
		job = Job.fetch(job_id, connection=conexao)
	except NoSuchJobError:
		return "ausente"

	# A fila do RQ e compartilhada entre os sites do bench: nunca mexer no job de outro site.
	if (job.kwargs or {}).get("site") != frappe.local.site:
		frappe.throw(_("Este job pertence a outro site e não pode ser parado daqui."))

	situacao = job.get_status(refresh=True)
	try:
		if situacao == JobStatus.STARTED:
			send_stop_job_command(conexao, job.id)
			return "parado"
		if situacao in (JobStatus.QUEUED, JobStatus.DEFERRED, JobStatus.SCHEDULED):
			job.cancel()
			return "cancelado"
	except InvalidJobOperation:
		return "ausente"

	return "ausente"


@frappe.whitelist(methods=["POST"])
def parar_execucao(name: str) -> dict:
	"""Interrompe uma execucao em andamento e fecha o log dela como "Erro".

	Vale para jobs rodando no worker e para jobs ainda na fila. Se o RQ ja nao
	conhece o job (log "preso" apos queda do worker), apenas encerra o registro.
	"""
	_garantir_acesso()

	if not name or not frappe.db.exists(DOCTYPE_LOG, name):
		frappe.throw(_("Execução não encontrada."), frappe.DoesNotExistError)

	log = frappe.db.get_value(
		DOCTYPE_LOG, name, ["status", "metodo", "job_id", "inicio", "eventos"], as_dict=True
	)

	if log.status != STATUS_EM_EXECUCAO:
		frappe.throw(_("Esta execução já terminou e não pode ser parada."))

	if not str(log.metodo or "").startswith(PREFIXO_DO_APP):
		frappe.throw(_("Só é possível parar jobs do próprio GRIS por esta página."))

	resultado = _encerrar_job_no_rq(log.job_id)

	motivo = {
		"parado": _("Execução interrompida manualmente por {0}.").format(frappe.session.user),
		"cancelado": _("Execução cancelada por {0} antes de começar.").format(frappe.session.user),
		"ausente": _(
			"Execução encerrada manualmente por {0}: o job já não estava ativo na fila (o worker pode ter sido reiniciado)."
		).format(frappe.session.user),
	}[resultado]

	try:
		eventos = json.loads(log.eventos or "[]")
	except ValueError:
		eventos = []
	eventos.append(
		{
			"horario": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
			"nivel": "AVISO",
			"mensagem": motivo,
			"contexto": {},
		}
	)

	agora = now_datetime()
	frappe.db.set_value(
		DOCTYPE_LOG,
		name,
		{
			"status": "Erro",
			"fim": agora,
			"duracao": round(max(time_diff_in_seconds(agora, log.inicio), 0), 3),
			"erro": motivo,
			"eventos": json.dumps(eventos, ensure_ascii=False),
			"total_eventos": len(eventos),
			"total_avisos": cint(frappe.db.get_value(DOCTYPE_LOG, name, "total_avisos")) + 1,
		},
		update_modified=False,
	)

	return {"success": True, "resultado": resultado, "mensagem": motivo}
