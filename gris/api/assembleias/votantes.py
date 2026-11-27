# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Lista de presença: quem vota, pela regra do estatuto (art. 9º) e das configurações (RF-07).

`montar_votantes` é pura: recebe as regras, os associados já lidos e a data, e devolve
as linhas e os avisos. `aplicar_lista` junta o que foi gerado com o que a gestão mexeu à
mão: inclusões manuais ficam, e linhas removidas não voltam.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, getdate, now_datetime

from gris.api.assembleias import constantes as c
from gris.api.assembleias.padroes import configuracoes
from gris.api.assembleias.pagina import _assembleia
from gris.api.assembleias.pessoas import (
	DOCTYPE_ASSOCIADO,
	idade_em_meses,
	nome_da_pessoa,
	registro_ativo,
	separar_pessoa,
)
from gris.utils.chefes import normalizar_texto

CATEGORIA_BENEFICIARIO = "Beneficiário"
CATEGORIA_ESCOTISTA = "Escotista"
CATEGORIA_DIRIGENTE = "Dirigente"

# Ramo → campo da configuração que liga o voto por equipe e o nome da equipe.
EQUIPES_POR_RAMO = {
	"Lobinho": ("voto_por_matilha", "matilha"),
	"Escoteiro": ("voto_por_patrulha_escoteiro", "patrulha"),
	"Sênior": ("voto_por_patrulha_senior", "patrulha"),
}

ROTULO_REPRESENTADO = "representado por seu responsável legal"

ORDEM_DOS_TIPOS = (
	c.LINHA_DIRIGENTE,
	c.LINHA_ESCOTISTA,
	c.LINHA_ASSOCIADO,
	c.LINHA_JOVEM,
	c.LINHA_JOVEM_REPRESENTADO,
	c.LINHA_EQUIPE,
	c.LINHA_MANUAL,
)


def chave_da_equipe(equipe: str | None) -> str:
	"""Sem acento, sem maiúsculas e sem espaço repetido: "Patrulha  lobo" = "Patrulha Lobo"."""
	return " ".join(normalizar_texto(equipe or "").split())


def regras_de_voto(config) -> dict:
	return {
		"escotistas": cint(config.voto_escotistas),
		"dirigentes": cint(config.voto_dirigentes),
		"demais": cint(config.voto_demais_associados),
		"exigir_registro": cint(config.exigir_registro_ativo),
		"jovens": cint(config.voto_jovens),
		"idade_voto_meses": cint(config.idade_minima_voto_jovem) * 12,
		"representacao": cint(config.voto_representado_por_responsavel),
		"idade_representacao_meses": cint(config.idade_minima_representacao_meses),
		"equipes": [ramo for ramo, (campo, _n) in EQUIPES_POR_RAMO.items() if cint(config.get(campo))],
	}


def carregar_associados() -> list[dict]:
	"""Associados ativos com o que a regra precisa, numa consulta só."""
	return frappe.get_all(
		DOCTYPE_ASSOCIADO,
		filters={"status_no_grupo": "Ativo"},
		fields=[
			"name",
			"nome_completo",
			"categoria",
			"ramo",
			"equipe",
			"data_de_nascimento",
			"status",
			"validade_registro",
		],
		order_by="nome_completo asc",
	)


def _linha(nome, tipo, associado=None, ramo="", equipe="") -> dict:
	return {
		"nome": nome,
		"tipo_linha": tipo,
		"pessoa_tipo": DOCTYPE_ASSOCIADO if associado else "",
		"pessoa": associado or "",
		"ramo": ramo or "",
		"equipe": equipe or "",
		"origem": "Automática",
		"removido": 0,
	}


def montar_votantes(regras: dict, associados: list[dict], data) -> tuple[list[dict], dict]:
	"""Linhas da lista e avisos, na data da assembleia (CA-07.1 a CA-07.3)."""
	data = getdate(data)
	linhas: list[dict] = []
	vistos: set[str] = set()
	equipes: dict[str, dict[str, str]] = {ramo: {} for ramo in regras["equipes"]}
	avisos = {"registro_vencido": 0, "sem_nascimento": 0, "sem_equipe": {}}

	for a in associados:
		if a.get("name") in vistos or not a.get("nome_completo"):
			continue
		if regras["exigir_registro"] and not registro_ativo(
			a.get("status"), a.get("validade_registro"), data
		):
			avisos["registro_vencido"] += 1
			continue

		categoria = (a.get("categoria") or "").strip()
		nome = a["nome_completo"]
		linha = None
		if categoria == CATEGORIA_BENEFICIARIO:
			meses = idade_em_meses(a.get("data_de_nascimento"), data)
			if meses is None:
				avisos["sem_nascimento"] += 1
				continue
			if regras["jovens"] and meses >= regras["idade_voto_meses"]:
				linha = _linha(nome, c.LINHA_JOVEM, a["name"], a.get("ramo"), a.get("equipe"))
			elif regras["representacao"] and meses >= regras["idade_representacao_meses"]:
				linha = _linha(nome, c.LINHA_JOVEM_REPRESENTADO, a["name"], a.get("ramo"), a.get("equipe"))

			ramo = a.get("ramo") or ""
			if ramo in equipes:
				equipe = (a.get("equipe") or "").strip()
				if equipe:
					equipes[ramo].setdefault(chave_da_equipe(equipe), " ".join(equipe.split()))
				else:
					avisos["sem_equipe"][ramo] = avisos["sem_equipe"].get(ramo, 0) + 1
		elif categoria == CATEGORIA_ESCOTISTA:
			if regras["escotistas"]:
				linha = _linha(nome, c.LINHA_ESCOTISTA, a["name"], a.get("ramo"))
		elif categoria == CATEGORIA_DIRIGENTE:
			if regras["dirigentes"]:
				linha = _linha(nome, c.LINHA_DIRIGENTE, a["name"])
		elif regras["demais"]:
			linha = _linha(nome, c.LINHA_ASSOCIADO, a["name"])

		if linha:
			vistos.add(a["name"])
			linhas.append(linha)

	for ramo, por_chave in equipes.items():
		for equipe in sorted(por_chave.values(), key=chave_da_equipe):
			linhas.append(_linha(f"Representante — {equipe} ({ramo})", c.LINHA_EQUIPE, None, ramo, equipe))

	return linhas, avisos


def _chave(linha) -> str:
	if linha.get("tipo_linha") == c.LINHA_EQUIPE:
		return f"equipe|{linha.get('ramo')}|{chave_da_equipe(linha.get('equipe'))}"
	return f"{linha.get('tipo_linha')}|{linha.get('pessoa_tipo')}|{linha.get('pessoa')}"


def aplicar_lista(existentes: list[dict], geradas: list[dict]) -> list[dict]:
	"""O que a regra gera, mais as inclusões manuais, menos o que foi removido (CA-07.4).

	A ordem é alfabética.
	"""
	manuais = [dict(linha) for linha in existentes if linha.get("origem") == "Manual"]
	removidas = [
		dict(linha) for linha in existentes if linha.get("origem") != "Manual" and cint(linha.get("removido"))
	]
	chaves_removidas = {_chave(linha) for linha in removidas}
	ativas = [linha for linha in geradas if _chave(linha) not in chaves_removidas]
	# Uma removida que a regra não gera mais some de vez.
	chaves_geradas = {_chave(linha) for linha in geradas}
	removidas = [linha for linha in removidas if _chave(linha) in chaves_geradas]
	return sorted(ativas + manuais + removidas, key=lambda linha: (linha.get("nome") or "").casefold())


def totais(linhas: list[dict]) -> dict:
	ativas = [linha for linha in linhas if not cint(linha.get("removido"))]
	por_tipo = {tipo: 0 for tipo in ORDEM_DOS_TIPOS}
	for linha in ativas:
		tipo = linha.get("tipo_linha") or c.LINHA_MANUAL
		por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
	total = len(ativas)
	return {
		"por_tipo": [{"tipo": tipo, "total": n} for tipo, n in por_tipo.items() if n],
		"total": total,
		# Art. 3: em primeira convocação, a maioria absoluta dos membros com direito a voto.
		"maioria_absoluta": total // 2 + 1 if total else 0,
	}


# --------------------------------------------------------------------------------------
# Leitura e endpoints
# --------------------------------------------------------------------------------------


def _linhas_do_doc(doc) -> list[dict]:
	return [
		{
			"name": v.name,
			"nome": v.nome,
			"tipo_linha": v.tipo_linha or c.LINHA_MANUAL,
			"pessoa_tipo": v.pessoa_tipo or "",
			"pessoa": v.pessoa or "",
			"ramo": v.ramo or "",
			"equipe": v.equipe or "",
			"origem": v.origem or "Automática",
			"removido": cint(v.removido),
		}
		for v in doc.votantes
	]


def dados_da_lista(doc, config=None) -> dict:
	config = config or configuracoes()
	linhas = _linhas_do_doc(doc)
	_geradas, avisos = montar_votantes(regras_de_voto(config), carregar_associados(), doc.data)
	return {
		"modified": str(doc.modified),
		"gerada_em": str(doc.lista_gerada_em or ""),
		"editavel": getdate() <= getdate(doc.data),
		"linhas": [linha for linha in linhas if not linha["removido"]],
		"removidas": [linha for linha in linhas if linha["removido"]],
		"totais": totais(linhas),
		"avisos": avisos,
	}


def _garantir_editavel(doc) -> None:
	if getdate() > getdate(doc.data):
		frappe.throw(_("A assembleia já aconteceu: a lista de presença não pode mais mudar."))


def _gravar(doc, linhas: list[dict]) -> None:
	doc.set("votantes", [])
	for linha in linhas:
		doc.append("votantes", {campo: valor for campo, valor in linha.items() if campo != "name"})
	doc.save()


@frappe.whitelist(methods=["POST"])
def gerar_lista(name: str) -> dict:
	doc = _assembleia(name)
	_garantir_editavel(doc)
	config = configuracoes()
	geradas, _avisos = montar_votantes(regras_de_voto(config), carregar_associados(), doc.data)
	doc.lista_gerada_em = now_datetime()
	_gravar(doc, aplicar_lista(_linhas_do_doc(doc), geradas))
	return dados_da_lista(doc, config)


@frappe.whitelist(methods=["POST"])
def incluir_votante(name: str, pessoa: str | None = None, nome_livre: str | None = None) -> dict:
	"""Inclui alguém à mão: uma pessoa do cadastro ou um nome livre."""
	doc = _assembleia(name)
	_garantir_editavel(doc)
	tipo, pessoa_name = separar_pessoa(pessoa)
	nome = nome_da_pessoa(tipo, pessoa_name) if pessoa_name else " ".join((nome_livre or "").split())
	if not nome:
		frappe.throw(_("Escolha uma pessoa ou escreva o nome."))
	if len(nome) > 140:
		frappe.throw(_("O nome pode ter até 140 caracteres."))
	if pessoa_name and any(
		v.pessoa == pessoa_name and v.pessoa_tipo == tipo and not cint(v.removido) for v in doc.votantes
	):
		frappe.throw(_("{0} já está na lista.").format(nome))
	doc.append(
		"votantes",
		{
			"nome": nome,
			"tipo_linha": c.LINHA_MANUAL,
			"pessoa_tipo": tipo or None,
			"pessoa": pessoa_name or None,
			"origem": "Manual",
			"removido": 0,
		},
	)
	_gravar(doc, sorted(_linhas_do_doc(doc), key=lambda linha: linha["nome"].casefold()))
	return dados_da_lista(doc)


@frappe.whitelist(methods=["POST"])
def remover_votante(name: str, linha: str) -> dict:
	"""Manual sai da lista; automática fica marcada como removida para não voltar."""
	doc = _assembleia(name)
	_garantir_editavel(doc)
	alvo = next((v for v in doc.votantes if v.name == linha), None)
	if not alvo:
		frappe.throw(_("Linha não encontrada."))
	if alvo.origem == "Manual":
		doc.remove(alvo)
	else:
		alvo.removido = 1
	doc.save()
	return dados_da_lista(doc)


@frappe.whitelist(methods=["POST"])
def restaurar_votante(name: str, linha: str) -> dict:
	doc = _assembleia(name)
	_garantir_editavel(doc)
	alvo = next((v for v in doc.votantes if v.name == linha), None)
	if not alvo:
		frappe.throw(_("Linha não encontrada."))
	alvo.removido = 0
	doc.save()
	return dados_da_lista(doc)
