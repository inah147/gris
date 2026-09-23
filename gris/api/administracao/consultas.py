"""Leituras da estrutura da UEL: áreas, funções e quem as ocupa.

Tudo é montado em poucas consultas agregadas, nunca uma por linha: as duas telas
listam a estrutura inteira de uma vez.
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate


def listar_unidades() -> list[dict]:
	"""Todas as áreas, com hierarquia, responsável e as funções vinculadas."""
	areas = frappe.get_all(
		"Unidade Organizacional",
		fields=[
			"name",
			"area",
			"responde_para",
			"responsavel",
			"ativa",
			"ordem",
			"origem_automatica",
			"descricao",
		],
		order_by="ordem asc, area asc",
	)
	if not areas:
		return []

	funcoes_por_area = _funcoes_por_area([a["name"] for a in areas])
	nomes = _nomes_dos_responsaveis({a["responsavel"] for a in areas if a["responsavel"]})

	return [
		{
			"name": area["name"],
			"area": area["area"],
			"responde_para": area["responde_para"],
			"responsavel": area["responsavel"],
			"responsavel_nome": nomes.get(area["responsavel"]),
			"ativa": bool(area["ativa"]),
			"ordem": area["ordem"] or 0,
			"origem_automatica": bool(area["origem_automatica"]),
			"descricao": area["descricao"],
			"funcoes": funcoes_por_area.get(area["name"], []),
		}
		for area in areas
	]


def listar_funcoes() -> list[dict]:
	"""Todas as funções, com responsabilidades, áreas e quantas pessoas as exercem."""
	funcoes = frappe.get_all(
		"Funcao Voluntario",
		fields=["name", "titulo", "categoria", "ativa", "origem_automatica", "descricao"],
		order_by="titulo asc",
	)
	if not funcoes:
		return []

	titulos = [f["name"] for f in funcoes]
	responsabilidades: dict[str, list[dict]] = {}
	for linha in frappe.get_all(
		"Responsabilidade da Funcao",
		filters={"parent": ["in", titulos], "parenttype": "Funcao Voluntario"},
		fields=["parent", "responsabilidade", "detalhe"],
		order_by="parent asc, idx asc",
	):
		responsabilidades.setdefault(linha.parent, []).append(
			{"responsabilidade": linha.responsabilidade, "detalhe": linha.detalhe or ""}
		)

	areas_por_funcao: dict[str, list[str]] = {}
	for vinculo in frappe.get_all(
		"Funcao da Area",
		filters={"parenttype": "Unidade Organizacional", "funcao": ["in", titulos]},
		fields=["parent", "funcao"],
		order_by="funcao asc, parent asc",
	):
		areas_por_funcao.setdefault(vinculo.funcao, []).append(vinculo.parent)

	pessoas = contar_pessoas_por_funcao(titulos)

	return [
		{
			"name": funcao["name"],
			"titulo": funcao["titulo"],
			"categoria": funcao["categoria"] or "",
			"ativa": bool(funcao["ativa"]),
			"origem_automatica": bool(funcao["origem_automatica"]),
			"descricao": funcao["descricao"] or "",
			"responsabilidades": responsabilidades.get(funcao["name"], []),
			"areas": areas_por_funcao.get(funcao["name"], []),
			"pessoas": pessoas.get(funcao["name"], 0),
		}
		for funcao in funcoes
	]


def contar_pessoas_por_funcao(titulos: list[str]) -> dict[str, int]:
	"""Pessoas distintas que exercem cada função hoje.

	Uma leitura só de `Funcao do Associado`, agregada em Python: a tabela tem
	centenas de linhas, e uma consulta por função seria N+1 na tela inteira.

	O corte de "hoje" é o mesmo do organograma (`lotacoes_atuais`): só está
	encerrada a linha cuja `data_fim` já passou.
	"""
	if not titulos:
		return {}

	hoje = getdate()
	por_funcao: dict[str, set[str]] = {}
	for linha in frappe.get_all(
		"Funcao do Associado",
		filters={"parenttype": "Associado", "funcao": ["in", titulos]},
		fields=["funcao", "parent", "data_fim"],
	):
		if linha.data_fim and getdate(linha.data_fim) < hoje:
			continue
		por_funcao.setdefault(linha.funcao, set()).add(linha.parent)

	return {funcao: len(pessoas) for funcao, pessoas in por_funcao.items()}


def opcoes_de_responsavel() -> list[dict]:
	"""Adultos que podem liderar uma área — o mesmo recorte do controller.

	A primeira opção é vazia e não é enfeite: ao inicializar, o select do design
	system seleciona sozinho a primeira opção, e em silêncio. Sem ela, abrir uma
	área sem responsável mostraria a primeira pessoa da lista como se fosse a
	responsável — e o save gravaria isso.
	"""
	pessoas = frappe.get_all(
		"Associado",
		filters={"categoria": ["!=", "Beneficiário"], "status_no_grupo": "Ativo"},
		fields=["name", "nome_completo"],
		order_by="nome_completo asc",
	)
	return [
		{"value": "", "label": "Sem responsável"},
		*(
			{"value": p["name"], "label": p["nome_completo"] or p["name"]}
			for p in pessoas
			if p["nome_completo"]
		),
	]


def opcoes_de_funcao() -> list[dict]:
	"""Funções ativas, para vincular a uma área."""
	return [
		{"value": f["name"], "label": f["titulo"]}
		for f in frappe.get_all(
			"Funcao Voluntario",
			filters={"ativa": 1},
			fields=["name", "titulo"],
			order_by="titulo asc",
		)
	]


def _funcoes_por_area(nomes: list[str]) -> dict[str, list[dict]]:
	por_area: dict[str, list[dict]] = {}
	for vinculo in frappe.get_all(
		"Funcao da Area",
		filters={"parenttype": "Unidade Organizacional", "parent": ["in", nomes]},
		fields=["parent", "funcao", "observacao", "idx"],
		order_by="parent asc, idx asc",
	):
		por_area.setdefault(vinculo.parent, []).append(
			{"funcao": vinculo.funcao, "observacao": vinculo.observacao or ""}
		)
	return por_area


def _nomes_dos_responsaveis(nomes: set[str]) -> dict[str, str]:
	if not nomes:
		return {}
	return {
		p["name"]: p["nome_completo"] or p["name"]
		for p in frappe.get_all(
			"Associado", filters={"name": ["in", sorted(nomes)]}, fields=["name", "nome_completo"]
		)
	}
