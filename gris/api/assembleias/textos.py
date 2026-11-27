# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Variáveis dos textos das assembleias: edital, títulos da pauta e modelo de ata.

A troca é a mesma da régua de vencimento (`{nome}` por um dicionário fechado, sem
`str.format` nem Jinja): texto editado pela gestão nunca vira código.
"""

from __future__ import annotations

import re

import frappe
from frappe import _

from gris.api.associados_vencimento_modelos import substituir

VARIAVEIS = frozenset(
	{
		"tipo",
		"tipo_minusculo",
		"data",
		"data_curta",
		"hora_primeira",
		"hora_segunda",
		"local",
		"nome_uel",
		"numeral",
		"cnpj",
		"endereco_sede",
		"cidade",
		"data_publicacao",
		"diretor_presidente",
		"ano",
		"ano_anterior",
		"gestao",
		"data_assembleia_anterior",
	}
)

_VARIAVEL = re.compile(r"\{(\w+)\}")
_CODIGO_DE_TEMPLATE = re.compile(r"\{\{|\}\}|\{%|%\}")


def variaveis_desconhecidas(texto: str | None) -> list[str]:
	"""Variáveis usadas no texto que não existem, na ordem em que aparecem."""
	usadas = _VARIAVEL.findall(texto or "")
	return list(dict.fromkeys(nome for nome in usadas if nome not in VARIAVEIS))


def lista_de_variaveis() -> str:
	return ", ".join(f"{{{nome}}}" for nome in sorted(VARIAVEIS))


def validar_texto(texto: str | None, rotulo: str) -> None:
	"""Recusa no save o texto que sairia com `{variavel}` crua no documento."""
	if _CODIGO_DE_TEMPLATE.search(texto or ""):
		frappe.throw(
			_(
				"“{0}” só aceita variáveis no formato {{variavel}}. Remova os trechos com {{{{ }}}} ou {{% %}}."
			).format(rotulo)
		)
	desconhecidas = variaveis_desconhecidas(texto)
	if desconhecidas:
		frappe.throw(
			_("“{0}” usa {1}, que não existe. As variáveis aceitas são: {2}.").format(
				rotulo,
				", ".join(f"{{{nome}}}" for nome in desconhecidas),
				lista_de_variaveis(),
			)
		)
