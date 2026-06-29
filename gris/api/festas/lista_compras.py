# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Lista de compras da festa em PDF.

Documento de apoio (não oficial) para levar ao mercado: itens previstos com
cotação de compra real escolhida, ordenados por nome, com um checkbox para
marcação manual do que já foi comprado. O pipeline espelha o do relatório da
festa (gris/api/festas/relatorio.py): Jinja + WeasyPrint, bytes devolvidos via
`frappe.local.response`.
"""

from __future__ import annotations

import base64
import io
import os

import frappe
from frappe.utils import flt, format_date, get_fullname, today

from gris.festas.utils.unidades import converter

_TEMPLATE = "templates/pages/lista_compras_pdf.html"


def _logo_uel_data_uri() -> str:
	"""Logo da UEL como data-URI PNG (sem contorno: o hero fica sobre fundo claro)."""
	from gris.festas.utils.convite_qr import _carregar_logo

	logo = _carregar_logo()
	if logo is None:
		return ""
	buf = io.BytesIO()
	logo.save(buf, format="PNG")
	return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _render_pdf_template(rel_path: str, ctx: dict) -> str:
	path = os.path.join(frappe.get_app_path("gris"), rel_path)
	with open(path, encoding="utf-8") as fh:
		return frappe.render_template(fh.read(), ctx)


def _fmt_num(val) -> str:
	"""Formata número no padrão pt-BR (até 2 casas, sem zeros à direita).

	Espelha `fmtNum` de festa.js (Intl pt-BR, maximumFractionDigits: 2).
	"""
	n = round(flt(val), 2)
	if n == int(n):
		return f"{int(n):,}".replace(",", ".")
	inteiro, _, dec = f"{n:,.2f}".partition(".")
	dec = dec.rstrip("0")
	inteiro = inteiro.replace(",", ".")
	return f"{inteiro},{dec}" if dec else inteiro


def build_lista_compras_payload(festa_name: str) -> dict:
	"""Monta o contexto do PDF da lista de compras.

	Inclui apenas itens previstos com cotação escolhida de compra real
	(`escolhida=1, doacao=0`); itens sem cotação ou doados ficam de fora.
	"""
	doc = frappe.get_doc("Festa", festa_name)

	compras = frappe.get_all(
		"Compra Festa",
		filters={"festa": festa_name, "previsto": 1},
		fields=["name", "nome_item", "unidade_compra", "quantidade_compra_final"],
	)

	rows: list[dict] = []
	if compras:
		nomes = [c.name for c in compras]
		cotacoes = frappe.get_all(
			"Cotacao Compra Festa",
			filters={
				"parenttype": "Compra Festa",
				"parent": ["in", nomes],
				"escolhida": 1,
				"doacao": 0,
			},
			fields=["parent", "quantidade", "unidade_medida"],
		)
		cot_por_compra = {c.parent: c for c in cotacoes}

		for c in compras:
			cot = cot_por_compra.get(c.name)
			if not cot:
				continue
			unidade_compra = c.unidade_compra or "unidade"
			unidade_cot = cot.unidade_medida or "unidade"
			# qtdPacote: quantidade da cotação convertida para a unidade de compra.
			# Unidades incompatíveis (mesma lógica de convertUnit no festa.js) → 0.
			try:
				qtd_pacote = converter(flt(cot.quantidade), unidade_cot, unidade_compra)
			except Exception:
				qtd_pacote = 0.0
			total = flt(c.quantidade_compra_final) * qtd_pacote
			# Especificação completa: nome + quantidade da cotação + unidade da cotação.
			especificacao = " ".join(
				p for p in [c.nome_item, _fmt_num(cot.quantidade), unidade_cot] if p
			)
			rows.append(
				{
					"especificacao": especificacao,
					"quantidade": _fmt_num(c.quantidade_compra_final),
					"total": f"{_fmt_num(total)} {unidade_compra}".strip(),
					"_ordem": (c.nome_item or "").casefold(),
				}
			)
		rows.sort(key=lambda r: r["_ordem"])

	nome_festa = doc.nome_festa or doc.name
	usuario = get_fullname()
	data_hoje = format_date(today(), "dd/MM/yyyy")
	uel = frappe.get_cached_doc("Definicao da UEL")
	return {
		"nome_festa": nome_festa,
		"data_festa": format_date(doc.data, "dd/MM/yyyy") if doc.data else "",
		"rows": rows,
		"uel_logo": _logo_uel_data_uri(),
		"uel_tipo": uel.get("tipo_uel") or "",
		"uel_nome": uel.get("nome_da_uel") or "",
		"footer_text": f"Dados da {nome_festa} extraídos por {usuario} no dia {data_hoje}",
	}


def _gerar_lista_compras_pdf_bytes(festa_name: str) -> bytes:
	from weasyprint import HTML

	ctx = build_lista_compras_payload(festa_name)
	html = _render_pdf_template(_TEMPLATE, ctx)
	base_url = frappe.get_app_path("gris", "public") + os.sep
	return HTML(string=html, base_url=base_url).write_pdf()


@frappe.whitelist()
def download_lista_compras_pdf(festa_name: str) -> None:
	"""Gera e disponibiliza a lista de compras da festa em PDF (documento de apoio)."""
	if not festa_name:
		frappe.throw("Parâmetro 'festa_name' obrigatório.", frappe.ValidationError)
	if not frappe.has_permission("Festa", "read", festa_name):
		frappe.throw("Sem permissão para acessar esta festa.", frappe.PermissionError)

	nome_festa = frappe.db.get_value("Festa", festa_name, "nome_festa") or festa_name
	frappe.local.response.filename = f"lista-compras-{frappe.scrub(nome_festa)}.pdf"
	frappe.local.response.filecontent = _gerar_lista_compras_pdf_bytes(festa_name)
	frappe.local.response.type = "pdf"
