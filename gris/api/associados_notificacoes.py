# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Notificacoes de lembrete para atualizacao de dados de associados."""

from __future__ import annotations

import frappe
from frappe.utils import date_diff, get_datetime, today

from gris.utils.job_logger import definir_resumo, metrica, obter_logger
from gris.utils.whatsapp import enviar_texto


def _deve_enviar_lembrete(dias_desde_importacao: int) -> bool:
	"""Aplica a regua de frequencia dos lembretes.

	- Entre 7 e 11 dias: envio em dias alternados (7, 9, 11).
	- Depois de 11 dias: envio diario.
	"""
	if dias_desde_importacao < 7:
		return False

	if dias_desde_importacao <= 11:
		return (dias_desde_importacao - 7) % 2 == 0

	return True


def _buscar_dias_desde_ultima_importacao() -> int | None:
	"""Retorna quantos dias se passaram desde a ultima importacao de associados."""
	ultima_importacao = frappe.db.get_value(
		"Log Importacao de Associados",
		filters={},
		fieldname="data_importacao",
		order_by="data_importacao desc",
	)
	if not ultima_importacao:
		return None

	return max(0, date_diff(today(), get_datetime(ultima_importacao).date()))


def _buscar_responsavel_atualizacao() -> frappe._dict | None:
	"""Busca o associado configurado como responsavel pela atualizacao."""
	associado_name = frappe.db.get_single_value(
		"Configuracoes de Associados",
		"responsavel_atualizacao",
	)
	if not associado_name:
		return None

	return frappe.db.get_value(
		"Associado",
		associado_name,
		["name", "nome_completo", "telefone"],
		as_dict=True,
	)


def _extrair_primeiro_nome(nome_completo: str | None) -> str:
	nome_normalizado = (nome_completo or "").strip()
	if not nome_normalizado:
		return "amigo"

	return nome_normalizado.split()[0]


def enviar_lembrete_atualizacao_associados() -> None:
	"""Envia lembrete de atualizacao dos associados para o responsavel configurado."""
	logger = obter_logger("associados_notificacoes")

	try:
		dias_desde_ultima_importacao = _buscar_dias_desde_ultima_importacao()
		if dias_desde_ultima_importacao is None:
			logger.info("Lembrete nao enviado: nenhuma importacao de associados encontrada.")
			definir_resumo("Nenhuma importação de associados encontrada — nada a lembrar.")
			return

		metrica("dias_desde_a_ultima_importacao", dias_desde_ultima_importacao, incrementar=False)

		if not _deve_enviar_lembrete(dias_desde_ultima_importacao):
			logger.info(
				"Lembrete nao enviado: regua sem disparo para "
				f"{dias_desde_ultima_importacao} dia(s) desde a ultima importacao."
			)
			definir_resumo(
				f"Régua sem disparo hoje ({dias_desde_ultima_importacao} dia(s) desde a última importação)."
			)
			return

		responsavel = _buscar_responsavel_atualizacao()
		if not responsavel:
			logger.warning(
				"Lembrete nao enviado: responsavel_atualizacao nao configurado "
				"em Configuracoes de Associados."
			)
			definir_resumo("Responsável pela atualização não configurado — nenhum lembrete enviado.")
			return

		telefone = (responsavel.get("telefone") or "").strip()
		if not telefone:
			logger.warning(f"Lembrete nao enviado: associado {responsavel.get('name')} sem telefone.")
			definir_resumo("Responsável configurado está sem telefone — nenhum lembrete enviado.")
			return

		primeiro_nome = _extrair_primeiro_nome(responsavel.get("nome_completo"))
		mensagem = (
			f"Oi, {primeiro_nome}!\n\n"
			f"Passando pra te lembrar que j\u00e1 fazem {dias_desde_ultima_importacao} dias desde a \u00faltima "
			"atualiza\u00e7\u00e3o dos dados dos associados no Gris, n\u00e3o se esque\u00e7a de atualizar o quanto antes\n\n"
			"_Essa \u00e9 uma mensagem autom\u00e1tica do seu amigo Gris_"
		)

		enviar_texto(telefone, mensagem)
		metrica("lembretes_enviados")
		logger.info(
			"Lembrete de atualizacao enfileirado para "
			f"{responsavel.get('name')} ({dias_desde_ultima_importacao} dia(s))."
		)
		definir_resumo(
			f"1 lembrete enviado para {responsavel.get('nome_completo') or responsavel.get('name')} "
			f"({dias_desde_ultima_importacao} dia(s) desde a última importação)."
		)

	except Exception:
		logger.exception("Falha ao enviar o lembrete de atualizacao de associados.")
		frappe.log_error(frappe.get_traceback(), "Lembrete atualizacao de associados")
