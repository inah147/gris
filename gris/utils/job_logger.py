# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Registro detalhado das execucoes de jobs do GRIS.

Duas camadas trabalham juntas:

1. **Automatica** — os hooks ``before_job`` / ``after_job`` abrem e fecham um
   "Log de Execucao de Job" para cada job rodado por um worker (agendado pelo
   scheduler ou enfileirado com ``frappe.enqueue``), guardando inicio, fim,
   duracao, status, parametros e traceback.
2. **Detalhada** — o proprio job descreve o que fez chamando ``obter_logger()``,
   ``registrar()``, ``metrica()`` e ``definir_resumo()``. Tudo isso entra na
   linha do tempo da execucao aberta pela camada automatica.

Fora de um job as funcoes viram no-op: o mesmo codigo continua funcionando
quando chamado a partir de uma requisicao HTTP ou de um teste.

Jobs do proprio framework (``frappe.*``) so geram registro quando falham, para
o log nao virar ruido com as tarefas de manutencao que rodam a cada poucos
minutos.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import frappe
from frappe.utils import now_datetime

DOCTYPE = "Log de Execucao de Job"
ATRIBUTO_LOCAL = "gris_execucao_job"
PREFIXO_DO_APP = "gris."
METODO_JOB_AGENDADO = "frappe.core.doctype.scheduled_job_type.scheduled_job_type.run_scheduled_job"

ORIGEM_AGENDADO = "Agendado"
ORIGEM_FILA = "Fila"
ORIGEM_MANUAL = "Manual"

STATUS_EM_EXECUCAO = "Em Execucao"
STATUS_SUCESSO = "Sucesso"
STATUS_SUCESSO_COM_AVISOS = "Sucesso com Avisos"
STATUS_CONCLUIDO_COM_ERROS = "Concluido com Erros"
STATUS_ERRO = "Erro"

NIVEL_DEBUG = "DEBUG"
NIVEL_INFO = "INFO"
NIVEL_AVISO = "AVISO"
NIVEL_ERRO = "ERRO"

# Limites para uma execucao com muitos itens nao estourar o tamanho da linha.
LIMITE_DE_EVENTOS = 400
LIMITE_DA_MENSAGEM = 1000
LIMITE_DO_RESUMO = 500
LIMITE_DO_TRACEBACK = 20000
LIMITE_DOS_PARAMETROS = 4000

CHAVES_SENSIVEIS = ("password", "passwd", "secret", "token", "key", "pwd", "authorization")

_NIVEL_POR_LOGGING = {
	logging.DEBUG: NIVEL_DEBUG,
	logging.INFO: NIVEL_INFO,
	logging.WARNING: NIVEL_AVISO,
	logging.ERROR: NIVEL_ERRO,
	logging.CRITICAL: NIVEL_ERRO,
}

_METODO_POR_NIVEL = {
	logging.DEBUG: "debug",
	logging.INFO: "info",
	logging.WARNING: "warning",
	logging.ERROR: "error",
	logging.CRITICAL: "critical",
}

_ALIAS_DE_NIVEL = {
	"WARN": NIVEL_AVISO,
	"WARNING": NIVEL_AVISO,
	"AVISO": NIVEL_AVISO,
	"ERROR": NIVEL_ERRO,
	"ERRO": NIVEL_ERRO,
	"CRITICAL": NIVEL_ERRO,
	"EXCEPTION": NIVEL_ERRO,
	"INFO": NIVEL_INFO,
	"DEBUG": NIVEL_DEBUG,
}

# Nome amigavel de cada job, exibido no Monitor de Jobs. Metodos ausentes daqui
# ganham um rotulo derivado do proprio caminho do metodo.
ROTULOS_DE_JOBS = {
	"gris.api.associados_notificacoes.enviar_lembrete_atualizacao_associados": (
		"Lembrete de atualização dos associados"
	),
	"gris.api.associados_vencimento_notificacoes.enviar_lembretes_vencimento_registro_associados": (
		"Lembretes de vencimento de registro"
	),
	"gris.api.backup.google_shared_drive.enqueue_daily_backup": "Backup diário (agendamento)",
	"gris.api.backup.google_shared_drive.run_daily_backup": "Backup diário no Google Drive",
	"gris.api.calendario.sync_feriados.sync_feriados": "Sincronização de feriados",
	"gris.api.financeiro.conta_fixa.generate_monthly_fixed_payments": (
		"Geração mensal de pagamentos de contas fixas"
	),
	"gris.api.financeiro.infinitepay_email_import.enqueue_infinitepay_email_import": (
		"Importação do fechamento Infinitepay por e-mail (agendamento)"
	),
	"gris.api.financeiro.infinitepay_email_import.run_infinitepay_email_import": (
		"Importação do fechamento Infinitepay por e-mail"
	),
	"gris.api.financeiro.monthly_payments.generate_monthly_payments": ("Geração mensal de contribuições"),
	"gris.api.financeiro.monthly_payments.update_status_monthly_payment": (
		"Atualização de status das contribuições"
	),
	"gris.api.google_workspace.access_manager.enqueue_daily_global_access_sync": (
		"Sincronização de acessos do Workspace (agendamento)"
	),
	"gris.api.google_workspace.access_manager.enqueue_daily_inactive_access_cleanup": (
		"Limpeza de acessos inativos (agendamento)"
	),
	"gris.api.google_workspace.access_manager.enqueue_daily_restricted_access_cleanup": (
		"Limpeza de acessos restritos (agendamento)"
	),
	"gris.api.google_workspace.access_manager.run_daily_global_access_sync": (
		"Sincronização de acessos do Google Workspace"
	),
	"gris.api.google_workspace.access_manager.run_daily_inactive_access_cleanup": (
		"Limpeza de acessos de associados inativos"
	),
	"gris.api.google_workspace.access_manager.run_daily_restricted_access_cleanup": (
		"Limpeza de acessos restritos do Workspace"
	),
	"gris.api.recepcao_notificacoes.enviar_lembretes_visita": "Lembretes de visita da recepção",
	"gris.api.registro_provisorio_notificacoes.enviar_avisos_seguimento_registro_provisorio": (
		"Avisos de seguimento do registro provisório"
	),
	"gris.api.users.user_manager.manage_associate_users": "Manutenção dos usuários de associados",
	"gris.festas.doctype.festa.festa.marcar_festas_realizadas": "Marcação de festas realizadas",
	"gris.festas.doctype.opcao_convite_festa.opcao_convite_festa.atualizar_lotes_opcoes_convite": (
		"Atualização de lotes das opções de convite"
	),
	"gris.gestao_de_projetos.doctype.projeto.projeto.enviar_lembretes_whatsapp_aprovacao_projetos": (
		"Lembretes de aprovação de projetos"
	),
	"gris.gris.doctype.gestao_de_tarefas.gestao_de_tarefas.validar_tarefas_atrasadas": (
		"Validação de tarefas atrasadas"
	),
	"gris.gris.doctype.novo_associado.novo_associado.atualizar_ramos_por_idade": (
		"Atualização de ramo dos novos associados"
	),
}


def _truncar(texto: str | None, limite: int) -> str | None:
	if texto is None:
		return None

	texto = str(texto)
	if len(texto) <= limite:
		return texto

	return f"{texto[:limite]}\n… (conteúdo truncado)"


def _normalizar_nivel(nivel: str | None) -> str:
	return _ALIAS_DE_NIVEL.get((nivel or NIVEL_INFO).upper(), NIVEL_INFO)


def rotulo_do_metodo(metodo: str) -> str:
	"""Devolve o nome amigavel do job a partir do caminho do metodo."""
	if not metodo:
		return "Job desconhecido"

	rotulo = ROTULOS_DE_JOBS.get(metodo)
	if rotulo:
		return rotulo

	nome_da_funcao = metodo.split(".")[-1]
	return nome_da_funcao.replace("_", " ").strip().capitalize() or metodo


def _sanitizar(valor: Any) -> Any:
	"""Remove segredos de dicionarios antes de gravar os parametros do job."""
	if isinstance(valor, dict):
		limpo = {}
		for chave, item in valor.items():
			if any(sensivel in str(chave).lower() for sensivel in CHAVES_SENSIVEIS):
				limpo[chave] = "***"
			else:
				limpo[chave] = _sanitizar(item)
		return limpo

	if isinstance(valor, list | tuple):
		return [_sanitizar(item) for item in valor]

	return valor


def _serializar(valor: Any, limite: int) -> str | None:
	if valor in (None, {}, []):
		return None

	try:
		texto = json.dumps(_sanitizar(valor), ensure_ascii=False, default=str, indent=1)
	except (TypeError, ValueError):
		texto = str(valor)

	return _truncar(texto, limite)


class ExecucaoJob:
	"""Acumula o que aconteceu em uma execucao e persiste o log correspondente."""

	def __init__(
		self,
		metodo: str,
		rotulo: str | None = None,
		origem: str = ORIGEM_FILA,
		parametros: dict | None = None,
		job_id: str | None = None,
		fila: str | None = None,
		persistir_sempre: bool = True,
	):
		self.metodo = metodo
		self.rotulo = rotulo or rotulo_do_metodo(metodo)
		self.origem = origem
		self.parametros = parametros or {}
		self.job_id = job_id
		self.fila = fila
		self.persistir_sempre = persistir_sempre
		self.usuario = getattr(frappe.session, "user", None)
		self.inicio = now_datetime()
		self.eventos: list[dict] = []
		self.metricas: dict[str, Any] = {}
		self.resumo: str | None = None
		self.total_avisos = 0
		self.total_erros = 0
		self.eventos_descartados = 0
		self.name: str | None = None
		self._contador = time.monotonic()

	# ---------------------------------------------------------------- registro

	def registrar(self, mensagem: Any, nivel: str = NIVEL_INFO, **contexto: Any) -> None:
		"""Adiciona uma linha a linha do tempo da execucao."""
		nivel = _normalizar_nivel(nivel)
		if nivel == NIVEL_AVISO:
			self.total_avisos += 1
		elif nivel == NIVEL_ERRO:
			self.total_erros += 1

		if len(self.eventos) >= LIMITE_DE_EVENTOS:
			self.eventos_descartados += 1
			return

		self.eventos.append(
			{
				"horario": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
				"nivel": nivel,
				"mensagem": _truncar(str(mensagem), LIMITE_DA_MENSAGEM),
				"contexto": _sanitizar(contexto) if contexto else {},
			}
		)

	def metrica(self, chave: str, valor: Any = 1, incrementar: bool = True) -> None:
		"""Registra um contador do job (ex.: ``metrica("criados")``)."""
		if (
			incrementar
			and isinstance(valor, int | float)
			and isinstance(self.metricas.get(chave), int | float)
		):
			self.metricas[chave] += valor
		elif incrementar and isinstance(valor, int | float) and chave not in self.metricas:
			self.metricas[chave] = valor
		else:
			self.metricas[chave] = valor

	def definir_resumo(self, texto: str) -> None:
		"""Define a frase que resume o resultado da execucao."""
		self.resumo = _truncar(texto, LIMITE_DO_RESUMO)

	def duracao(self) -> float:
		return round(time.monotonic() - self._contador, 3)

	# --------------------------------------------------------------- persistencia

	def _eventos_para_gravar(self) -> list[dict]:
		eventos = list(self.eventos)
		if self.eventos_descartados:
			eventos.append(
				{
					"horario": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
					"nivel": NIVEL_AVISO,
					"mensagem": (
						f"{self.eventos_descartados} evento(s) adicionais não foram gravados "
						f"(limite de {LIMITE_DE_EVENTOS} por execução)."
					),
					"contexto": {},
				}
			)
		return eventos

	def _dados(self, status: str, erro: str | None = None, error_log: str | None = None) -> dict:
		eventos = self._eventos_para_gravar()
		return {
			"job": self.rotulo,
			"metodo": self.metodo,
			"origem": self.origem,
			"status": status,
			"inicio": self.inicio,
			"fim": now_datetime() if status != STATUS_EM_EXECUCAO else None,
			"duracao": self.duracao(),
			"resumo": self.resumo,
			"total_eventos": len(eventos),
			"total_avisos": self.total_avisos,
			"total_erros": self.total_erros,
			"eventos": json.dumps(eventos, ensure_ascii=False, default=str),
			"metricas": json.dumps(_sanitizar(self.metricas), ensure_ascii=False, default=str),
			"erro": _truncar(erro, LIMITE_DO_TRACEBACK),
			"error_log": error_log,
			"usuario": self.usuario,
			"fila": self.fila,
			"job_id": self.job_id,
			"parametros": _serializar(self.parametros, LIMITE_DOS_PARAMETROS),
		}

	def abrir(self) -> None:
		"""Grava o log ja em "Em Execucao", para o job aparecer enquanto roda."""
		if not self.persistir_sempre:
			return

		self.name = _inserir(self._dados(STATUS_EM_EXECUCAO))

	def fechar(self, status: str, erro: str | None = None, error_log: str | None = None) -> None:
		"""Finaliza o log com o status apurado."""
		houve_problema = status in (STATUS_ERRO, STATUS_CONCLUIDO_COM_ERROS)
		if not self.persistir_sempre and not houve_problema:
			return

		dados = self._dados(status, erro=erro, error_log=error_log)
		if self.name:
			_atualizar(self.name, dados)
		else:
			self.name = _inserir(dados)


def _inserir(dados: dict) -> str | None:
	"""Insere o log em transacao propria, sem derrubar o job em caso de falha."""
	try:
		# ignore_permissions: o log e escrito pelo worker, que roda como
		# Administrator/Guest conforme o job; o DocType e somente leitura na UI.
		doc = frappe.get_doc({"doctype": DOCTYPE, **dados})
		doc.insert(ignore_permissions=True)
		frappe.db.commit()  # nosemgrep — o log precisa sobreviver ao rollback do job
		return doc.name
	except Exception:
		_avisar_falha_do_proprio_log("insert")
		return None


def _atualizar(name: str, dados: dict) -> None:
	try:
		frappe.db.set_value(DOCTYPE, name, dados, update_modified=False)
		frappe.db.commit()  # nosemgrep — o log precisa sobreviver ao rollback do job
	except Exception:
		_avisar_falha_do_proprio_log("update")


def _avisar_falha_do_proprio_log(operacao: str) -> None:
	"""Falha ao gravar o log nunca pode quebrar o job que estava sendo observado."""
	try:
		frappe.logger("gris_job_logger", allow_site=True).warning(
			f"Falha ao gravar o log de execucao de job ({operacao}): {frappe.get_traceback()}"
		)
	except Exception:
		pass


# ------------------------------------------------------------------ API do job


def execucao_atual() -> ExecucaoJob | None:
	"""Retorna a execucao de job em andamento nesta thread, se houver."""
	return getattr(frappe.local, ATRIBUTO_LOCAL, None)


def registrar(mensagem: Any, nivel: str = NIVEL_INFO, **contexto: Any) -> None:
	"""Registra uma linha no log do job em andamento (no-op fora de um job)."""
	execucao = execucao_atual()
	if execucao:
		execucao.registrar(mensagem, nivel=nivel, **contexto)


def metrica(chave: str, valor: Any = 1, incrementar: bool = True) -> None:
	"""Registra um contador no log do job em andamento (no-op fora de um job)."""
	execucao = execucao_atual()
	if execucao:
		execucao.metrica(chave, valor, incrementar=incrementar)


def definir_resumo(texto: str) -> None:
	"""Define o resumo do job em andamento (no-op fora de um job)."""
	execucao = execucao_atual()
	if execucao:
		execucao.definir_resumo(texto)


class LoggerDoJob:
	"""Logger que escreve no arquivo de log e na linha do tempo da execucao.

	Substitui ``frappe.logger(...)`` dentro de jobs: mantem a mesma interface
	(``info``/``warning``/``error``/``debug``/``exception``) e, de quebra, grava
	o que foi dito no "Log de Execucao de Job" da execucao corrente.
	"""

	def __init__(self, nome: str, **opcoes: Any):
		self.nome = nome
		self._logger = frappe.logger(nome, allow_site=True, **opcoes)
		_garantir_captura(self._logger)

	@staticmethod
	def _formatar(mensagem: Any, args: tuple) -> str:
		"""Aplica a interpolacao ``%`` do logging padrao (``logger.info("x=%s", x)``)."""
		if not args:
			return mensagem

		try:
			return str(mensagem) % args
		except (TypeError, ValueError):
			return f"{mensagem} {args}"

	def _escrever_no_arquivo(self, nivel_logging: int, mensagem: Any, args: tuple, **extras: Any) -> None:
		"""Escreve no logger do Frappe sem nunca derrubar o job.

		`gris_ja_registrado` evita registro em dobro: o handler de captura
		ignora os records que ja passaram por aqui. O fallback cobre loggers
		substituidos por dublês em testes, que nem sempre implementam `log`.
		"""
		try:
			self._logger.log(nivel_logging, mensagem, *args, extra={"gris_ja_registrado": True}, **extras)
			return
		except AttributeError:
			pass
		except Exception:
			return

		metodo = getattr(self._logger, _METODO_POR_NIVEL.get(nivel_logging, "info"), None)
		if not callable(metodo):
			return

		try:
			metodo(mensagem, *args)
		except Exception:
			pass

	def _emitir(self, nivel_logging: int, mensagem: Any, args: tuple, contexto: dict) -> None:
		self._escrever_no_arquivo(nivel_logging, mensagem, args)
		registrar(
			self._formatar(mensagem, args),
			nivel=_NIVEL_POR_LOGGING.get(nivel_logging, NIVEL_INFO),
			**contexto,
		)

	def debug(self, mensagem: Any, *args: Any, **contexto: Any) -> None:
		self._emitir(logging.DEBUG, mensagem, args, contexto)

	def info(self, mensagem: Any, *args: Any, **contexto: Any) -> None:
		self._emitir(logging.INFO, mensagem, args, contexto)

	def warning(self, mensagem: Any, *args: Any, **contexto: Any) -> None:
		self._emitir(logging.WARNING, mensagem, args, contexto)

	def error(self, mensagem: Any, *args: Any, **contexto: Any) -> None:
		self._emitir(logging.ERROR, mensagem, args, contexto)

	def exception(self, mensagem: Any, *args: Any, **contexto: Any) -> None:
		"""Registra um erro junto do traceback da excecao em tratamento."""
		self._escrever_no_arquivo(logging.ERROR, mensagem, args, exc_info=True)
		registrar(
			self._formatar(mensagem, args),
			nivel=NIVEL_ERRO,
			traceback=frappe.get_traceback(),
			**contexto,
		)

	# Apelidos em portugues, alinhados ao vocabulario do restante do app.
	aviso = warning
	erro = error


def obter_logger(nome: str, **opcoes: Any) -> LoggerDoJob:
	"""Logger recomendado dentro de jobs — veja :class:`LoggerDoJob`.

	``opcoes`` extras (``file_count``, ``max_size``, …) seguem para
	``frappe.logger``, mantendo a compatibilidade com quem ja customizava.
	"""
	return LoggerDoJob(nome, **opcoes)


@contextmanager
def registrar_execucao(
	metodo: str,
	rotulo: str | None = None,
	origem: str = ORIGEM_MANUAL,
	parametros: dict | None = None,
) -> Iterator[ExecucaoJob]:
	"""Abre um log de execucao para codigo rodado fora de um worker.

	Util em botoes de "executar agora" e em rotinas sincronas. Se ja existir uma
	execucao em andamento, apenas reaproveita a atual (nao duplica o log).
	"""
	em_andamento = execucao_atual()
	if em_andamento:
		yield em_andamento
		return

	execucao = ExecucaoJob(metodo=metodo, rotulo=rotulo, origem=origem, parametros=parametros)
	setattr(frappe.local, ATRIBUTO_LOCAL, execucao)
	execucao.abrir()

	try:
		yield execucao
	except Exception:
		setattr(frappe.local, ATRIBUTO_LOCAL, None)
		execucao.registrar("A execução foi interrompida por um erro.", nivel=NIVEL_ERRO)
		execucao.fechar(STATUS_ERRO, erro=frappe.get_traceback(with_context=True))
		raise
	else:
		setattr(frappe.local, ATRIBUTO_LOCAL, None)
		execucao.fechar(_status_final(execucao))


def _status_final(execucao: ExecucaoJob) -> str:
	if execucao.total_erros:
		return STATUS_CONCLUIDO_COM_ERROS
	if execucao.total_avisos:
		return STATUS_SUCESSO_COM_AVISOS
	return STATUS_SUCESSO


# --------------------------------------------------------- captura de logging


class _CapturaDeLog(logging.Handler):
	"""Espelha o que os loggers do Frappe emitirem para a execucao corrente."""

	def emit(self, record: logging.LogRecord) -> None:
		if getattr(record, "gris_ja_registrado", False):
			return

		execucao = execucao_atual()
		if not execucao:
			return

		try:
			execucao.registrar(
				record.getMessage(),
				nivel=_NIVEL_POR_LOGGING.get(record.levelno, NIVEL_INFO),
			)
		except Exception:
			pass


_CAPTURA = _CapturaDeLog()
_CAPTURA.setLevel(logging.DEBUG)


def _garantir_captura(logger: Any) -> None:
	"""Instala o handler de captura, tolerando loggers que nao sejam padrao.

	Em testes o ``frappe.logger`` costuma ser trocado por um dublê sem
	``handlers``; nesse caso nao ha o que instrumentar e seguimos em frente.
	"""
	if not isinstance(logger, logging.Logger):
		return

	if not any(isinstance(handler, _CapturaDeLog) for handler in logger.handlers):
		logger.addHandler(_CAPTURA)


def _capturar_loggers_existentes() -> None:
	"""Cobre tambem quem continuar usando ``frappe.logger`` direto.

	Os loggers do Frappe filtram por nivel antes do handler, entao dessa forma
	chegam ao log os avisos e erros — que e justamente o que interessa em codigo
	que ainda nao usa :func:`obter_logger`.
	"""
	for logger in list(getattr(frappe, "loggers", {}).values()):
		try:
			_garantir_captura(logger)
		except Exception:
			pass


# ------------------------------------------------------------------- hooks


def before_job(method: str | None = None, kwargs: dict | None = None, **_ignorado: Any) -> None:
	"""Hook ``before_job``: abre o log da execucao que esta comecando."""
	try:
		_iniciar(method or "", kwargs or {})
	except Exception:
		_avisar_falha_do_proprio_log("before_job")


def after_job(
	method: str | None = None,
	kwargs: dict | None = None,
	result: Any = None,
	**_ignorado: Any,
) -> None:
	"""Hook ``after_job``: apura o status e fecha o log da execucao."""
	try:
		_finalizar(result)
	except Exception:
		_avisar_falha_do_proprio_log("after_job")


def _dados_do_worker() -> tuple[str | None, str | None]:
	try:
		from rq import get_current_job

		job = get_current_job()
		if job:
			return job.id, job.origin
	except Exception:
		pass

	return None, None


def _iniciar(method: str, kwargs: dict) -> None:
	metodo = method
	origem = ORIGEM_FILA
	parametros = dict(kwargs or {})

	if metodo == METODO_JOB_AGENDADO:
		# O scheduler enfileira sempre o mesmo wrapper; o job de verdade vem em
		# `job_type`. Sem isso, todo job agendado apareceria com o mesmo nome.
		metodo = parametros.get("job_type") or metodo
		origem = ORIGEM_AGENDADO
		parametros = {}

	job_id, fila = _dados_do_worker()
	execucao = ExecucaoJob(
		metodo=metodo,
		origem=origem,
		parametros=parametros,
		job_id=job_id,
		fila=fila,
		persistir_sempre=metodo.startswith(PREFIXO_DO_APP),
	)
	setattr(frappe.local, ATRIBUTO_LOCAL, execucao)
	_capturar_loggers_existentes()
	execucao.abrir()


def _finalizar(result: Any) -> None:
	execucao = execucao_atual()
	if not execucao:
		return

	# Zerado antes de persistir para o proprio log nao capturar seus eventos.
	setattr(frappe.local, ATRIBUTO_LOCAL, None)

	erro = _traceback_da_excecao_em_curso()
	if not erro and execucao.origem == ORIGEM_AGENDADO:
		erro = _falha_do_job_agendado(execucao)

	_absorver_retorno(execucao, result)

	if erro:
		status = STATUS_ERRO
	else:
		status = _status_final(execucao)

	execucao.fechar(status, erro=erro, error_log=_error_log_recente(execucao) if erro else None)


def _traceback_da_excecao_em_curso() -> str | None:
	"""``after_job`` roda dentro do ``finally`` — a excecao ainda esta ativa aqui."""
	tipo, valor, tb = sys.exc_info()
	if not tipo:
		return None

	return _truncar("".join(traceback.format_exception(tipo, valor, tb)), LIMITE_DO_TRACEBACK)


def _nome_do_tipo_agendado(metodo: str) -> str:
	"""Reproduz o ``autoname`` de "Scheduled Job Type" (dois ultimos segmentos)."""
	return ".".join(metodo.split(".")[-2:])


def _falha_do_job_agendado(execucao: ExecucaoJob) -> str | None:
	"""Jobs agendados engolem a excecao; a falha fica no "Scheduled Job Log"."""
	try:
		registro = frappe.db.get_value(
			"Scheduled Job Log",
			filters={
				"scheduled_job_type": _nome_do_tipo_agendado(execucao.metodo),
				"creation": [">=", execucao.inicio],
			},
			fieldname=["status", "details"],
			order_by="creation desc",
			as_dict=True,
		)
	except Exception:
		return None

	if not registro or registro.get("status") != "Failed":
		return None

	return _truncar(registro.get("details") or "O job agendado terminou com falha.", LIMITE_DO_TRACEBACK)


def _absorver_retorno(execucao: ExecucaoJob, result: Any) -> None:
	"""Aproveita o retorno do job como metricas/resumo quando ele devolve dados."""
	if result is None:
		return

	if isinstance(result, dict):
		for chave, valor in result.items():
			if isinstance(valor, int | float) and not isinstance(valor, bool):
				execucao.metrica(str(chave), valor, incrementar=False)
		if not execucao.resumo:
			resumo = ", ".join(
				f"{str(chave).replace('_', ' ')}: {valor}"
				for chave, valor in result.items()
				if isinstance(valor, int | float) and not isinstance(valor, bool)
			)
			if resumo:
				execucao.definir_resumo(resumo)
		return

	if isinstance(result, int | float) and not isinstance(result, bool):
		execucao.metrica("retorno", result, incrementar=False)
		if not execucao.resumo:
			execucao.definir_resumo(f"Retorno do job: {result}")


def _error_log_recente(execucao: ExecucaoJob) -> str | None:
	"""Liga o log ao "Error Log" que o proprio Frappe gravou para esta falha."""
	try:
		return frappe.db.get_value(
			"Error Log",
			filters={"method": execucao.metodo, "creation": [">=", execucao.inicio]},
			fieldname="name",
			order_by="creation desc",
		)
	except Exception:
		return None
