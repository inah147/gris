# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Geração de QR code (PNG) e PDF do convite para envio por e-mail."""

from __future__ import annotations

import base64
import io
import os

import frappe
import pyqrcode
from frappe.utils.pdf import get_pdf


def gerar_png(payload: str) -> bytes:
	"""Gera bytes PNG do QR code a partir do payload (UUID/hash)."""
	buf = io.BytesIO()
	pyqrcode.create(payload).png(buf, scale=8)
	return buf.getvalue()


def gerar_pdf_convite(convite, convidado, *, item_convite=None) -> bytes:
	"""Renderiza o PDF de um convite individual.

	Conteúdo: nome da festa, data, horário, nome do convidado, tipo de convite
	e o QR code. O template fica em `festas/print_format/convite_festa_qr/`.
	"""
	festa = frappe.get_doc("Festa", convite.festa)
	tipo_convite = _descobrir_tipo_convite(convite, item_convite)
	png = gerar_png(convidado.qr_code_payload)
	template_path = os.path.join(
		frappe.get_app_path("gris"),
		"festas",
		"print_format",
		"convite_festa_qr",
		"convite_festa_qr.html",
	)
	with open(template_path, encoding="utf-8") as fh:
		template = fh.read()

	html = frappe.render_template(
		template,
		{
			"festa": festa,
			"convite": convite,
			"convidado": convidado,
			"tipo_convite": tipo_convite,
			"qr_png_b64": base64.b64encode(png).decode(),
		},
	)
	return get_pdf(html)


def _descobrir_tipo_convite(convite, item_convite=None) -> str:
	"""Devolve a descrição da Opção de Convite que originou o convidado.

	Quando o pagador recebe todos, qualquer item-convite serve como referência.
	Em envio individual, o chamador pode passar o item específico via kwarg.
	"""
	if item_convite and item_convite.descricao:
		return item_convite.descricao
	for item in convite.itens or []:
		if item.eh_convite and item.descricao:
			return item.descricao
	return "Convite"
