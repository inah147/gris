# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Resolução de chefes de seção a partir do cadastro de ``Associado``.

Ser chefe de seção não é um vínculo modelado: é o texto livre de ``Associado.funcao``
contendo "chefe" e "seção", combinado com ``secao`` (texto livre) ou ``ramo`` (Select).
A comparação ignora acentos e caixa porque as três colunas vêm de importação de planilha.

Este módulo é a única definição da regra — ``gestao_de_projetos`` (aprovação de projeto por
chefe de seção) e ``recepcao_mensagens`` (menção no grupo de chefes) consomem daqui.
"""

from __future__ import annotations

import unicodedata

import frappe

LIMITE_DE_CANDIDATOS = 500


def normalizar_texto(value: str | None) -> str:
	"""Minúsculas sem acento, para comparar valores digitados à mão."""
	text = (value or "").strip().lower()
	if not text:
		return ""
	decomposed = unicodedata.normalize("NFKD", text)
	return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def eh_funcao_chefe_de_secao(value: str | None) -> bool:
	"""True quando a função descreve uma chefia de seção ("Chefe de Seção", "Chefe da Seção"…)."""
	normalized = normalizar_texto(value)
	return "chefe" in normalized and "secao" in normalized


def _candidatos_a_chefe() -> list[dict]:
	candidates = frappe.get_all(
		"Associado",
		filters={"funcao": ["like", "%Chefe%"]},
		fields=["name", "nome_completo", "funcao", "secao", "ramo", "telefone"],
		order_by="modified desc",
		limit_page_length=LIMITE_DE_CANDIDATOS,
	)
	return [row for row in candidates if row.get("name") and eh_funcao_chefe_de_secao(row.get("funcao"))]


def buscar_chefes_de_secao(secao: str, ramo: str = "") -> list[str]:
	"""Nomes dos ``Associado`` que chefiam a seção informada.

	Casa primeiro por ``secao``; só cai para ``ramo`` quando a seção não resolve nada.
	Devolve lista vazia quando não há chefe cadastrado — quem chama decide se isso é erro.
	"""
	section_chiefs = _candidatos_a_chefe()
	if not section_chiefs:
		return []

	normalized_secao = normalizar_texto(secao)
	if normalized_secao:
		matched_by_secao = [
			row.get("name")
			for row in section_chiefs
			if normalizar_texto(row.get("secao")) == normalized_secao
		]
		matched_by_secao = [name for name in matched_by_secao if name]
		if matched_by_secao:
			return list(dict.fromkeys(matched_by_secao))

	normalized_ramo = normalizar_texto(ramo)
	if normalized_ramo:
		matched_by_ramo = [
			row.get("name") for row in section_chiefs if normalizar_texto(row.get("ramo")) == normalized_ramo
		]
		matched_by_ramo = [name for name in matched_by_ramo if name]
		if matched_by_ramo:
			return list(dict.fromkeys(matched_by_ramo))

	return []


def buscar_contatos_chefes_por_ramo(ramos: list[str] | tuple[str, ...]) -> dict[str, list[frappe._dict]]:
	"""Mapa ramo -> chefes daquele ramo, com nome e telefone.

	Uma consulta só para todos os ramos pedidos: as mensagens do fluxo de recepção mencionam
	um chefe por jovem e um ``get_all`` por jovem seria N+1.
	Chefes sem telefone entram no mapa mesmo assim — só não podem ser mencionados.
	"""
	if not ramos:
		return {}

	section_chiefs = _candidatos_a_chefe()
	if not section_chiefs:
		return {}

	por_ramo: dict[str, list[frappe._dict]] = {}
	for ramo in ramos:
		normalized_ramo = normalizar_texto(ramo)
		if not normalized_ramo:
			continue
		encontrados = [
			frappe._dict(
				{
					"name": row.get("name"),
					"nome_completo": (row.get("nome_completo") or "").strip(),
					"telefone": (row.get("telefone") or "").strip(),
				}
			)
			for row in section_chiefs
			if normalizar_texto(row.get("ramo")) == normalized_ramo
		]
		if encontrados:
			por_ramo[ramo] = encontrados

	return por_ramo
