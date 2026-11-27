# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Markdown restrito → requests da Google Docs API.

Entende o que os documentos das assembleias usam:

- `#` e `##`: títulos centralizados, em negrito;
- parágrafos justificados, com `**negrito**`, `_itálico_`, `[texto](url)` e `<br>`;
- listas `1.` e `-` (um nível);
- linha de assinatura: parágrafo que começa com `_____`, com espaço acima para assinar;
- tabelas `| a | b |`, com a primeira linha como cabeçalho.

Tudo aqui é puro: recebe texto e índices e devolve requests. Quem chama a API é
`api/google_workspace/assembleia_drive.py`. A Docs API conta posições em unidades
UTF-16, por isso o comprimento de cada trecho é medido assim, e não com `len()`.
"""

from __future__ import annotations

import re

FONTE = "Calibri"
TAMANHO_CORPO = 11
TAMANHO_TABELA = 10
TAMANHO_TITULO = {"titulo1": 14, "titulo2": 12}
COR_DO_LINK = {"red": 0.067, "green": 0.333, "blue": 0.8}
COR_DO_CABECALHO = {"red": 0.886, "green": 0.906, "blue": 0.925}
COR_DA_LINHA_PAR = {"red": 0.957, "green": 0.965, "blue": 0.973}
COR_DA_BORDA = {"red": 0.82, "green": 0.835, "blue": 0.859}
# Proporção das colunas da lista de presença: Nome | Representado por | Assinatura.
PROPORCAO_DAS_COLUNAS = {3: (0.42, 0.30, 0.28)}

_INLINE = re.compile(
	r"\*\*(?P<negrito>.+?)\*\*"
	r"|(?<![\w_])_(?P<italico>[^_\n]+?)_(?![\w_])"
	r"|\[(?P<texto>[^\]\n]+)\]\((?P<url>[^)\s]+)\)"
)
_ITEM_NUMERADO = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_ITEM_MARCADOR = re.compile(r"^\s*[-*]\s+(.*)$")
_LINHA_SEPARADORA_DE_TABELA = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
_ASSINATURA = re.compile(r"^_{5,}")


def unidades(texto: str) -> int:
	"""Comprimento em unidades UTF-16, a medida dos índices da Docs API."""
	return len(texto.encode("utf-16-le")) // 2


def _cor(rgb: dict) -> dict:
	return {"color": {"rgbColor": rgb}}


def inline(texto: str) -> tuple[str, list[tuple[int, int, dict]]]:
	"""Tira a marcação inline e devolve o texto limpo e os trechos com estilo.

	Os intervalos são em unidades UTF-16, relativos ao começo do texto. `<br>` vira
	quebra de linha suave (\\v), que não abre parágrafo novo.
	"""
	texto = texto.replace("<br>", "\v")
	partes = []
	estilos = []
	posicao = 0
	ultimo = 0
	for match in _INLINE.finditer(texto):
		antes = texto[ultimo : match.start()]
		partes.append(antes)
		posicao += unidades(antes)
		if match.group("negrito") is not None:
			dentro, estilo = match.group("negrito"), {"bold": True}
		elif match.group("italico") is not None:
			dentro, estilo = match.group("italico"), {"italic": True}
		else:
			dentro = match.group("texto")
			estilo = {
				"link": {"url": match.group("url")},
				"underline": True,
				"foregroundColor": _cor(COR_DO_LINK),
			}
		estilos.append((posicao, posicao + unidades(dentro), estilo))
		partes.append(dentro)
		posicao += unidades(dentro)
		ultimo = match.end()
	partes.append(texto[ultimo:])
	return "".join(partes), estilos


def _estilo_de_texto(inicio: int, fim: int, estilo: dict) -> dict:
	return {
		"updateTextStyle": {
			"range": {"startIndex": inicio, "endIndex": fim},
			"textStyle": estilo,
			"fields": ",".join(estilo),
		}
	}


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
	# Parágrafos são separados por linha em branco; dentro de um bloco, cada linha de
	# lista é um parágrafo próprio, e as demais linhas se juntam com quebra suave.
	acumulado: list[str] = []

	def fechar_paragrafo():
		if acumulado:
			texto = "\n".join(acumulado)
			estilo = "assinatura" if _ASSINATURA.match(texto) else "normal"
			paragrafos.append({"texto": texto, "estilo": estilo, "lista": None})
			acumulado.clear()

	def fechar_texto():
		fechar_paragrafo()
		if paragrafos:
			resultado.append({"tipo": "texto", "paragrafos": list(paragrafos)})
			paragrafos.clear()

	def fechar_tabela():
		if linhas_de_tabela:
			resultado.append({"tipo": "tabela", "linhas": list(linhas_de_tabela)})
			linhas_de_tabela.clear()

	for linha in (markdown or "").replace("\r\n", "\n").split("\n"):
		bruta = linha.rstrip()
		if bruta.strip().startswith("|"):
			fechar_texto()
			if not _LINHA_SEPARADORA_DE_TABELA.match(bruta.strip()):
				linhas_de_tabela.append(_celulas(bruta))
			continue
		fechar_tabela()
		if not bruta.strip():
			fechar_paragrafo()
			continue
		if bruta.startswith("## ") or bruta.startswith("# "):
			fechar_paragrafo()
			nivel = "titulo2" if bruta.startswith("## ") else "titulo1"
			paragrafos.append({"texto": bruta.lstrip("#").strip(), "estilo": nivel, "lista": None})
			continue
		numerado = _ITEM_NUMERADO.match(bruta)
		marcador = _ITEM_MARCADOR.match(bruta)
		if (numerado or marcador) and not _ASSINATURA.match(bruta.strip()):
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
	fechar_texto()
	fechar_tabela()
	return resultado


def _estilo_de_paragrafo(estilo: str, lista: str | None) -> dict:
	"""Sem recuo: o timbrado pode trazer recuo de primeira linha no estilo normal."""
	base = {
		"lineSpacing": 115,
		"spaceAbove": {"magnitude": 0, "unit": "PT"},
		"spaceBelow": {"magnitude": 6, "unit": "PT"},
		"indentFirstLine": {"magnitude": 0, "unit": "PT"},
		"indentStart": {"magnitude": 0, "unit": "PT"},
		"indentEnd": {"magnitude": 0, "unit": "PT"},
	}
	if estilo in TAMANHO_TITULO:
		base.update(alignment="CENTER", spaceAbove={"magnitude": 6, "unit": "PT"})
	elif estilo == "assinatura":
		# Espaço acima para assinar: a linha não pode ficar colada no texto.
		base.update(alignment="START", spaceAbove={"magnitude": 40, "unit": "PT"})
	else:
		base.update(alignment="JUSTIFIED")
	if lista:
		base["spaceBelow"] = {"magnitude": 2, "unit": "PT"}
	return base


def requests_de_texto(paragrafos: list[dict], inicio: int) -> tuple[list[dict], int]:
	"""Insere os parágrafos a partir de `inicio` e aplica os estilos.

	Devolve as requests e o comprimento inserido (em unidades UTF-16). Uma quebra de
	linha dentro do parágrafo vira quebra suave (\\v), para não abrir outro parágrafo.
	"""
	textos = []
	estilos = []
	listas: list[tuple[int, int, str]] = []
	posicao = inicio
	for paragrafo in paragrafos:
		texto, trechos = inline(paragrafo["texto"].replace("\n", "\v"))
		fim = posicao + unidades(texto) + 1  # + o \n que fecha o parágrafo
		textos.append(texto + "\n")
		campos = _estilo_de_paragrafo(paragrafo["estilo"], paragrafo["lista"])
		estilos.append(
			{
				"updateParagraphStyle": {
					"range": {"startIndex": posicao, "endIndex": fim},
					"paragraphStyle": campos,
					"fields": ",".join(campos),
				}
			}
		)
		if paragrafo["estilo"] in TAMANHO_TITULO and fim - 1 > posicao:
			estilos.append(
				_estilo_de_texto(
					posicao,
					fim - 1,
					{
						"bold": True,
						"fontSize": {"magnitude": TAMANHO_TITULO[paragrafo["estilo"]], "unit": "PT"},
					},
				)
			)
		for a, b, estilo in trechos:
			estilos.append(_estilo_de_texto(posicao + a, posicao + b, estilo))
		if paragrafo["lista"]:
			if listas and listas[-1][2] == paragrafo["lista"] and listas[-1][1] == posicao:
				listas[-1] = (listas[-1][0], fim, paragrafo["lista"])
			else:
				listas.append((posicao, fim, paragrafo["lista"]))
		posicao = fim

	requests = [{"insertText": {"location": {"index": inicio}, "text": "".join(textos)}}]
	# Fonte do corpo em todo o trecho, antes dos títulos e destaques que a sobrepõem.
	requests.append(
		_estilo_de_texto(
			inicio,
			posicao,
			{
				"weightedFontFamily": {"fontFamily": FONTE},
				"fontSize": {"magnitude": TAMANHO_CORPO, "unit": "PT"},
			},
		)
	)
	requests.extend(estilos)
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


# --------------------------------------------------------------------------------------
# Tabelas
# --------------------------------------------------------------------------------------


def requests_de_tabela(linhas: list[list[str]]) -> dict:
	"""Cria a tabela no fim do corpo; o resto vem depois, com os índices reais."""
	colunas = max((len(linha) for linha in linhas), default=1)
	return {
		"insertTable": {"rows": len(linhas), "columns": colunas, "endOfSegmentLocation": {"segmentId": ""}}
	}


def ultima_tabela(documento: dict) -> dict | None:
	"""O último elemento de tabela do corpo de um `documents().get` (com `startIndex`)."""
	for elemento in reversed((documento.get("body") or {}).get("content") or []):
		if "table" in elemento:
			return elemento
	return None


def largura_util(documento: dict) -> float:
	"""Largura entre as margens, em pontos."""
	estilo = documento.get("documentStyle") or {}
	pagina = ((estilo.get("pageSize") or {}).get("width") or {}).get("magnitude") or 595.28
	esquerda = (estilo.get("marginLeft") or {}).get("magnitude") or 72
	direita = (estilo.get("marginRight") or {}).get("magnitude") or 72
	return max(pagina - esquerda - direita, 200)


def _borda(largura: float) -> dict:
	return {"width": {"magnitude": largura, "unit": "PT"}, "dashStyle": "SOLID", "color": _cor(COR_DA_BORDA)}


def requests_de_estilo_da_tabela(elemento: dict, linhas: int, colunas: int, largura: float) -> list[dict]:
	"""Visual da tabela: largura útil inteira, só linhas horizontais, cabeçalho e linhas
	pares sombreados, cabeçalho repetido a cada página e nenhuma linha partida entre
	páginas (antes, nomes ficavam cortados na quebra)."""
	inicio = {"index": elemento["startIndex"]}
	requests = []
	proporcoes = PROPORCAO_DAS_COLUNAS.get(colunas) or tuple(1 / colunas for _ in range(colunas))
	for indice, proporcao in enumerate(proporcoes):
		requests.append(
			{
				"updateTableColumnProperties": {
					"tableStartLocation": inicio,
					"columnIndices": [indice],
					"tableColumnProperties": {
						"widthType": "FIXED_WIDTH",
						"width": {"magnitude": round(largura * proporcao, 1), "unit": "PT"},
					},
					"fields": "widthType,width",
				}
			}
		)
	padding = {"magnitude": 5, "unit": "PT"}
	requests.append(
		{
			"updateTableCellStyle": {
				"tableStartLocation": inicio,
				"tableCellStyle": {
					"borderLeft": _borda(0),
					"borderRight": _borda(0),
					"borderTop": _borda(0.5),
					"borderBottom": _borda(0.5),
					"paddingTop": padding,
					"paddingBottom": padding,
					"paddingLeft": padding,
					"paddingRight": padding,
					"contentAlignment": "MIDDLE",
				},
				"fields": "borderLeft,borderRight,borderTop,borderBottom,paddingTop,paddingBottom,paddingLeft,paddingRight,contentAlignment",
			}
		}
	)
	for linha in range(linhas):
		if linha == 0 or linha % 2 == 0:
			cor = COR_DO_CABECALHO if linha == 0 else COR_DA_LINHA_PAR
			requests.append(
				{
					"updateTableCellStyle": {
						"tableRange": {
							"tableCellLocation": {
								"tableStartLocation": inicio,
								"rowIndex": linha,
								"columnIndex": 0,
							},
							"rowSpan": 1,
							"columnSpan": colunas,
						},
						"tableCellStyle": {"backgroundColor": _cor(cor)},
						"fields": "backgroundColor",
					}
				}
			)
	requests.append(
		{
			"updateTableRowStyle": {
				"tableStartLocation": inicio,
				"rowIndices": list(range(linhas)),
				"tableRowStyle": {"minRowHeight": {"magnitude": 26, "unit": "PT"}, "preventOverflow": True},
				"fields": "minRowHeight,preventOverflow",
			}
		}
	)
	# Cabeçalho repetido no topo de cada página.
	requests.append({"pinTableHeaderRows": {"tableStartLocation": inicio, "pinnedHeaderRowsCount": 1}})
	return requests


def requests_de_preenchimento(tabela: dict, linhas: list[list[str]]) -> list[dict]:
	"""Texto de cada célula, do fim para o começo, para os índices não andarem.

	A primeira linha é o cabeçalho e sai em negrito. Aceita a marcação inline.
	"""
	alvos = []
	for r, linha in enumerate(tabela.get("tableRows") or []):
		for col, celula in enumerate(linha.get("tableCells") or []):
			if r >= len(linhas) or col >= len(linhas[r]) or not linhas[r][col]:
				continue
			conteudo = celula.get("content") or []
			if conteudo:
				alvos.append((conteudo[0]["startIndex"], linhas[r][col], r == 0))
	requests = []
	for inicio, texto, cabecalho in sorted(alvos, key=lambda alvo: alvo[0], reverse=True):
		limpo, trechos = inline(texto)
		fim = inicio + unidades(limpo)
		requests.append({"insertText": {"location": {"index": inicio}, "text": limpo}})
		base = {
			"weightedFontFamily": {"fontFamily": FONTE},
			"fontSize": {"magnitude": TAMANHO_TABELA, "unit": "PT"},
		}
		if cabecalho:
			base["bold"] = True
		requests.append(_estilo_de_texto(inicio, fim, base))
		for a, b, estilo in trechos:
			requests.append(_estilo_de_texto(inicio + a, inicio + b, estilo))
	return requests


def fim_do_corpo(documento: dict) -> int:
	"""Índice onde inserir no fim do corpo (antes do \\n final obrigatório)."""
	conteudo = (documento.get("body") or {}).get("content") or []
	return max((conteudo[-1].get("endIndex") or 2) - 1, 1) if conteudo else 1
