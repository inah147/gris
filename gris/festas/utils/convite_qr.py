# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Geração de QR code (PNG) e PDF do convite para envio por e-mail."""

from __future__ import annotations

import base64
import io
import os

import frappe
import qrcode
from frappe.utils.pdf import get_pdf
from PIL import Image, ImageDraw
from qrcode.constants import ERROR_CORRECT_H

# Logo de fallback (caso Definicao da UEL não tenha logo configurado).
LOGO_QR_FALLBACK_REL_PATH = ("public", "images", "icons", "logo_gris.png")

# Proporção máxima da área do QR ocupada pelo logo. Acima de ~30% começa a
# corromper a leitura mesmo com error correction H.
LOGO_QR_RATIO = 0.22


def gerar_png(payload: str, *, com_logo: bool = True) -> bytes:
	"""Gera bytes PNG do QR code a partir do payload (UUID/hash).

	Usa a lib `qrcode` (que depende do Pillow, já disponível via Frappe).
	Quando `com_logo=True` (padrão), embute o logo do Grupo no centro com
	correção de erro nível H (~30%), que tolera a obstrução causada pelo logo.
	"""
	qr = qrcode.QRCode(
		error_correction=ERROR_CORRECT_H,
		box_size=10,
		border=2,
	)
	qr.add_data(payload)
	qr.make(fit=True)
	img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")

	if com_logo:
		logo = _carregar_logo()
		if logo is not None:
			img = _sobrepor_logo(img, logo)

	buf = io.BytesIO()
	img.save(buf, format="PNG")
	return buf.getvalue()


def _carregar_logo() -> Image.Image | None:
	"""Tenta carregar o logo da UEL (Definicao da UEL.logo); cai pro logo Gris."""
	uel_logo = frappe.db.get_single_value("Definicao da UEL", "logo")
	img = _abrir_logo_url(uel_logo) if uel_logo else None
	if img is not None:
		return img
	# Fallback: logo padrão do Gris empacotado no app.
	path = os.path.join(frappe.get_app_path("gris"), *LOGO_QR_FALLBACK_REL_PATH)
	if os.path.exists(path):
		return Image.open(path).convert("RGBA")
	return None


def _abrir_logo_url(url: str) -> Image.Image | None:
	"""Resolve um File URL do Frappe em path absoluto e abre como RGBA."""
	if not url:
		return None
	path = None
	if url.startswith("/files/"):
		path = os.path.join(
			frappe.get_site_path("public", "files"), url[len("/files/") :]
		)
	elif url.startswith("/private/files/"):
		path = os.path.join(
			frappe.get_site_path("private", "files"), url[len("/private/files/") :]
		)
	if not path or not os.path.exists(path):
		return None
	try:
		return Image.open(path).convert("RGBA")
	except Exception:
		return None


def _sobrepor_logo(qr_img: Image.Image, logo: Image.Image) -> Image.Image:
	"""Cola o logo no centro do QR sobre um fundo branco *circular*.

	O fundo branco circular evita que partes pretas do QR fiquem encostadas
	no logo e quebrem a leitura, preservando o visual arredondado.
	"""
	qr_size = min(qr_img.size)
	logo_max = int(qr_size * LOGO_QR_RATIO)
	# Pillow >= 10 não tem mais Image.ANTIALIAS — usar Resampling.LANCZOS.
	resample = getattr(Image, "Resampling", Image).LANCZOS
	logo = logo.copy()
	logo.thumbnail((logo_max, logo_max), resample)

	# Diâmetro do círculo: maior dimensão do logo + padding.
	pad = max(4, max(logo.size) // 8)
	diam = max(logo.size) + pad * 2

	# Cria fundo transparente e desenha o círculo branco.
	background = Image.new("RGBA", (diam, diam), (0, 0, 0, 0))
	draw = ImageDraw.Draw(background)
	draw.ellipse((0, 0, diam - 1, diam - 1), fill=(255, 255, 255, 255))

	# Centraliza o logo no círculo.
	logo_pos = (
		(diam - logo.size[0]) // 2,
		(diam - logo.size[1]) // 2,
	)
	background.paste(logo, logo_pos, mask=logo)

	pos = (
		(qr_img.size[0] - diam) // 2,
		(qr_img.size[1] - diam) // 2,
	)
	qr_img.paste(background, pos, mask=background)
	return qr_img


def gerar_pdf_convite(convite, convidado, *, item_convite=None) -> bytes:
	"""Renderiza o PDF de um convite individual.

	Conteúdo: logo da UEL, nome da festa, data, horário, dados do convidado e
	QR code em card com sombra. O template fica em
	`festas/print_format/convite_festa_qr/`.
	"""
	festa = frappe.get_doc("Festa", convite.festa)
	tipo_convite = _descobrir_tipo_convite(convite, item_convite)
	png = gerar_png(convidado.qr_code_payload)
	uel = frappe.get_cached_doc("Definicao da UEL")
	logo_img = _carregar_logo()
	uel_logo_b64 = ""
	if logo_img is not None:
		buf = io.BytesIO()
		logo_img.save(buf, format="PNG")
		uel_logo_b64 = base64.b64encode(buf.getvalue()).decode()

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
			"uel_tipo": uel.get("tipo_uel") or "",
			"uel_nome": uel.get("nome_da_uel") or "",
			"uel_logo_b64": uel_logo_b64,
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
