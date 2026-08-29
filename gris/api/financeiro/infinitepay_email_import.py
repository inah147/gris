# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Importação automática do fechamento mensal da Infinitepay recebido por e-mail.

A Infinitepay envia, a partir do 5º dia útil do mês, um e-mail com os três
relatórios (extrato, vendas e recebimentos) usados na conciliação — hoje feita
manualmente em `/financeiro/contas` (`process_uploaded_files`). Este módulo
automatiza o mesmo fluxo: a cada execução, busca na Conta de e-mail configurada
em "Configuracao infinitepay" os e-mails candidatos do mês corrente ainda não
importados, identifica os três anexos de cada um pelo conteúdo (o cliente de
e-mail pode renomear o arquivo) e reaproveita `reconciliar_e_inserir_infinitepay`
para inserir as transações.

Cada e-mail processado com sucesso vira um registro em "Infinitepay Email
Importado" — é esse marcador (não uma data ou um mês) que decide se um e-mail já
foi tratado, então mais de um fechamento pendente (reenvio, atraso, mês anterior
que chegou fora de época) é importado no mesmo dia sem esperar o próximo mês. A
inserção em si já é idempotente por doctype de origem, então mesmo sem o
marcador rodar o job de novo não duplicaria nada — o marcador só evita reabrir e
reclassificar os mesmos anexos a cada execução.
"""

from datetime import date, timedelta

import frappe
from frappe.utils import getdate, now_datetime
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
MARCADOR_DOCTYPE = "Infinitepay Email Importado"
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


def _buscar_comunicacoes_candidatas(config, desde: date) -> list[dict]:
	"""E-mails recebidos na conta configurada, desde o início do 5º dia útil do mês corrente.

	`desde` é só o ponto de partida da busca (evita varrer a caixa de entrada
	inteira a cada execução) — não bloqueia a importação: como nenhum e-mail tem
	data futura, a busca não encontra nada antes do 5º dia útil de qualquer forma.
	"""
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


def _ja_importada(comunicacao_name: str) -> bool:
	return bool(frappe.db.exists(MARCADOR_DOCTYPE, comunicacao_name))


def _marcar_importada(comunicacao_name: str, resumo: str) -> None:
	frappe.get_doc(
		{
			"doctype": MARCADOR_DOCTYPE,
			"communication": comunicacao_name,
			"importado_em": now_datetime(),
			"resumo": resumo,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_single_value(CONFIG_DOCTYPE, "ultima_importacao_em", now_datetime())
	# O marcador precisa sobreviver a um rollback de um item seguinte no mesmo job
	# (cada e-mail é processado em sua própria transação — ver `run_infinitepay_email_import`).
	frappe.db.commit()  # nosemgrep


def _anexos_de_uma_comunicacao(comunicacao_name: str) -> dict[str, str]:
	"""Classifica os anexos de UM e-mail pelo conteúdo. Ignora o que não reconhece."""
	anexos: dict[str, str] = {}
	arquivos = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Communication", "attached_to_name": comunicacao_name},
		fields=["name"],
	)
	for arquivo in arquivos:
		caminho = frappe.get_doc("File", arquivo["name"]).get_full_path()
		tipo = identificar_tipo_arquivo(caminho)
		if tipo:
			anexos[tipo] = caminho
	return anexos


def enqueue_infinitepay_email_import():
	"""Job diário: se houver conta de e-mail configurada, enfileira a busca na fila longa."""
	logger = obter_logger("infinitepay_email_import")
	config = frappe.get_single(CONFIG_DOCTYPE)
	if not config.email_account:
		motivo = "Conta de e-mail não configurada em Configuracao infinitepay."
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
	"""Busca e-mails do fechamento ainda não importados e insere as transações de cada um."""
	logger = obter_logger("infinitepay_email_import")
	config = frappe.get_single(CONFIG_DOCTYPE)
	if not config.email_account:
		motivo = "Conta de e-mail não configurada em Configuracao infinitepay."
		logger.info(motivo)
		definir_resumo(motivo)
		return

	try:
		conta = frappe.get_doc("Email Account", config.email_account)
	except frappe.DoesNotExistError:
		logger.error("Email Account configurada (%s) não existe mais.", config.email_account)
		definir_resumo("Conta de e-mail configurada não foi encontrada.")
		raise

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
	pendentes = [c["name"] for c in comunicacoes if not _ja_importada(c["name"])]
	logger.info(
		"%s e-mail(s) candidato(s) desde %s, %s ainda não importado(s).",
		len(comunicacoes),
		desde,
		len(pendentes),
	)

	if not pendentes:
		definir_resumo("Nenhum e-mail novo do fechamento Infinitepay para importar.")
		return

	importados, incompletos, com_falha = 0, 0, 0
	for comunicacao_name in pendentes:
		try:
			anexos = _anexos_de_uma_comunicacao(comunicacao_name)
			faltando = [tipo for tipo in (TIPO_EXTRATO, TIPO_VENDAS, TIPO_RECEBIMENTOS) if tipo not in anexos]
			if faltando:
				incompletos += 1
				logger.warning(
					"E-mail %s ainda incompleto (faltam: %s) — será reavaliado na próxima execução.",
					comunicacao_name,
					", ".join(faltando),
				)
				continue

			resultado = reconciliar_e_inserir_infinitepay(
				anexos[TIPO_EXTRATO], anexos[TIPO_VENDAS], anexos[TIPO_RECEBIMENTOS]
			)
			if not resultado.get("stats"):
				raise frappe.ValidationError(
					resultado.get("summary_text") or "Falha ao processar os anexos do fechamento."
				)

			for secao, valores in resultado["stats"].items():
				metrica(f"{secao}_inseridas", valores.get("inserted", 0))
				metrica(f"{secao}_erros", valores.get("failed", 0))

			_marcar_importada(comunicacao_name, resultado["summary_text"])
			importados += 1
			logger.info("E-mail %s importado. %s", comunicacao_name, resultado["summary_text"])
		except Exception:
			com_falha += 1
			logger.exception("Falha ao importar o e-mail %s.", comunicacao_name)
			frappe.log_error(frappe.get_traceback(), "Infinitepay Email Import Failure")

	definir_resumo(
		f"{importados} e-mail(s) importado(s), {incompletos} incompleto(s) "
		f"(aguardando anexos) e {com_falha} com falha."
	)
	if com_falha:
		raise frappe.ValidationError(
			f"{com_falha} e-mail(s) do fechamento Infinitepay falharam ao importar — ver Error Log."
		)
