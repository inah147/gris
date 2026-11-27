# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Pessoas nas assembleias: idade, registro, ocupantes de função e opções de combobox.

Pessoa é um par tipo + nome (`Associado` ou `Responsavel`). Responsável e Associado da
mesma pessoa compartilham o `name` (md5 do CPF): quem é as duas coisas aparece uma vez
só, como Associado.
"""

from __future__ import annotations

from datetime import date

import frappe
from frappe.utils import getdate

DOCTYPE_ASSOCIADO = "Associado"
DOCTYPE_RESPONSAVEL = "Responsavel"
STATUS_REGISTRO_VALIDO = "Válido"


def idade_em_meses(nascimento, referencia) -> int | None:
	"""Meses completos de vida na data de referência; None sem data de nascimento."""
	if not nascimento:
		return None
	nascimento = getdate(nascimento)
	referencia = getdate(referencia)
	meses = (referencia.year - nascimento.year) * 12 + (referencia.month - nascimento.month)
	if referencia.day < nascimento.day:
		meses -= 1
	return meses


def idade_em_anos(nascimento, referencia) -> int | None:
	meses = idade_em_meses(nascimento, referencia)
	return None if meses is None else meses // 12


def registro_ativo(status: str | None, validade, referencia) -> bool:
	"""`status` Válido e validade alcançando a data. O status sozinho fica velho entre
	uma importação do Paxtu e outra."""
	if status != STATUS_REGISTRO_VALIDO:
		return False
	return not validade or getdate(validade) >= getdate(referencia)


def contar_associados_com_registro_ativo(referencia) -> int:
	linhas = frappe.get_all(
		DOCTYPE_ASSOCIADO,
		filters={"status_no_grupo": "Ativo", "status": STATUS_REGISTRO_VALIDO},
		fields=["validade_registro"],
	)
	return sum(
		1 for linha in linhas if registro_ativo(STATUS_REGISTRO_VALIDO, linha.validade_registro, referencia)
	)


def ocupantes_da_funcao(funcao: str, referencia=None) -> list[str]:
	"""Nomes de quem exerce a função na data (lotação sem `data_fim`, ou ainda por vir)."""
	referencia = getdate(referencia) if referencia else getdate()
	linhas = frappe.get_all(
		"Funcao do Associado",
		filters={"funcao": funcao, "parentfield": "funcoes_internas"},
		fields=["parent", "parenttype", "data_inicio", "data_fim"],
	)
	por_doctype: dict[str, list[str]] = {}
	for linha in linhas:
		if linha.data_inicio and getdate(linha.data_inicio) > referencia:
			continue
		if linha.data_fim and getdate(linha.data_fim) < referencia:
			continue
		por_doctype.setdefault(linha.parenttype, []).append(linha.parent)

	nomes: list[str] = []
	for doctype, parents in por_doctype.items():
		filtros = {"name": ["in", parents]}
		if doctype == DOCTYPE_ASSOCIADO:
			filtros["status_no_grupo"] = "Ativo"
		nomes.extend(frappe.get_all(doctype, filters=filtros, pluck="nome_completo"))
	return sorted(dict.fromkeys(nome for nome in nomes if nome))


def opcoes_de_pessoas(idade_minima: int, referencia: date | str | None = None) -> list[dict]:
	"""Associados ativos com a idade mínima e responsáveis, para os comboboxes.

	O valor é `Tipo::name`, separado na gravação. Começa com uma opção vazia: o select
	do design system escolhe sozinho a primeira opção ao inicializar.
	"""
	referencia = getdate(referencia) if referencia else getdate()
	associados = frappe.get_all(
		DOCTYPE_ASSOCIADO,
		filters={"status_no_grupo": "Ativo"},
		fields=["name", "nome_completo", "data_de_nascimento"],
	)
	opcoes = []
	nomes_de_associado = set()
	for a in associados:
		idade = idade_em_anos(a.data_de_nascimento, referencia)
		# Sem data de nascimento só entra quando não há idade mínima (inclusão manual).
		sem_idade_suficiente = (idade is None and idade_minima > 0) or (
			idade is not None and idade < idade_minima
		)
		if sem_idade_suficiente or not a.nome_completo:
			continue
		nomes_de_associado.add(a.name)
		opcoes.append({"label": a.nome_completo, "value": f"{DOCTYPE_ASSOCIADO}::{a.name}"})

	for r in frappe.get_all(DOCTYPE_RESPONSAVEL, fields=["name", "nome_completo", "migrado_para_associado"]):
		if r.migrado_para_associado or r.name in nomes_de_associado or not r.nome_completo:
			continue
		opcoes.append(
			{"label": f"{r.nome_completo} · responsável", "value": f"{DOCTYPE_RESPONSAVEL}::{r.name}"}
		)

	opcoes.sort(key=lambda o: o["label"].casefold())
	return [{"label": "Ninguém escolhido", "value": ""}, *opcoes]


def separar_pessoa(valor: str | None) -> tuple[str, str]:
	"""`Tipo::name` → (tipo, name). Valor vazio ou de outro DocType vira ("", "")."""
	tipo, _sep, name = (valor or "").partition("::")
	if tipo not in (DOCTYPE_ASSOCIADO, DOCTYPE_RESPONSAVEL) or not name:
		return "", ""
	if not frappe.db.exists(tipo, name):
		return "", ""
	return tipo, name


def juntar_pessoa(tipo: str | None, name: str | None) -> str:
	return f"{tipo}::{name}" if tipo and name else ""


def nome_da_pessoa(tipo: str | None, name: str | None) -> str:
	if not tipo or not name:
		return ""
	return frappe.db.get_value(tipo, name, "nome_completo") or ""
