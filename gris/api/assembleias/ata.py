# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Aba Ata: os campos e o que a tela recebe (RF-08).

A gravação automática passa por `pagina.salvar_campos`, a mesma fila da página: duas
filas disputariam o `modified` e acusariam conflito uma da outra (CA-08.3).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, get_time

from gris.api.assembleias.padroes import hora
from gris.api.assembleias.pessoas import juntar_pessoa, separar_pessoa

MARCADOR_A_CONFIRMAR = "[A CONFIRMAR"
CAMPOS_DE_TEXTO = ("anotacoes_secretario", "ata_texto")
CAMPOS_DE_HORA = ("ata_hora_inicio", "ata_hora_termino")
CAMPOS_DE_PESSOA = ("presidente", "secretario")
LIMITE_DE_TEXTO = 100_000


def contar_marcadores(texto: str | None) -> int:
	return (texto or "").count(MARCADOR_A_CONFIRMAR)


def dados_da_ata(doc) -> dict:
	return {
		"modified": str(doc.modified),
		"hora_inicio": hora(doc.ata_hora_inicio),
		"hora_termino": hora(doc.ata_hora_termino),
		"presentes": cint(doc.ata_presentes) or None,
		"presidente": juntar_pessoa(doc.presidente_tipo, doc.presidente),
		"secretario": juntar_pessoa(doc.secretario_tipo, doc.secretario),
		"anotacoes": doc.anotacoes_secretario or "",
		"texto": doc.ata_texto or "",
		"marcadores": contar_marcadores(doc.ata_texto),
		"status_geracao": doc.ata_status_geracao or "",
		"erro_geracao": doc.ata_erro_geracao or "",
		"doc_link": doc.ata_doc_link or "",
		"pdf_link": doc.ata_pdf_link or "",
	}


def aplicar_campos(doc, campos: dict) -> None:
	"""Só os campos da aba; o resto do payload é ignorado."""
	for campo in CAMPOS_DE_TEXTO:
		if campo in campos:
			texto = str(campos[campo] or "")
			if len(texto) > LIMITE_DE_TEXTO:
				frappe.throw(_("O texto passou do limite de {0} caracteres.").format(LIMITE_DE_TEXTO))
			doc.set(campo, texto)
	for campo in CAMPOS_DE_HORA:
		if campo in campos:
			valor = campos[campo]
			try:
				doc.set(campo, get_time(valor).strftime("%H:%M:%S") if valor else None)
			except Exception:
				frappe.throw(_("Horário inválido: {0}.").format(valor))
	if "ata_presentes" in campos:
		doc.ata_presentes = max(cint(campos["ata_presentes"]), 0)
	for campo in CAMPOS_DE_PESSOA:
		if campo in campos:
			tipo, name = separar_pessoa(campos[campo])
			doc.set(f"{campo}_tipo", tipo or None)
			doc.set(campo, name or None)
