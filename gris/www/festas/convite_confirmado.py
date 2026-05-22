"""Página pública /festas/convite_confirmado.

Renderizada após a Infinitepay redirecionar o comprador de volta ao GRIS.
O acesso é protegido por um token HMAC (gerado em
`gris.api.festas.convite_confirmado._build_token`). Sem token válido, devolve 404.

A página apresenta apenas dados não sensíveis (nome da festa, data, horário,
e-mails mascarados, link para o recibo da Infinitepay). Nenhum side-effect
(envio de WhatsApp / e-mail) acontece aqui — esses só são disparados pelo
webhook autenticado da Infinitepay.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import frappe

from gris.api.festas.convite_confirmado import (
	_is_safe_receipt_url,
	_mask_email,
	_validate_token,
)
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

STATUS_PAGO = "Pago"
STATUS_FALHA = {"Erro", "Cancelado", "Estornado", "Expirado"}


def get_context(context):
	context.title = "Pagamento confirmado"
	context.show_sidebar = False
	context.no_header = True
	context.no_footer = True

	convite_name = (frappe.form_dict.get("c") or "").strip()
	token = (frappe.form_dict.get("t") or "").strip()

	if not _validate_token(convite_name, token):
		frappe.throw("Página indisponível", frappe.PageDoesNotExistError)

	convite_row = frappe.db.get_value(
		"Convite Festa",
		convite_name,
		[
			"name",
			"festa",
			"email_pagador",
			"pagador_recebe_qr_codes",
			"cobranca_infinitepay",
		],
		as_dict=True,
	)
	if not convite_row:
		frappe.throw("Página indisponível", frappe.PageDoesNotExistError)

	festa_row = frappe.db.get_value(
		"Festa",
		convite_row.festa,
		["nome_festa", "data", "horario_inicio", "horario_termino"],
		as_dict=True,
	) or {}

	cobranca_row = {}
	if convite_row.cobranca_infinitepay:
		cobranca_row = frappe.db.get_value(
			"Cobranca Infinitepay",
			convite_row.cobranca_infinitepay,
			["status", "receipt_url"],
			as_dict=True,
		) or {}

	status = (cobranca_row.get("status") or "Pendente").strip()
	if status == STATUS_PAGO:
		estado = "pago"
	elif status in STATUS_FALHA:
		estado = "falha"
	else:
		estado = "pendente"

	receipt_url = cobranca_row.get("receipt_url") or ""
	receipt_url_safe = receipt_url if _is_safe_receipt_url(receipt_url) else ""

	uel_data = get_uel_cached() or {}

	context.estado = estado
	context.convite_name = convite_row.name
	context.convite_token = token
	context.festa = {
		"nome": festa_row.get("nome_festa") or "",
		"data": _formatar_data(festa_row.get("data")),
		"horario_inicio": _formatar_horario(festa_row.get("horario_inicio")),
		"horario_termino": _formatar_horario(festa_row.get("horario_termino")),
	}
	context.pagador_recebe_qr_codes = bool(convite_row.pagador_recebe_qr_codes)
	context.email_pagador_mascarado = _mask_email(convite_row.email_pagador)
	context.receipt_url = receipt_url_safe
	context.portal_logo = uel_data.get("logo")
	context.uel = {
		"tipo_uel": uel_data.get("tipo_uel") or "",
		"nome_da_uel": uel_data.get("nome_da_uel") or "",
		"numeral": uel_data.get("numeral") or "",
		"regiao": uel_data.get("regiao") or "",
	}


def _formatar_data(valor) -> str:
	if not valor:
		return ""
	if isinstance(valor, datetime):
		valor = valor.date()
	if isinstance(valor, date):
		return valor.strftime("%d/%m/%Y")
	return str(valor)


def _formatar_horario(valor) -> str:
	if valor is None or valor == "":
		return ""
	if isinstance(valor, timedelta):
		total = int(valor.total_seconds())
		horas, resto = divmod(total, 3600)
		minutos = resto // 60
		return f"{horas:02d}:{minutos:02d}"
	if isinstance(valor, time):
		return valor.strftime("%H:%M")
	if isinstance(valor, datetime):
		return valor.strftime("%H:%M")
	texto = str(valor).strip()
	if len(texto) >= 5:
		return texto[:5]
	return texto
