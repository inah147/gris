#!/usr/bin/env python3
"""Gera ``gris/public/data/municipios.json`` a partir da API de localidades do IBGE.

O cadastro pede cidade de nascimento e cidade de residência como seleção, não como texto
livre — é o pedido do documento de ajustes do registro ("não colocar texto aberto e sim as
opções pq tem pai que coloca coisa aleatória"). A lista é embarcada no app em vez de
consultada a cada abertura de formulário: são ~5.570 nomes que praticamente não mudam, e o
formulário não pode depender de uma API externa estar de pé para o responsável conseguir
preencher o cadastro do filho.

Rode uma vez num ambiente com saída para a internet e comite o JSON gerado::

    python gris/scripts/gerar_municipios.py

O arquivo fica no formato ``{"SP": ["Adamantina", ...], ...}``, com os nomes ordenados como o
IBGE os devolve (ordem alfabética por UF).
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

IBGE_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
DESTINO = Path(__file__).resolve().parents[1] / "public" / "data" / "municipios.json"

UF_SIGLAS = [
	"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
	"PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]  # fmt: skip


def baixar(uf: str) -> list[str]:
	url = IBGE_MUNICIPIOS.format(uf=uf)
	# URL fixa do IBGE, montada só com a sigla da UF.
	with urllib.request.urlopen(url, timeout=30) as resposta:
		dados = json.load(resposta)

	nomes = sorted({item["nome"] for item in dados})
	if not nomes:
		raise ValueError(f"IBGE devolveu lista vazia para {uf}")

	return nomes


def main() -> int:
	municipios: dict[str, list[str]] = {}

	for uf in UF_SIGLAS:
		try:
			municipios[uf] = baixar(uf)
		except (urllib.error.URLError, ValueError, KeyError) as erro:
			print(f"falha ao baixar {uf}: {erro}", file=sys.stderr)
			return 1

		print(f"{uf}: {len(municipios[uf])} municípios")

	DESTINO.parent.mkdir(parents=True, exist_ok=True)
	DESTINO.write_text(json.dumps(municipios, ensure_ascii=False, sort_keys=True), encoding="utf-8")
	print(f"gravado em {DESTINO} ({sum(len(v) for v in municipios.values())} municípios)")

	return 0


if __name__ == "__main__":
	raise SystemExit(main())
