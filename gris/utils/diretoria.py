# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Quem é da Diretoria, derivado da lotação — não de papéis.

A Diretoria é quem ocupa, hoje, uma função marcada como `Eleita` ou `Nomeada` no
catálogo (`Funcao Voluntario.diretoria`). A lotação é a grade `funcoes_internas`
(`Funcao do Associado`), que existe no `Associado` e no `Responsavel`: uma linha sem
`data_fim`, ou com `data_fim` ainda por vir, está em vigor.

O Presidente e a área de Relações Institucionais são configuráveis em
`Configuracoes de Captacao`, porque os títulos variam de grupo para grupo.

Este módulo só responde o que a lotação diz. Quem passa por cima dela (o
`System Manager`) é decidido na camada de permissão de cada feature.
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate

from gris.api.gestao_adultos import identidade

DOCTYPE_CONFIGURACOES = "Configuracoes de Captacao"
DOCTYPE_LOTACAO = "Funcao do Associado"
CAMPO_DA_GRADE = "funcoes_internas"
TIPOS_DE_DIRETORIA = ("Eleita", "Nomeada")
FUNCAO_PRESIDENTE_PADRAO = "Diretor(a) Presidente"


def pessoas_do_usuario(user: str | None) -> list[str]:
	"""Chaves (`associado:…` / `responsavel:…`) de quem está logado como `user`.

	O login do associado é o id@escoteiros, não o email comum, então a busca vai pelos
	dois. O responsável é achado pelo email e também pela mesma chave do associado:
	quem é as duas coisas tem o mesmo md5 de CPF nos dois DocTypes, e a função pode ter
	sido lançada em qualquer uma das grades.
	"""
	if not user or user == "Guest":
		return []

	associados = frappe.get_all(
		identidade.DOCTYPE_ASSOCIADO,
		or_filters={"id_escoteiros": user, "email": user},
		pluck="name",
		limit_page_length=20,
	)
	responsaveis = set(
		frappe.get_all(
			identidade.DOCTYPE_RESPONSAVEL,
			filters={"email": user},
			pluck="name",
			limit_page_length=20,
		)
	)
	if associados:
		responsaveis.update(
			frappe.get_all(
				identidade.DOCTYPE_RESPONSAVEL,
				filters={"name": ["in", associados]},
				pluck="name",
			)
		)

	return [identidade.chave_do_associado(name) for name in associados] + [
		identidade.chave_do_responsavel(name) for name in sorted(responsaveis)
	]


def lotacoes_em_vigor(user: str | None, pessoas: list[str] | None = None) -> list[dict]:
	"""Funções que o usuário exerce hoje, uma por linha da grade: `{pessoa, funcao, area}`.

	`pessoas` evita repetir a busca quando quem chama já tem as chaves do usuário.
	"""
	nomes_por_doctype: dict[str, list[str]] = {}
	for chave in pessoas if pessoas is not None else pessoas_do_usuario(user):
		doctype, name = identidade.separar(chave)
		nomes_por_doctype.setdefault(doctype, []).append(name)

	hoje = getdate()
	lotacoes: list[dict] = []
	for doctype, nomes in nomes_por_doctype.items():
		for linha in frappe.get_all(
			DOCTYPE_LOTACAO,
			filters={"parenttype": doctype, "parentfield": CAMPO_DA_GRADE, "parent": ["in", nomes]},
			fields=["parent", "funcao", "area", "data_fim"],
		):
			if linha.data_fim and getdate(linha.data_fim) < hoje:
				continue
			if not linha.funcao:
				continue
			lotacoes.append(
				{
					"pessoa": identidade.chave(doctype, linha.parent),
					"funcao": linha.funcao,
					"area": linha.area or "",
				}
			)
	return lotacoes


def papeis_na_diretoria(user: str | None) -> dict:
	"""Tudo o que a lotação diz sobre o usuário, numa leitura só.

	`{pessoas, membro, presidente, relacoes_institucionais}`. O presidente conta como
	membro mesmo que a função dele ainda não tenha sido marcada como eleita.
	"""
	pessoas = pessoas_do_usuario(user)
	lotacoes = lotacoes_em_vigor(user, pessoas=pessoas) if pessoas else []
	funcoes = {lotacao["funcao"] for lotacao in lotacoes}
	areas = {lotacao["area"] for lotacao in lotacoes if lotacao["area"]}

	presidente = funcao_do_presidente() in funcoes
	area_ri = area_de_relacoes_institucionais()
	return {
		"pessoas": pessoas,
		"membro": presidente or bool(funcoes & funcoes_da_diretoria()),
		"presidente": presidente,
		"relacoes_institucionais": bool(area_ri and area_ri in areas),
	}


def funcoes_da_diretoria() -> set[str]:
	"""Títulos das funções marcadas como Diretoria eleita ou nomeada."""
	return set(
		frappe.get_all(
			"Funcao Voluntario",
			filters={"diretoria": ["in", TIPOS_DE_DIRETORIA]},
			pluck="name",
		)
	)


def funcao_do_presidente() -> str:
	return _configuracao("funcao_presidente") or FUNCAO_PRESIDENTE_PADRAO


def area_de_relacoes_institucionais() -> str:
	return _configuracao("area_relacoes_institucionais") or ""


def eh_membro_da_diretoria(user: str | None) -> bool:
	return papeis_na_diretoria(user)["membro"]


def eh_diretor_presidente(user: str | None) -> bool:
	return papeis_na_diretoria(user)["presidente"]


def eh_de_relacoes_institucionais(user: str | None) -> bool:
	"""Qualquer pessoa lotada na área de RI: o diretor nomeado e a equipe dele."""
	return papeis_na_diretoria(user)["relacoes_institucionais"]


def _configuracao(campo: str) -> str:
	if not frappe.db.exists("DocType", DOCTYPE_CONFIGURACOES):
		return ""
	return (frappe.db.get_single_value(DOCTYPE_CONFIGURACOES, campo) or "").strip()
