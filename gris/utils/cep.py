# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Consulta de endereço pelo CEP na ViaCEP.

A ViaCEP foi escolhida entre as APIs gratuitas por ter a base mais completa e atualizada
(segue a base dos Correios) e responder "não encontrado" para CEP inexistente — a BrasilAPI,
testada junto, devolveu endereço inventado para um CEP que não existe. A consulta sai sempre
do servidor: a ViaCEP bloqueia por IP quem faz uso massivo, então quem chama isto precisa
limitar a frequência (ver ``buscar_endereco_por_cep`` no registro do responsável).
"""

from __future__ import annotations

import re

import requests

VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
TIMEOUT_SEGUNDOS = 5


def limpar_cep(cep: str | None) -> str:
	"""Só os dígitos do CEP, sem hífen ou ponto."""
	return re.sub(r"\D", "", cep or "")


def formatar_cep(cep: str | None) -> str:
	"""CEP com hífen (``00000-000``).

	Devolve o valor original quando não há 8 dígitos, pelo mesmo motivo de ``formatar_cpf``:
	mascarar um valor incompleto esconderia o problema.
	"""
	digitos = limpar_cep(cep)
	if len(digitos) != 8:
		return (cep or "").strip()

	return f"{digitos[:5]}-{digitos[5:]}"


def consultar_cep(cep: str | None) -> dict | None:
	"""Endereço do CEP, nos nomes de campo do formulário, ou ``None`` se o CEP não existe.

	Só volta o que o CEP determina: rua, bairro, cidade e UF. O ``complemento`` da ViaCEP
	("lado ímpar", "de 3253 ao fim") descreve a faixa de numeração do CEP, não a casa de
	quem preenche, e por isso fica de fora. CEP geral de cidade volta com rua e bairro vazios.

	Falha de rede, timeout ou resposta HTTP de erro sobem como ``requests.RequestException``,
	e resposta que não é JSON como ``ValueError``: cabe ao chamador decidir o que mostrar.
	"""
	digitos = limpar_cep(cep)
	if len(digitos) != 8:
		raise ValueError("CEP precisa ter 8 dígitos.")

	resposta = requests.get(VIACEP_URL.format(cep=digitos), timeout=TIMEOUT_SEGUNDOS)
	resposta.raise_for_status()
	dados = resposta.json()

	# Já veio como booleano e hoje vem como a string "true"; qualquer valor verdadeiro vale.
	if dados.get("erro"):
		return None

	return {
		"cep": formatar_cep(dados.get("cep") or digitos),
		"endereco": (dados.get("logradouro") or "").strip(),
		"bairro": (dados.get("bairro") or "").strip(),
		"cidade": (dados.get("localidade") or "").strip(),
		"estado": (dados.get("uf") or "").strip().upper(),
	}
