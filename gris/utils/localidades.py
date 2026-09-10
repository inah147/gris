# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Municípios do IBGE e consulta de CEP, para tirar o texto livre do cadastro.

Cidade e estado eram digitados à mão, e o resultado chegava à recepção com grafia livre —
o que obriga a reescrever o valor na hora de transcrever o registro para o Paxtu, onde os
dois campos são seleção. Aqui ficam as duas fontes que substituem a digitação: a lista de
municípios embarcada (ver ``gris/scripts/gerar_municipios.py``) e a consulta de CEP.

Ambas degradam sem quebrar o cadastro: sem a lista, a cidade volta a ser texto livre; sem
resposta do ViaCEP, o responsável preenche o endereço à mão. Travar o formulário do
responsável porque um serviço externo caiu seria pior do que aceitar um dado menos limpo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import frappe
import requests

VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
VIACEP_TIMEOUT = 5


def caminho_dos_municipios() -> Path:
	"""Onde mora o JSON gerado pelo ``gris/scripts/gerar_municipios.py``.

	Resolvido em chamada, e não na importação do módulo, para o import não depender de haver
	um site do Frappe inicializado.
	"""
	return Path(frappe.get_app_path("gris")) / "public" / "data" / "municipios.json"


def limpar_cep(cep: str | None) -> str:
	"""Só os dígitos do CEP."""
	return re.sub(r"\D", "", cep or "")


def formatar_cep(cep: str | None) -> str:
	"""CEP pontuado (``00000-000``); devolve o valor original quando não há 8 dígitos."""
	digitos = limpar_cep(cep)
	if len(digitos) != 8:
		return (cep or "").strip()

	return f"{digitos[:5]}-{digitos[5:]}"


def _carregar_municipios() -> dict[str, list[str]]:
	"""Lê o JSON gerado a partir do IBGE. Sem arquivo, devolve dicionário vazio.

	Não é cacheado em memória de propósito: o arquivo é lido raramente (só quando o
	formulário troca de UF) e o projeto não usa ``frappe.cache``.
	"""
	try:
		return json.loads(caminho_dos_municipios().read_text(encoding="utf-8"))
	except (OSError, ValueError):
		return {}


def municipios_por_uf(uf: str | None) -> list[str]:
	"""Municípios de uma UF, em ordem alfabética. Lista vazia quando a UF não existe."""
	return _carregar_municipios().get((uf or "").strip().upper(), [])


def municipio_valido(cidade: str | None, uf: str | None) -> bool:
	"""Se o par cidade/UF existe na lista do IBGE.

	Devolve ``True`` quando a lista não está embarcada: sem fonte para conferir, recusar o
	cadastro do responsável seria trocar um dado impreciso por nenhum dado.
	"""
	municipios = municipios_por_uf(uf)
	if not municipios:
		return True

	return (cidade or "").strip() in municipios


def consultar_cep(cep: str) -> dict[str, Any] | None:
	"""Endereço de um CEP pelo ViaCEP, ou ``None`` quando não há resposta utilizável.

	Chamado do servidor, não do navegador: evita CORS, mantém o limite de taxa sob controle
	do GRIS e não expõe o cadastro em andamento a um terceiro pelo cliente.
	"""
	digitos = limpar_cep(cep)
	if len(digitos) != 8:
		return None

	try:
		resposta = requests.get(VIACEP_URL.format(cep=digitos), timeout=VIACEP_TIMEOUT)
		resposta.raise_for_status()
		dados = resposta.json()
	except (requests.RequestException, ValueError):
		frappe.logger("gris").info(f"consulta de CEP indisponível para {digitos}")
		return None

	if not isinstance(dados, dict) or dados.get("erro"):
		return None

	return {
		"cep": formatar_cep(digitos),
		"endereco": (dados.get("logradouro") or "").strip(),
		"bairro": (dados.get("bairro") or "").strip(),
		"cidade": (dados.get("localidade") or "").strip(),
		"estado": (dados.get("uf") or "").strip().upper(),
	}
