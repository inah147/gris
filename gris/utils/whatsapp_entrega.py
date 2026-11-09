"""Confirma se as mensagens que a Evolution aceitou chegaram ao destinatário.

"Enviada" no ``Log de Mensagem`` quer dizer só que a Evolution respondeu 201: a mensagem
entrou na fila dela. Se o WhatsApp a entregou, quem diz é o ``messages.update`` que a
Evolution guarda no banco (``DATABASE_SAVE_MESSAGE_UPDATE``) e expõe em
``/chat/findStatusMessage``. Esta rotina pergunta por cada mensagem recente e grava a
resposta no campo ``entrega``.

A consulta lê o banco da Evolution e não passa pelo WhatsApp, por isso fica fora da fila
cadenciada de envio. Grupos não entram: o WhatsApp não manda confirmação de entrega de
mensagem de grupo, e o envio já grava "Não rastreável (grupo)".
"""

from __future__ import annotations

from datetime import timedelta

import frappe
from frappe.utils import get_datetime, now_datetime

from gris.utils.job_logger import definir_resumo, metrica, obter_logger
from gris.utils.whatsapp import (
	ENTREGA_AGUARDANDO,
	LOG_DOCTYPE,
	STATUS_ENVIADA,
	_get_config,
	_post,
)
from gris.utils.whatsapp_errors import WhatsAppConfigurationError

ENTREGA_ENTREGUE = "Entregue"
ENTREGA_LIDA = "Lida"
ENTREGA_SEM_CONFIRMACAO = "Sem confirmação"
ENTREGA_ERRO = "Erro na entrega"

# Depois disso a mensagem sai da conferência: o que não chegou em três dias não vai chegar.
JANELA_DE_CONFERENCIA = timedelta(hours=72)
# Celular desligado um dia inteiro é comum; depois disso a falta de confirmação já é um aviso.
PRAZO_PARA_CONFIRMAR = timedelta(hours=24)
LIMITE_POR_RODADA = 300

_STATUS_LIDA = {"READ", "PLAYED"}


def entrega_pelos_status(status: list[str]) -> str | None:
	"""Traduz os ``messages.update`` de uma mensagem no valor do campo ``entrega``.

	Fica com o mais avançado: a Evolution grava uma linha por mudança (SERVER_ACK,
	DELIVERY_ACK, READ...), sem garantia de ordem. ``None`` quer dizer que ainda não há
	nada além do aceite pelo servidor.
	"""
	vistos = {str(s or "").upper() for s in status}
	if vistos & _STATUS_LIDA:
		return ENTREGA_LIDA
	if "DELIVERY_ACK" in vistos:
		return ENTREGA_ENTREGUE
	if "ERROR" in vistos:
		return ENTREGA_ERRO
	return None


def _status_na_evolution(config: dict, id_mensagem: str) -> list[str]:
	resposta = _post(
		f"/chat/findStatusMessage/{config['nome_instancia']}",
		{"where": {"id": id_mensagem}},
		config=config,
	)
	if not isinstance(resposta, list):
		return []
	return [linha.get("status") for linha in resposta if isinstance(linha, dict)]


def conciliar_entregas() -> None:
	"""Scheduler (de hora em hora): atualiza a entrega das mensagens das últimas 72 horas."""
	logger = obter_logger("whatsapp_entrega")
	agora = now_datetime()

	# O que passou da janela sem confirmação não vai mais ser conferido.
	vencidas = frappe.get_all(
		LOG_DOCTYPE,
		filters={
			"status": STATUS_ENVIADA,
			"entrega": ENTREGA_AGUARDANDO,
			"enviada_em": ["<", agora - JANELA_DE_CONFERENCIA],
		},
		pluck="name",
	)
	for name in vencidas:
		_gravar(name, ENTREGA_SEM_CONFIRMACAO, agora)

	try:
		config = _get_config()
	except WhatsAppConfigurationError:
		definir_resumo("Integração com o WhatsApp desligada: nada a conferir.")
		return

	pendentes = frappe.get_all(
		LOG_DOCTYPE,
		filters={
			"status": STATUS_ENVIADA,
			"entrega": ["in", [ENTREGA_AGUARDANDO, ENTREGA_SEM_CONFIRMACAO]],
			"id_mensagem": ["is", "set"],
			"enviada_em": [">=", agora - JANELA_DE_CONFERENCIA],
		},
		fields=["name", "id_mensagem", "enviada_em", "entrega"],
		order_by="enviada_em asc",
		limit=LIMITE_POR_RODADA,
	)
	metrica("conferidas", len(pendentes), incrementar=False)

	atualizadas = 0
	for linha in pendentes:
		try:
			entrega = entrega_pelos_status(_status_na_evolution(config, linha.id_mensagem))
		except Exception:
			# Evolution fora do ar: a próxima rodada tenta de novo.
			logger.exception("Falha ao consultar a entrega na Evolution; rodada interrompida.")
			metrica("falhas_na_consulta")
			break

		if entrega is None and agora - get_datetime(linha.enviada_em) >= PRAZO_PARA_CONFIRMAR:
			entrega = ENTREGA_SEM_CONFIRMACAO
		if entrega and entrega != linha.entrega:
			_gravar(linha.name, entrega, agora)
			atualizadas += 1
			metrica(entrega)

	definir_resumo(f"{atualizadas} de {len(pendentes)} mensagem(ns) com a entrega atualizada.")


def _gravar(name: str, entrega: str, quando) -> None:
	frappe.db.set_value(
		LOG_DOCTYPE,
		name,
		{"entrega": entrega, "entrega_atualizada_em": quando},
		update_modified=False,
	)
