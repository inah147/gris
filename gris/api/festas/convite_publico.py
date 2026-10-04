# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Link público do convite da festa (`/convite/<código>`).

É o link que vai na legenda do PDF enviado pelo WhatsApp, um por convidado: se o
arquivo não abrir, o convidado mostra o QR direto na tela do celular.

Sem login, ninguém garante que só o dono abra o link — e o mesmo vale para o PDF:
quem tem o QR entra uma vez, porque a portaria registra a entrada. O que este módulo
garante:

- o código é aleatório (32 caracteres), não derivado do QR nem do nome da linha;
- antes de mostrar o QR, a página pede os 4 últimos dígitos do WhatsApp que recebeu
  o convite, com limite de tentativas por código e por IP;
- antes da conferência a página não mostra nenhum dado pessoal, e depois mostra só
  aquele convidado — nada do pagador nem dos outros convidados do pedido;
- o link expira no dia seguinte à festa e não é indexado nem vaza pelo `Referer`.
"""

from __future__ import annotations

import base64
import hmac
import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, getdate, today

COMPRIMENTO_TOKEN = 32
PADRAO_TOKEN = re.compile(rf"^[0-9a-z]{{{COMPRIMENTO_TOKEN}}}$")
ROTA_PUBLICA = "/convite"
PREFIXO_API = "/api/method/gris.api.festas.convite_publico."
DOCTYPE_CONVIDADO = "Convidado Convite Festa"
DIGITOS_CONFERIDOS = 4
# Quem sai da festa depois da meia-noite ainda precisa do convite.
DIAS_DE_VALIDADE_APOS_A_FESTA = 1


def _mensagem_generica() -> str:
	# Sempre a mesma, para quem tenta não descobrir se errou o código, os dígitos
	# ou se o pedido não está pago.
	return _("Não foi possível abrir o convite. Confira os dígitos.")


# ─── Código do link ───────────────────────────────────────────────────────────


def token_valido(token: str | None) -> bool:
	return bool(token) and bool(PADRAO_TOKEN.match(token))


def gerar_token() -> str:
	return frappe.generate_hash(length=COMPRIMENTO_TOKEN).lower()


def obter_token_link(convidado_row: str) -> str:
	"""Código do convidado; gera no primeiro uso (convidados de antes do link)."""
	atual = frappe.db.get_value(DOCTYPE_CONVIDADO, convidado_row, "token_link")
	if atual:
		return atual
	token = gerar_token()
	# Direto na linha: salvar o Convite Festa reescreveria os valores dos itens a
	# partir da Opção de Convite atual.
	frappe.db.set_value(DOCTYPE_CONVIDADO, convidado_row, "token_link", token, update_modified=False)
	return token


def url_convite(convidado_row: str) -> str:
	"""Link público absoluto do convite. Funciona dentro de job (sem request)."""
	from gris.api.festas.convite_confirmado import _site_base_url

	return f"{_site_base_url().rstrip('/')}{ROTA_PUBLICA}/{obter_token_link(convidado_row)}"


# ─── Leitura ──────────────────────────────────────────────────────────────────


def _so_digitos(valor: str | None) -> str:
	return re.sub(r"\D", "", valor or "")


def carregar_convite(token: str | None) -> frappe._dict | None:
	"""Convite, convidado e festa do código, ou `None` quando a página não deve existir.

	`None` para código malformado ou inexistente, pedido não pago, venda presencial
	(entra na hora, sem convite para mostrar) e convidado sem telefone (não há dígitos
	a conferir, e o convite nem foi pelo WhatsApp). Festa que já passou devolve os
	dados com `expirado=True`, para a página explicar em vez de dar 404.
	"""
	from gris.festas.doctype.convite_festa.convite_festa import STATUS_PAGAMENTO_PAGO

	if not token_valido(token):
		return None
	row = frappe.db.get_value(
		DOCTYPE_CONVIDADO,
		{"token_link": token, "parenttype": "Convite Festa"},
		["name", "parent"],
		as_dict=True,
	)
	if not row:
		return None

	convite = frappe.get_doc("Convite Festa", row.parent)
	if convite.presencial or convite.status_pagamento != STATUS_PAGAMENTO_PAGO:
		return None
	convidado = next((c for c in convite.convidados if c.name == row.name), None)
	if not convidado or not convidado.qr_code_payload:
		return None
	if len(_so_digitos(convidado.telefone)) < DIGITOS_CONFERIDOS:
		return None

	festa = frappe.db.get_value(
		"Festa",
		convite.festa,
		["name", "nome_festa", "data", "horario_inicio", "horario_termino"],
		as_dict=True,
	)
	if not festa:
		return None
	expirado = bool(festa.data) and getdate(today()) > add_days(
		getdate(festa.data), DIAS_DE_VALIDADE_APOS_A_FESTA
	)
	return frappe._dict(convite=convite, convidado=convidado, festa=festa, expirado=expirado)


def _digitos_conferem(telefone: str | None, digitos: str | None) -> bool:
	esperado = _so_digitos(telefone)[-DIGITOS_CONFERIDOS:]
	informado = _so_digitos(digitos)
	if len(esperado) != DIGITOS_CONFERIDOS or len(informado) != DIGITOS_CONFERIDOS:
		return False
	return hmac.compare_digest(esperado, informado)


def _convite_autorizado(token: str | None, digitos: str | None) -> frappe._dict:
	dados = carregar_convite(token)
	if not dados or dados.expirado or not _digitos_conferem(dados.convidado.telefone, digitos):
		frappe.throw(_mensagem_generica(), frappe.PermissionError)
	return dados


def horario_da_festa(festa) -> str:
	from gris.www.festas.convite_confirmado import _formatar_horario

	inicio = _formatar_horario(festa.horario_inicio)
	termino = _formatar_horario(festa.horario_termino)
	if inicio and termino:
		return f"{inicio} às {termino}"
	return inicio


# ─── Endpoints ────────────────────────────────────────────────────────────────


# Público por necessidade: o convidado não tem login. Exige o código do link e os
# 4 últimos dígitos do telefone, com limite de tentativas por código (todos os IPs
# somados) e por IP. Devolve só o convite daquele convidado.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep
@rate_limit(key="token", limit=10, seconds=15 * 60, ip_based=False)
@rate_limit(limit=30, seconds=10 * 60)
def abrir_convite(token: str | None = None, digitos: str | None = None) -> dict:
	"""QR code e dados do convite, depois de conferir os 4 dígitos."""
	from gris.festas.utils.convite_qr import _descobrir_tipo_convite, gerar_png
	from gris.www.festas.convite_confirmado import _formatar_data

	dados = _convite_autorizado(token, digitos)
	png = gerar_png(dados.convidado.qr_code_payload)
	return {
		"nome": dados.convidado.nome,
		"tipo_convite": _descobrir_tipo_convite(dados.convite),
		"festa": dados.festa.nome_festa or dados.festa.name,
		"data": _formatar_data(dados.festa.data),
		"horario": horario_da_festa(dados.festa),
		"qr_png_b64": base64.b64encode(png).decode(),
	}


# Mesmo acesso de `abrir_convite`: código + 4 dígitos, com os mesmos limites.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep
@rate_limit(key="token", limit=10, seconds=15 * 60, ip_based=False)
@rate_limit(limit=30, seconds=10 * 60)
def baixar_convite_pdf(token: str | None = None, digitos: str | None = None) -> None:
	"""O mesmo PDF do e-mail e do WhatsApp, para baixar pela página."""
	from gris.festas.doctype.convite_festa.convite_festa import _safe_filename
	from gris.festas.utils import convite_qr

	dados = _convite_autorizado(token, digitos)
	frappe.local.response.filename = _safe_filename(dados.festa.nome_festa, dados.convidado.nome)
	frappe.local.response.filecontent = convite_qr.gerar_pdf_convite(dados.convite, dados.convidado)
	frappe.local.response.type = "pdf"


def proteger_resposta(response, request) -> None:
	"""Hook `after_request`: o código do link não pode vazar, ser indexado nem ir para cache.

	Vale para a página e para os endpoints, que devolvem o QR.
	"""
	if response is None or request is None:
		return
	caminho = request.path or ""
	if not (caminho.startswith(f"{ROTA_PUBLICA}/") or caminho.startswith(PREFIXO_API)):
		return
	response.headers["Referrer-Policy"] = "no-referrer"
	response.headers["X-Robots-Tag"] = "noindex, nofollow"
	response.headers["Cache-Control"] = "no-store"
