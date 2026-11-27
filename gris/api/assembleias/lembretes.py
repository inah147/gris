# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Lembretes do prazo do edital no grupo da Diretoria (spec RF-14).

O prazo é a data da assembleia menos `dias_limite_edital` (30, pelo estatuto). Os marcos
contam até o prazo: 60, 30, 25 e 7 dias antes dele. Cada marco tem uma janela, como na
régua de vencimento: um dia sem rodada é recuperado no dia seguinte, e o texto sempre
mostra os dias reais. O edital publicado encerra os lembretes.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, get_url, getdate, today

from gris.api.assembleias import constantes as c
from gris.api.assembleias.padroes import data_por_extenso
from gris.api.assembleias.textos import substituir
from gris.utils.job_logger import definir_resumo, metrica, obter_logger

NOME_LOGGER = "assembleias_lembretes"
ASSUNTO = "Prazo do edital da assembleia"
DESTINATARIO = "Grupo da diretoria"

# Marco → janela de d (dias até o prazo), do maior para o menor.
JANELAS = ((60, 31, 60), (30, 26, 30), (25, 8, 25), (7, 0, 7))


def marco_do_edital(dias: int, ultimo: int | None) -> int | None:
	"""O marco a enviar hoje, ou None (CA-14.2).

	Sai o marco cuja janela contém `dias`, e só se ele vier depois do último enviado.
	"""
	for marco, de, ate in JANELAS:
		if de <= dias <= ate:
			if ultimo and marco >= ultimo:
				return None
			return marco
	return None


def mensagem(doc, prazo, dias: int) -> str:
	faltam = (
		"o prazo termina *hoje*"
		if dias == 0
		else f"falta{'m' if dias != 1 else ''} *{dias}* dia{'s' if dias != 1 else ''}"
	)
	corpo = substituir(
		c.MENSAGEM_LEMBRETE_EDITAL,
		{
			"tipo_minusculo": (doc.tipo or "").lower(),
			"data": data_por_extenso(doc.data),
			"prazo_edital": data_por_extenso(prazo),
			"faltam": faltam,
			"link": get_url(f"/administracao/assembleias/assembleia?name={doc.name}"),
		},
	)
	return f"{corpo}\n\n{c.ASSINATURA_AUTOMATICA}"


def enfileirar_lembretes() -> None:
	"""Scheduler diário (9h): só enfileira a rodada na fila longa."""
	frappe.enqueue("gris.api.assembleias.lembretes.lembrar_publicacao_edital", queue="long", timeout=900)


def lembrar_publicacao_edital(hoje=None) -> dict:
	from gris.utils.whatsapp import enviar_para_grupo

	logger = obter_logger(NOME_LOGGER)
	hoje = getdate(hoje or today())
	config = frappe.get_single(c.DOCTYPE_CONFIGURACOES)
	grupo = (config.grupo_diretoria_whatsapp or "").strip()
	if not grupo:
		motivo = (
			"Sem grupo da Diretoria em Configurações de Assembleias: nenhum lembrete do edital foi enviado."
		)
		definir_resumo(motivo)
		return {"enviados": 0, "motivo": motivo}
	if not cint(frappe.db.get_single_value("Configuracoes WhatsApp", "habilitar_integracao")):
		motivo = "Integração WhatsApp desabilitada: nenhum lembrete do edital foi enviado."
		definir_resumo(motivo)
		return {"enviados": 0, "motivo": motivo}

	dias_limite = cint(config.dias_limite_edital) or 30
	assembleias = frappe.get_all(
		c.DOCTYPE_ASSEMBLEIA,
		filters={"data": [">=", hoje], "edital_publicado": 0},
		fields=["name"],
	)
	metrica("assembleias_avaliadas", len(assembleias), incrementar=False)
	enviados = 0
	for linha in assembleias:
		doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, linha.name)
		prazo = add_days(doc.data, -dias_limite)
		dias = (getdate(prazo) - hoje).days
		marco = marco_do_edital(dias, cint(doc.lembrete_edital_marco) or None)
		if not marco:
			continue
		try:
			enviar_para_grupo(
				grupo,
				mensagem(doc, prazo, dias),
				enqueue=False,
				contexto={"assunto": ASSUNTO, "destinatario_tipo": DESTINATARIO, "destinatario_nome": ""},
			)
		except Exception:
			# Sem carimbo: a próxima rodada tenta de novo (CA-14.4).
			logger.exception(f"Falha no lembrete do edital da assembleia {doc.name}.")
			metrica("falhas_no_envio")
			frappe.log_error(frappe.get_traceback(), f"Lembrete do edital: {doc.name}")
			continue
		frappe.db.set_value(
			c.DOCTYPE_ASSEMBLEIA,
			doc.name,
			{"lembrete_edital_marco": marco, "lembrete_edital_em": hoje},
			update_modified=False,
		)
		# Commit por envio: a mensagem já saiu, e uma falha adiante não pode desfazer o
		# carimbo — senão o grupo receberia o mesmo lembrete amanhã.
		frappe.db.commit()  # nosemgrep
		enviados += 1
		metrica(f"enviados_{marco}")

	definir_resumo(
		f"{enviados} lembrete(s) do edital enviados; {len(assembleias)} assembleia(s) avaliada(s)."
	)
	return {"enviados": enviados}
