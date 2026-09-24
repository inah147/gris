"""Leituras da estrutura da UEL: áreas, funções e quem as ocupa.

Tudo é montado em poucas consultas agregadas, nunca uma por linha: as duas telas
listam a estrutura inteira de uma vez.
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate

from gris.api.gestao_adultos import identidade


def listar_unidades() -> list[dict]:
	"""Todas as áreas, com hierarquia, responsável e as funções vinculadas."""
	areas = frappe.get_all(
		"Unidade Organizacional",
		fields=[
			"name",
			"area",
			"responde_para",
			"responsavel",
			"tipo_responsavel",
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
	# O líder sai daqui como **chave** (`associado:` / `responsavel:`): é o mesmo valor das
	# opções do seletor, e é o que distingue o par homônimo dos dois cadastros.
	lideres = {a["name"]: identidade.chave_do_lider(a) for a in areas}
	nomes = _nomes_dos_responsaveis({chave for chave in lideres.values() if chave})

	return [
		{
			"name": area["name"],
			"area": area["area"],
			"responde_para": area["responde_para"],
			"responsavel": lideres[area["name"]],
			"responsavel_nome": nomes.get(lideres[area["name"]]),
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
	"""Quem pode liderar uma área — o mesmo recorte do controller.

	São os dois tipos de pessoa do organograma: o quadro de associados ativos e os
	responsáveis legais **sem** cadastro de associado. Quem tem os dois cadastros entra uma
	vez só, pelo lado do associado, que é o registro que vale para essa pessoa (ver
	`gris.api.pessoas`) — listar os dois deixaria duas linhas iguais na busca e uma delas
	desenharia a área sem líder.

	O valor é a chave com espaço de nomes, não o `name`: os dois DocTypes derivam o `name`
	do mesmo md5 de CPF, e sem o prefixo o homônimo do outro cadastro seria gravado no
	lugar da pessoa escolhida.

	A primeira opção é vazia e não é enfeite: ao inicializar, o select do design
	system seleciona sozinho a primeira opção, e em silêncio. Sem ela, abrir uma
	área sem responsável mostraria a primeira pessoa da lista como se fosse a
	responsável — e o save gravaria isso.
	"""
	associados = frappe.get_all(
		"Associado",
		filters={"categoria": ["!=", "Beneficiário"], "status_no_grupo": "Ativo"},
		fields=["name", "nome_completo"],
		order_by="nome_completo asc",
	)
	responsaveis = frappe.get_all(
		"Responsavel",
		filters={"migrado_para_associado": 0},
		fields=["name", "nome_completo"],
		order_by="nome_completo asc",
	)

	opcoes = [
		{
			"value": identidade.chave_do_associado(p["name"]),
			"label": p["nome_completo"],
			"ordem": p["nome_completo"],
		}
		for p in associados
		if p["nome_completo"]
	]
	opcoes += [
		{
			"value": identidade.chave_do_responsavel(p["name"]),
			# O sufixo diz de onde a pessoa vem: sem ele, dois nomes parecidos na busca
			# não teriam como ser distinguidos.
			"label": f"{p['nome_completo']} · responsável legal",
			"ordem": p["nome_completo"],
		}
		for p in responsaveis
		if p["nome_completo"]
	]
	opcoes.sort(key=lambda opcao: opcao["ordem"])

	return [
		{"value": "", "label": "Sem responsável"},
		*({"value": o["value"], "label": o["label"]} for o in opcoes),
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


def _nomes_dos_responsaveis(chaves: set[str]) -> dict[str, str]:
	"""Nome de exibição de cada líder, indexado pela chave com espaço de nomes.

	Uma consulta por DocType, nunca uma por área: são duas no pior caso.
	"""
	if not chaves:
		return {}

	por_doctype: dict[str, list[str]] = {}
	for chave in chaves:
		doctype, name = identidade.separar(chave)
		por_doctype.setdefault(doctype, []).append(name)

	nomes: dict[str, str] = {}
	for doctype, lista in por_doctype.items():
		for p in frappe.get_all(
			doctype, filters={"name": ["in", sorted(lista)]}, fields=["name", "nome_completo"]
		):
			nomes[identidade.chave(doctype, p["name"])] = p["nome_completo"] or p["name"]
	return nomes
