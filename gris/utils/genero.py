# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Concordância de gênero para os textos que o Gris envia a pessoas.

``Novo Associado``, ``Responsavel`` e ``Associado`` guardam ``sexo`` como Select
"Feminino"/"Masculino", e na base real o campo está preenchido em todos os registros.
Escrever "do(a) jovem" quando se sabe que é uma menina é uma escolha, não uma limitação —
estas funções existem para que a forma correta seja o caminho mais fácil.

Quando o sexo não está preenchido, cada função cai na forma dupla ("do(a)", "ele(a)"),
que é o comportamento antigo: nunca se arrisca um gênero errado.
"""

from __future__ import annotations

FEMININO = "Feminino"
MASCULINO = "Masculino"


def flexionar(sexo: str | None, feminino: str, masculino: str, indefinido: str | None = None) -> str:
	"""Escolhe a forma feminina ou masculina; sem sexo definido devolve ``indefinido``.

	``indefinido`` é opcional para os casos em que juntar as duas formas fica ilegível —
	quem chama passa uma redação melhor.
	"""
	valor = (sexo or "").strip()
	if valor == FEMININO:
		return feminino
	if valor == MASCULINO:
		return masculino
	return indefinido if indefinido is not None else f"{masculino}({feminino})"


def artigo(sexo: str | None) -> str:
	"""``a`` / ``o`` — "que **a** Joaninha fez a visita"."""
	return flexionar(sexo, "a", "o", "o(a)")


def de(sexo: str | None) -> str:
	"""``da`` / ``do`` — "o registro **da** Joaninha"."""
	return flexionar(sexo, "da", "do", "do(a)")


def por(sexo: str | None) -> str:
	"""``pela`` / ``pelo`` — "a jovem **pela** qual você é responsável"."""
	return flexionar(sexo, "pela", "pelo", "pelo(a)")


def para(sexo: str | None) -> str:
	"""``a`` / ``ao`` — "só avisar **a** Ana", "só avisar **ao** João"."""
	return flexionar(sexo, "a", "ao", "a(o)")


def dele(sexo: str | None) -> str:
	"""``dela`` / ``dele`` — "a ficha médica **dela**"."""
	return flexionar(sexo, "dela", "dele", "dele(a)")
