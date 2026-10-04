# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Página pública da contribuição mensal (`/contribuicao/<código>`).

É o endereço que o WhatsApp leva: um por beneficiário, sempre o mesmo. A página
mostra o mês a mês e entrega o link da InfinitePay com o valor do dia, o que
resolve o "novo link depois do vencimento" sem mudar o que foi enviado.

Quem tem o código vê o nome do beneficiário e a situação dos pagamentos — nada de
contato (telefone, e-mail, CPF, responsável). Competências e valores nunca vêm do
cliente: saem da mesma apuração que a tela do financeiro usa.
"""

from __future__ import annotations

import datetime

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import getdate

from gris.api.financeiro.cobranca_contribuicao import cobranca_vigente
from gris.api.financeiro.contribuicao_token import (
	ROTA_PUBLICA,
	associado_do_token,
	regenerar_token,
	url_publica,
)
from gris.api.financeiro.contribuicoes import ROLE_GESTOR, calcular_vencimento, get_parametros
from gris.api.financeiro.pagamentos_contribuicao import (
	STATUS_ATRASADO,
	STATUS_EM_ABERTO,
	STATUS_NAO_GERADO,
	apurar_associados,
	competencias_pendentes,
)

MESES_EXIBIDOS = 12

ESTADO_EM_ABERTO = "em_aberto"
ESTADO_VENCIDO = "vencido"
ESTADO_PAGO = "pago"


def montar_pagina(token: str | None, hoje: datetime.date | None = None) -> dict | None:
	"""Dados da página do código, ou `None` quando o código não existe."""
	associado = associado_do_token(token)
	if not associado:
		return None

	hoje = hoje or getdate()
	apuracoes = apurar_associados([associado], MESES_EXIBIDOS, hoje)
	if not apuracoes:
		return None
	apuracao = apuracoes[0]
	parametros = get_parametros()

	pendentes = competencias_pendentes(apuracao)
	ym_pendentes = {p["ym"] for p in pendentes}
	vencidos = [p for p in pendentes if p["status"] == STATUS_ATRASADO]

	meses = [
		{
			"ym": linha["ym"],
			"rotulo": linha["rotulo"],
			"status": linha["status"],
			"status_slug": linha["status_slug"],
			"valor": linha["valor"],
			"acrescimo": linha.get("acrescimo_atraso", 0.0),
			"pendente": linha["ym"] in ym_pendentes,
		}
		for linha in reversed(apuracao["linhas"])
		if linha["status"] != STATUS_NAO_GERADO
	]

	if not pendentes:
		estado = ESTADO_PAGO
	elif vencidos:
		estado = ESTADO_VENCIDO
	else:
		estado = ESTADO_EM_ABERTO

	vencimentos = [
		calcular_vencimento(getdate(f"{p['ym']}-01"), parametros.dia_vencimento)
		for p in pendentes
		if p["status"] == STATUS_EM_ABERTO
	]
	return {
		"nome": apuracao["nome"],
		"estado": estado,
		"meses": meses,
		"total_pendente": round(sum(p["valor"] for p in pendentes), 2),
		"acrescimo_pendente": round(
			sum(m["acrescimo"] for m in meses if m["pendente"]),
			2,
		),
		"meses_em_atraso": len(vencidos),
		"vencimento": min(vencimentos) if vencimentos else None,
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep
@rate_limit(key="contribuicao-publica-pagar", limit=10, seconds=60)
def iniciar_pagamento(token: str | None = None) -> dict:
	"""Devolve o link da InfinitePay com o valor de hoje do que está em aberto.

	Só aceita o código: competências e valores vêm da apuração, nunca do cliente.
	"""
	associado = associado_do_token(token)
	if not associado:
		frappe.throw(_("Página indisponível"), frappe.PageDoesNotExistError)

	cobranca = cobranca_vigente(associado)
	if not cobranca:
		frappe.throw(_("Não há contribuição em aberto para pagar."), frappe.ValidationError)
	return {"link_pagamento": cobranca["link_pagamento"]}


@frappe.whitelist(allow_guest=True)  # nosemgrep
@rate_limit(key="contribuicao-publica-status", limit=30, seconds=60)
def get_status(token: str | None = None) -> dict:
	"""Só o estado e o total pendente, para a página conferir o pagamento ao voltar."""
	pagina = montar_pagina(token)
	if not pagina:
		frappe.throw(_("Página indisponível"), frappe.PageDoesNotExistError)
	return {"estado": pagina["estado"], "total_pendente": pagina["total_pendente"]}


def _assert_gestor() -> None:
	if ROLE_GESTOR not in frappe.get_roles():
		frappe.throw(
			_("Requer acesso Gestor Contribuição Mensal para esta ação."),
			frappe.PermissionError,
		)


@frappe.whitelist(methods=["POST"])
def get_link_da_familia(associado: str) -> dict:
	"""Link público do beneficiário, para o gestor copiar."""
	_assert_gestor()
	return {"link": url_publica(associado)}


@frappe.whitelist(methods=["POST"])
def regenerar_link_da_familia(associado: str) -> dict:
	"""Troca o código do beneficiário; o link anterior deixa de funcionar."""
	regenerar_token(associado)
	return {"link": url_publica(associado)}


def proteger_resposta(response, request) -> None:
	"""Hook `after_request`: o código do link não pode vazar nem ser indexado.

	`Referrer-Policy: no-referrer` evita que o código siga no `Referer` quando a
	página leva o responsável à InfinitePay, e `X-Robots-Tag` mantém a página fora
	dos buscadores.
	"""
	if response is None or request is None:
		return
	if not (request.path or "").startswith(f"{ROTA_PUBLICA}/"):
		return
	response.headers["Referrer-Policy"] = "no-referrer"
	response.headers["X-Robots-Tag"] = "noindex, nofollow"
	response.headers["Cache-Control"] = "no-store"
