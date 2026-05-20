# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Helpers para a área Portaria (auto-criada por toda Festa)."""

from __future__ import annotations

import frappe

AREA_PORTARIA_NOME = "Portaria"


def get_coordenador_portaria(festa: str) -> dict[str, str | None]:
	"""Retorna nome, email e telefone do coordenador da Portaria da festa.

	Resolve as três variações de `tipo_coord` (Responsavel / Associado / Outro)
	e retorna um dict simples mesmo quando algum campo está vazio — o chamador
	decide o que fazer com lacunas.
	"""
	nome_doc = f"{festa} - {AREA_PORTARIA_NOME}"
	portaria = frappe.db.get_value(
		"Area da Festa",
		nome_doc,
		[
			"tipo_coord",
			"responsavel_coord",
			"associado_coord",
			"nome_coord",
			"email_coord",
			"telefone_coord",
		],
		as_dict=True,
	)
	if not portaria:
		return {"nome": None, "email": None, "telefone": None}

	if portaria.tipo_coord == "Responsavel" and portaria.responsavel_coord:
		pessoa = frappe.db.get_value(
			"Responsavel",
			portaria.responsavel_coord,
			["nome_completo", "email", "telefone"],
			as_dict=True,
		)
		if pessoa:
			return {
				"nome": pessoa.get("nome_completo") or portaria.nome_coord,
				"email": pessoa.get("email") or portaria.email_coord,
				"telefone": pessoa.get("telefone") or portaria.telefone_coord,
			}

	if portaria.tipo_coord == "Associado" and portaria.associado_coord:
		pessoa = frappe.db.get_value(
			"Associado",
			portaria.associado_coord,
			["nome_completo", "email", "telefone"],
			as_dict=True,
		)
		if pessoa:
			return {
				"nome": pessoa.get("nome_completo") or portaria.nome_coord,
				"email": pessoa.get("email") or portaria.email_coord,
				"telefone": pessoa.get("telefone") or portaria.telefone_coord,
			}

	return {
		"nome": portaria.nome_coord,
		"email": portaria.email_coord,
		"telefone": portaria.telefone_coord,
	}
