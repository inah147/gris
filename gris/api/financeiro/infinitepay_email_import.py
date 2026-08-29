# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Importação automática do fechamento mensal da Infinitepay recebido por e-mail.

A Infinitepay envia, todo 5º dia útil do mês, um e-mail com os três relatórios
(extrato, vendas e recebimentos) usados na conciliação — hoje feita manualmente
em `/financeiro/contas` (`process_uploaded_files`). Este módulo automatiza o
mesmo fluxo: aguarda o 5º dia útil, busca o e-mail na Conta de e-mail configurada
em "Configuracao infinitepay", identifica os três anexos pelo conteúdo (o
cliente de e-mail pode renomear o arquivo) e reaproveita
`reconciliar_e_inserir_infinitepay` para inserir as transações.

A inserção já é idempotente por si só (cada doctype de origem verifica
`frappe.db.exists` antes de inserir), então rodar o job mais de uma vez no mesmo
dia não duplica nada. `ultimo_mes_importado` só evita ficar buscando o e-mail
todo dia pelo resto do mês depois que o fechamento já foi importado.
"""

from datetime import date, timedelta

import frappe
from frappe.utils import getdate
from frappe.utils.background_jobs import enqueue

from gris.api.financeiro.infinitepay import (
	TIPO_EXTRATO,
	TIPO_RECEBIMENTOS,
	TIPO_VENDAS,
	identificar_tipo_arquivo,
)
from gris.utils.job_logger import definir_resumo, metrica, obter_logger
from gris.www.financeiro.contas import reconciliar_e_inserir_infinitepay

CONFIG_DOCTYPE = "Configuracao infinitepay"
N_ESIMO_DIA_UTIL = 5


def _e_dia_util(dia: date) -> bool:
	"""Fim de semana ou feriado cadastrado em "Feriados" (sincronizados por `sync_feriados`)."""
	if dia.weekday() >= 5:
		return False
	return not frappe.db.exists("Feriados", {"data": dia})


def _enesimo_dia_util_do_mes(mes_de_referencia: date, n: int) -> date:
	"""Data do n-ésimo dia útil do mês de `mes_de_referencia` (qualquer dia do mês serve)."""
	dia = mes_de_referencia.replace(day=1)
	contados = 0
	while True:
		if _e_dia_util(dia):
			contados += 1
			if contados == n:
				return dia
		dia += timedelta(days=1)


def _deve_importar(config, hoje: date) -> tuple[bool, date, str | None]:
	"""Decide se o job deve seguir agora. Devolve (deve_seguir, mes_referencia, motivo_do_nao)."""
	mes_referencia = hoje.replace(day=1)

	if not config.email_account:
		return False, mes_referencia, "Conta de e-mail não configurada em Configuracao infinitepay."

	quinto_dia_util = _enesimo_dia_util_do_mes(hoje, N_ESIMO_DIA_UTIL)
	if hoje < quinto_dia_util:
		return (
			False,
			mes_referencia,
			f"Ainda não chegou o {N_ESIMO_DIA_UTIL}º dia útil do mês ({quinto_dia_util}).",
		)

	# `ultimo_mes_importado` volta do banco como string ("2026-08-01") em vez de
	# `date`; comparar direto com `mes_referencia` nunca bateria.
	if config.ultimo_mes_importado and getdate(config.ultimo_mes_importado) == mes_referencia:
		return (
			False,
			mes_referencia,
			f"Fechamento de {mes_referencia.strftime('%m/%Y')} já foi importado.",
		)

	return True, mes_referencia, None


def _buscar_comunicacoes_candidatas(config, desde: date) -> list[dict]:
	"""E-mails recebidos na conta configurada, desde o início do 5º dia útil do mês."""
	filtros = {
		"communication_medium": "Email",
		"sent_or_received": "Received",
		"email_account": config.email_account,
		"communication_date": [">=", desde],
	}
	if config.remetente_contem:
		filtros["sender"] = ["like", f"%{config.remetente_contem}%"]
	if config.assunto_contem:
		filtros["subject"] = ["like", f"%{config.assunto_contem}%"]

	return frappe.get_all(
		"Communication", filters=filtros, fields=["name"], order_by="communication_date asc"
	)


def _coletar_anexos_classificados(comunicacoes: list[dict]) -> dict[str, str]:
	"""Varre os anexos das comunicações candidatas e devolve o caminho mais recente de cada tipo.

	Comunicações mais recentes são varridas por último, então um reenvio (ex.: o
	contador corrige e reenvia o mesmo relatório) sempre prevalece sobre o anterior.
	"""
	anexos: dict[str, str] = {}
	for comunicacao in comunicacoes:
		arquivos = frappe.get_all(
			"File",
			filters={"attached_to_doctype": "Communication", "attached_to_name": comunicacao["name"]},
			fields=["name"],
		)
		for arquivo in arquivos:
			caminho = frappe.get_doc("File", arquivo["name"]).get_full_path()
			tipo = identificar_tipo_arquivo(caminho)
			if tipo:
				anexos[tipo] = caminho
	return anexos


def enqueue_infinitepay_email_import():
	"""Job diário: decide se hoje é o dia de buscar o fechamento e, se for, enfileira a busca."""
	logger = obter_logger("infinitepay_email_import")
	config = frappe.get_single(CONFIG_DOCTYPE)
	deve_seguir, _mes_referencia, motivo = _deve_importar(config, getdate())
	if not deve_seguir:
		logger.info(motivo)
		definir_resumo(motivo)
		return

	logger.info("Enfileirando a busca do fechamento Infinitepay por e-mail na fila longa.")
	definir_resumo("Busca do fechamento por e-mail enviada para a fila longa.")
	enqueue(
		"gris.api.financeiro.infinitepay_email_import.run_infinitepay_email_import",
		queue="long",
		timeout=1200,
		job_name=f"{frappe.local.site}:infinitepay-email-import",
	)


def run_infinitepay_email_import():
	"""Busca o e-mail do fechamento, identifica os anexos e insere as transações."""
	logger = obter_logger("infinitepay_email_import")
	config = frappe.get_single(CONFIG_DOCTYPE)
	deve_seguir, mes_referencia, motivo = _deve_importar(config, getdate())
	if not deve_seguir:
		logger.info(motivo)
		definir_resumo(motivo)
		return

	try:
		conta = frappe.get_doc("Email Account", config.email_account)

		try:
			conta.receive()
		except Exception:
			# Erro de conexão/POP3/IMAP não impede seguir com o que já estiver
			# sincronizado (o próprio Frappe também tenta sincronizar periodicamente).
			logger.warning(
				"Falha ao buscar novas mensagens em %s; seguindo com o que já está sincronizado.",
				config.email_account,
			)

		desde = _enesimo_dia_util_do_mes(getdate(), N_ESIMO_DIA_UTIL)
		comunicacoes = _buscar_comunicacoes_candidatas(config, desde)
		logger.info("%s e-mail(s) candidato(s) encontrados desde %s.", len(comunicacoes), desde)

		anexos = _coletar_anexos_classificados(comunicacoes)
		faltando = [tipo for tipo in (TIPO_EXTRATO, TIPO_VENDAS, TIPO_RECEBIMENTOS) if tipo not in anexos]
		if faltando:
			resumo = f"E-mail do fechamento ainda não chegou por completo (faltam: {', '.join(faltando)})."
			logger.warning(resumo)
			definir_resumo(resumo)
			return

		resultado = reconciliar_e_inserir_infinitepay(
			anexos[TIPO_EXTRATO], anexos[TIPO_VENDAS], anexos[TIPO_RECEBIMENTOS]
		)
		if not resultado.get("stats"):
			raise frappe.ValidationError(
				resultado.get("summary_text") or "Falha ao processar os anexos do fechamento."
			)

		frappe.db.set_single_value(CONFIG_DOCTYPE, "ultimo_mes_importado", mes_referencia)
		frappe.db.commit()  # nosemgrep — o marcador do mês precisa sobreviver a um rollback do job

		for secao, valores in resultado["stats"].items():
			metrica(f"{secao}_inseridas", valores.get("inserted", 0), incrementar=False)
			metrica(f"{secao}_erros", valores.get("failed", 0), incrementar=False)

		logger.info(resultado["summary_text"])
		primeira_linha = next(iter(resultado["summary_text"].splitlines()[1:2]), "")
		definir_resumo(
			f"Fechamento de {mes_referencia.strftime('%m/%Y')} importado. {primeira_linha}".strip()
		)
	except Exception:
		error_message = frappe.get_traceback()
		logger.exception("Falha na importação por e-mail do fechamento Infinitepay.")
		definir_resumo("A importação por e-mail do fechamento Infinitepay falhou.")
		frappe.log_error(error_message, "Infinitepay Email Import Failure")
		raise
