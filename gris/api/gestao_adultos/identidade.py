# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Identidade de uma pessoa no organograma, que pode ser `Associado` ou `Responsavel`.

`Responsavel.name` e `Associado.name` são os dois md5 de CPF, então o nome sozinho não diz
de quem se trata: sem espaço de nomes, um clique num responsável marcaria o card do
associado homônimo, e uma alocação gravaria na grade da pessoa errada.

A chave prefixada (`associado:<id>` / `responsavel:<id>`) é o que a interface já recebia no
campo `pessoa` de cada card. Aqui ela vira também a identidade **interna** da montagem da
árvore e o parâmetro dos endpoints de alocação.

Módulo sem import de nenhum irmão do pacote de propósito: `atribuicoes` e `responsaveis`
dependem dele, e os dois já se importam entre si.
"""

from __future__ import annotations

import frappe
from frappe import _

PREFIXO_RESPONSAVEL = "responsavel:"
PREFIXO_ASSOCIADO = "associado:"

DOCTYPE_ASSOCIADO = "Associado"
DOCTYPE_RESPONSAVEL = "Responsavel"

_PREFIXO_POR_DOCTYPE = {
	DOCTYPE_ASSOCIADO: PREFIXO_ASSOCIADO,
	DOCTYPE_RESPONSAVEL: PREFIXO_RESPONSAVEL,
}


def chave(doctype: str, name: str) -> str:
	"""Chave com espaço de nomes de uma pessoa do organograma."""
	prefixo = _PREFIXO_POR_DOCTYPE.get(doctype)
	if not prefixo:
		frappe.throw(_("{0} não é um tipo de pessoa do organograma.").format(doctype))
	return f"{prefixo}{name}"


def chave_do_associado(name: str) -> str:
	return f"{PREFIXO_ASSOCIADO}{name}"


def chave_do_responsavel(name: str) -> str:
	return f"{PREFIXO_RESPONSAVEL}{name}"


def separar(pessoa: str) -> tuple[str, str]:
	"""`"associado:abc"` -> `("Associado", "abc")`.

	Valor sem prefixo é lido como associado: é o que os endpoints recebiam antes de o
	responsável entrar, e o que os links já publicados continuam mandando.
	"""
	texto = (pessoa or "").strip()
	if not texto:
		frappe.throw(_("Pessoa não informada."), frappe.DoesNotExistError)

	if texto.startswith(PREFIXO_RESPONSAVEL):
		return DOCTYPE_RESPONSAVEL, texto[len(PREFIXO_RESPONSAVEL) :]
	if texto.startswith(PREFIXO_ASSOCIADO):
		return DOCTYPE_ASSOCIADO, texto[len(PREFIXO_ASSOCIADO) :]
	return DOCTYPE_ASSOCIADO, texto


def carregar(pessoa: str):
	"""Documento da pessoa, seja ela associado ou responsável.

	Sem `ignore_permissions`: a grade do `Associado` é permlevel 2 e quem pode escrever
	nela está declarado no DocType, não aqui.
	"""
	doctype, name = separar(pessoa)
	if not name or not frappe.db.exists(doctype, name):
		frappe.throw(_("Pessoa não encontrada no organograma."), frappe.DoesNotExistError)
	return frappe.get_doc(doctype, name)


def nome_de_exibicao(pessoa: str) -> str:
	doctype, name = separar(pessoa)
	return frappe.db.get_value(doctype, name, "nome_completo") or name
