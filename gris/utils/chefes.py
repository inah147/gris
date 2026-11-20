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


def _candidatos_a_chefe(apenas_ativos: bool = False) -> list[dict]:
	filtros: dict = {"funcao": ["like", "%Chefe%"]}
	if apenas_ativos:
		filtros["status_no_grupo"] = "Ativo"
	candidates = frappe.get_all(
		"Associado",
		filters=filtros,
		fields=["name", "nome_completo", "funcao", "secao", "ramo", "telefone"],
		order_by="modified desc",
		limit_page_length=LIMITE_DE_CANDIDATOS,
	)
	return [row for row in candidates if row.get("name") and eh_funcao_chefe_de_secao(row.get("funcao"))]


def chefes_entre_candidatos(section_chiefs: list[dict], secao: str, ramo: str = "") -> list[str]:
	"""A regra de ``buscar_chefes_de_secao`` sobre uma lista de chefes já carregada.

	Serve a quem resolve a chefia de muitas seções de uma vez (ex.: o recorte da
	contribuição mensal por chefe) sem repetir a consulta por jovem.
	"""
	normalized_secao = normalizar_texto(secao)
	if normalized_secao:
		matched_by_secao = [
			row.get("name")
			for row in section_chiefs
			if row.get("name") and normalizar_texto(row.get("secao")) == normalized_secao
		]
		if matched_by_secao:
			return list(dict.fromkeys(matched_by_secao))

	normalized_ramo = normalizar_texto(ramo)
	if normalized_ramo:
		matched_by_ramo = [
			row.get("name")
			for row in section_chiefs
			if row.get("name") and normalizar_texto(row.get("ramo")) == normalized_ramo
		]
		if matched_by_ramo:
			return list(dict.fromkeys(matched_by_ramo))

	return []


def buscar_chefes_de_secao(secao: str, ramo: str = "") -> list[str]:
	"""Nomes dos ``Associado`` que chefiam a seção informada.

	Casa primeiro por ``secao``; só cai para ``ramo`` quando a seção não resolve nada.
	Devolve lista vazia quando não há chefe cadastrado — quem chama decide se isso é erro.
	"""
	section_chiefs = _candidatos_a_chefe()
	if not section_chiefs:
		return []
	return chefes_entre_candidatos(section_chiefs, secao, ramo)


def associados_chefiados_por(chefe: str, associados: list[dict]) -> set[str]:
	"""Quais dos ``associados`` (com ``name``, ``secao`` e ``ramo``) têm ``chefe`` como chefe de seção.

	É a regra de ``buscar_chefes_de_secao`` lida no sentido inverso: o jovem pertence
	ao chefe quando o chefe aparece entre os chefes resolvidos para a seção/ramo dele.
	"""
	if not chefe or not associados:
		return set()
	section_chiefs = _candidatos_a_chefe()
	if not any(row.get("name") == chefe for row in section_chiefs):
		return set()
	return {
		associado["name"]
		for associado in associados
		if chefe in chefes_entre_candidatos(section_chiefs, associado.get("secao"), associado.get("ramo"))
	}


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


def contatos_chefes_dos_beneficiarios(beneficiarios: list[dict]) -> dict[str, list[frappe._dict]]:
	"""Mapa ``name`` do beneficiário -> chefes **ativos e com telefone** da seção dele.

	Mesma regra de ``buscar_chefes_de_secao`` (seção primeiro, ramo como reserva), com uma
	consulta só para a lista inteira: a régua de vencimento resolve dezenas de jovens por
	rodada. Quem fica sem chefe recebe lista vazia — o chamador decide o que fazer.
	"""
	if not beneficiarios:
		return {}

	section_chiefs = _candidatos_a_chefe(apenas_ativos=True)
	por_nome = {row.get("name"): row for row in section_chiefs}
	por_chave: dict[tuple[str, str], list[frappe._dict]] = {}
	resultado: dict[str, list[frappe._dict]] = {}

	for beneficiario in beneficiarios:
		secao = beneficiario.get("secao") or ""
		ramo = beneficiario.get("ramo") or ""
		chave = (normalizar_texto(secao), normalizar_texto(ramo))
		if chave not in por_chave:
			contatos = []
			for nome in chefes_entre_candidatos(section_chiefs, secao, ramo):
				row = por_nome.get(nome) or {}
				telefone = (row.get("telefone") or "").strip()
				if telefone:
					contatos.append(
						frappe._dict(
							name=nome,
							nome_completo=(row.get("nome_completo") or "").strip(),
							telefone=telefone,
						)
					)
			por_chave[chave] = contatos
		resultado[beneficiario.get("name")] = por_chave[chave]

	return resultado
