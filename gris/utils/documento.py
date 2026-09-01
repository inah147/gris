# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Normalização e validação de documentos (CPF).

O CPF é a chave de identidade das pessoas no Gris: ``Responsavel``, ``Novo Associado``
e ``Associado`` são nomeados pelo md5 dos dígitos do CPF (ver ``autoname`` de cada
DocType). Concentrar a limpeza, a validação e o cálculo desse identificador aqui evita
que cada tela reimplemente a regra — e é justamente a divergência entre implementações
que gera registro duplicado ou busca que não encontra o que existe.
"""

from __future__ import annotations

import hashlib
import re


def limpar_cpf(cpf: str | None) -> str:
	"""Só os dígitos do CPF, sem pontuação."""
	return re.sub(r"\D", "", cpf or "")


def formatar_cpf(cpf: str | None) -> str:
	"""CPF pontuado (``000.000.000-00``), para exibição em tela e em documento gerado.

	Devolve o valor original quando não há 11 dígitos: cadastros antigos guardam o CPF
	nos dois formatos, e mascarar um valor incompleto esconderia o problema.
	"""
	digitos = limpar_cpf(cpf)
	if len(digitos) != 11:
		return (cpf or "").strip()

	return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def cpf_valido(cpf: str | None) -> bool:
	"""Valida os dígitos verificadores do CPF (espelho de ``validateCPF`` no registro.js)."""
	digitos = limpar_cpf(cpf)
	if len(digitos) != 11 or digitos == digitos[0] * 11:
		return False

	for posicao in (9, 10):
		soma = sum(int(digitos[i]) * (posicao + 1 - i) for i in range(posicao))
		resto = 11 - (soma % 11)
		esperado = 0 if resto >= 10 else resto
		if esperado != int(digitos[posicao]):
			return False

	return True


def id_por_cpf(cpf: str | None) -> str:
	"""Identificador (``name``) que os DocTypes de pessoa derivam do CPF.

	Retorna string vazia quando não há CPF, para o chamador decidir o que fazer.
	"""
	digitos = limpar_cpf(cpf)
	if not digitos:
		return ""

	return hashlib.md5(digitos.encode("utf-8")).hexdigest()  # nosec B324 - identificador, não segredo
