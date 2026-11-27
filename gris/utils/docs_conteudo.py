# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Markdown restrito → requests da Google Docs API.

Entende o que os documentos das assembleias usam: `#` e `##` (títulos centralizados),
parágrafos, `**negrito**`, listas `1.` e `-` (um nível) e tabelas `| a | b |`.

Tudo aqui é puro: recebe texto e índices e devolve requests. Quem chama a API é
`api/google_workspace/assembleia_drive.py`. A Docs API conta posições em unidades
UTF-16, por isso o comprimento de cada trecho é medido assim, e não com `len()`.
"""

from __future__ import annotations

import re

_NEGRITO = re.compile(r"\*\*(.+?)\*\*")
_ITEM_NUMERADO = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_ITEM_MARCADOR = re.compile(r"^\s*[-*]\s+(.*)$")
_LINHA_SEPARADORA_DE_TABELA = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")


def unidades(texto: str) -> int:
	"""Comprimento em unidades UTF-16, a medida dos índices da Docs API."""
	return len(texto.encode("utf-16-le")) // 2


def _sem_negrito(texto: str) -> tuple[str, list[tuple[int, int]]]:
	"""Tira os `**` e devolve os intervalos (em unidades UTF-16) que ficam em negrito."""
	partes = []
	negritos = []
	posicao = 0
	ultimo = 0
	for match in _NEGRITO.finditer(texto):
		antes = texto[ultimo : match.start()]
		partes.append(antes)
		posicao += unidades(antes)
		dentro = match.group(1)
		negritos.append((posicao, posicao + unidades(dentro)))
		partes.append(dentro)
		posicao += unidades(dentro)
		ultimo = match.end()
	partes.append(texto[ultimo:])
	return "".join(partes), negritos


def _celulas(linha: str) -> list[str]:
	conteudo = linha.strip()
	if conteudo.startswith("|"):
		conteudo = conteudo[1:]
	if conteudo.endswith("|"):
		conteudo = conteudo[:-1]
	return [celula.strip() for celula in conteudo.split("|")]


def blocos(markdown: str) -> list[dict]:
	"""Quebra o markdown em blocos de texto (parágrafos) e de tabela, na ordem."""
	resultado: list[dict] = []
	paragrafos: list[dict] = []
	linhas_de_tabela: list[list[str]] = []

	def fechar_texto():
		if paragrafos:
			resultado.append({"tipo": "texto", "paragrafos": list(paragrafos)})
			paragrafos.clear()

	def fechar_tabela():
		if linhas_de_tabela:
			resultado.append({"tipo": "tabela", "linhas": list(linhas_de_tabela)})
			linhas_de_tabela.clear()

	# Parágrafos são separados por linha em branco; dentro de um bloco, cada linha de
	# lista é um parágrafo próprio, e as demais linhas se juntam com quebra de linha.
	acumulado: list[str] = []

	def fechar_paragrafo():
		if acumulado:
			paragrafos.append({"texto": "\n".join(acumulado), "estilo": "normal", "lista": None})
			acumulado.clear()

	for linha in (markdown or "").replace("\r\n", "\n").split("\n"):
		bruta = linha.rstrip()
		if bruta.strip().startswith("|"):
			fechar_paragrafo()
			fechar_texto()
			if not _LINHA_SEPARADORA_DE_TABELA.match(bruta.strip()):
				linhas_de_tabela.append(_celulas(bruta))
			continue
		fechar_tabela()
		if not bruta.strip():
			fechar_paragrafo()
			continue
		if bruta.startswith("## "):
			fechar_paragrafo()
			paragrafos.append({"texto": bruta[3:].strip(), "estilo": "titulo2", "lista": None})
			continue
		if bruta.startswith("# "):
			fechar_paragrafo()
			paragrafos.append({"texto": bruta[2:].strip(), "estilo": "titulo1", "lista": None})
			continue
		numerado = _ITEM_NUMERADO.match(bruta)
		marcador = _ITEM_MARCADOR.match(bruta)
		if numerado or marcador:
			fechar_paragrafo()
			paragrafos.append(
				{
					"texto": (numerado or marcador).group(1).strip(),
					"estilo": "normal",
					"lista": "numerada" if numerado else "marcador",
				}
			)
			continue
		acumulado.append(bruta.strip())
	fechar_paragrafo()
	fechar_texto()
	fechar_tabela()
	return resultado


def requests_de_texto(paragrafos: list[dict], inicio: int) -> tuple[list[dict], int]:
	"""Insere os parágrafos a partir de `inicio` e aplica os estilos.

	Devolve as requests e o comprimento inserido (em unidades UTF-16). Uma quebra de
	linha dentro do parágrafo vira quebra de linha suave (\\v), para não virar outro
	parágrafo da lista.
	"""
	textos = []
	estilos = []
	listas: list[tuple[int, int, str]] = []
	posicao = inicio
	for paragrafo in paragrafos:
		texto, negritos = _sem_negrito(paragrafo["texto"].replace("\n", "\v"))
		comprimento = unidades(texto) + 1  # + o \n que fecha o parágrafo
		fim = posicao + comprimento
		textos.append(texto + "\n")

		if paragrafo["estilo"] in ("titulo1", "titulo2"):
			estilos.append(
				{
					"updateParagraphStyle": {
						"range": {"startIndex": posicao, "endIndex": fim},
						"paragraphStyle": {
							"alignment": "CENTER",
							"spaceAbove": {"magnitude": 6, "unit": "PT"},
							"spaceBelow": {"magnitude": 6, "unit": "PT"},
						},
						"fields": "alignment,spaceAbove,spaceBelow",
					}
				}
			)
			estilos.append(
				{
					"updateTextStyle": {
						"range": {"startIndex": posicao, "endIndex": fim - 1},
						"textStyle": {
							"bold": True,
							"fontSize": {
								"magnitude": 14 if paragrafo["estilo"] == "titulo1" else 12,
								"unit": "PT",
							},
						},
						"fields": "bold,fontSize",
					}
				}
			)
		else:
			estilos.append(
				{
					"updateParagraphStyle": {
						"range": {"startIndex": posicao, "endIndex": fim},
						"paragraphStyle": {
							"alignment": "JUSTIFIED",
							"spaceBelow": {"magnitude": 6, "unit": "PT"},
						},
						"fields": "alignment,spaceBelow",
					}
				}
			)
		for a, b in negritos:
			estilos.append(
				{
					"updateTextStyle": {
						"range": {"startIndex": posicao + a, "endIndex": posicao + b},
						"textStyle": {"bold": True},
						"fields": "bold",
					}
				}
			)
		if paragrafo["lista"]:
			if listas and listas[-1][2] == paragrafo["lista"] and listas[-1][1] == posicao:
				listas[-1] = (listas[-1][0], fim, paragrafo["lista"])
			else:
				listas.append((posicao, fim, paragrafo["lista"]))
		posicao = fim

	requests = [{"insertText": {"location": {"index": inicio}, "text": "".join(textos)}}]
	requests.extend(estilos)
	# Marcadores por último: não mudam índices sem tabulação, mas assim nada depende deles.
	for a, b, tipo in listas:
		requests.append(
			{
				"createParagraphBullets": {
					"range": {"startIndex": a, "endIndex": b},
					"bulletPreset": "NUMBERED_DECIMAL_ALPHA_ROMAN"
					if tipo == "numerada"
					else "BULLET_DISC_CIRCLE_SQUARE",
				}
			}
		)
	return requests, posicao - inicio


def requests_de_tabela(linhas: list[list[str]]) -> dict:
	"""Cria a tabela no fim do corpo; o preenchimento vem depois, com os índices reais."""
	colunas = max((len(linha) for linha in linhas), default=1)
	return {
		"insertTable": {"rows": len(linhas), "columns": colunas, "endOfSegmentLocation": {"segmentId": ""}}
	}


def ultima_tabela(documento: dict) -> dict | None:
	"""A última tabela do corpo de um `documents().get`."""
	for elemento in reversed((documento.get("body") or {}).get("content") or []):
		if "table" in elemento:
			return elemento["table"]
	return None


def requests_de_preenchimento(tabela: dict, linhas: list[list[str]]) -> list[dict]:
	"""Texto de cada célula, do fim para o começo, para os índices não andarem.

	A primeira linha é o cabeçalho e sai em negrito.
	"""
	requests = []
	alvos = []
	for r, linha in enumerate(tabela.get("tableRows") or []):
		for col, celula in enumerate(linha.get("tableCells") or []):
			if r >= len(linhas) or col >= len(linhas[r]):
				continue
			texto = linhas[r][col]
			if not texto:
				continue
			conteudo = celula.get("content") or []
			if not conteudo:
				continue
			inicio = conteudo[0]["startIndex"]
			alvos.append((inicio, texto, r == 0))
	for inicio, texto, cabecalho in sorted(alvos, key=lambda alvo: alvo[0], reverse=True):
		limpo, negritos = _sem_negrito(texto)
		requests.append({"insertText": {"location": {"index": inicio}, "text": limpo}})
		intervalos = [(0, unidades(limpo))] if cabecalho else negritos
		for a, b in intervalos:
			requests.append(
				{
					"updateTextStyle": {
						"range": {"startIndex": inicio + a, "endIndex": inicio + b},
						"textStyle": {"bold": True},
						"fields": "bold",
					}
				}
			)
	return requests


def fim_do_corpo(documento: dict) -> int:
	"""Índice onde inserir no fim do corpo (antes do \\n final obrigatório)."""
	conteudo = (documento.get("body") or {}).get("content") or []
	return max((conteudo[-1].get("endIndex") or 2) - 1, 1) if conteudo else 1
