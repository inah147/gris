# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Importa para o catálogo os preços dos distintivos da Loja Escoteira.

O catálogo de "Insignia ou Distintivo" nasceu com todos os itens valendo R$ 1,00,
o que deixa o valor estimado das solicitações sem significado. Esta rotina lê a
vitrine educativa da loja oficial, casa cada produto com o item já cadastrado e
grava o preço de lá.

Como a leitura é feita
----------------------

Nada de seletor de CSS chutado: a coleta usa os dados estruturados que as
plataformas de e-commerce publicam em toda página de produto, nesta ordem —

1. ``<script type="application/ld+json">`` com um objeto ``schema.org/Product``
   (nome, ``sku`` e ``offers.price``);
2. metatags de produto (``product:price:amount``, ``og:title``) e microdados
   (``itemprop="price"``, ``itemprop="sku"``).

Assim a rotina não depende do tema da loja: se a página descreve um produto de
forma legível por máquina, o preço é lido.

Casamento com o catálogo
------------------------

1. pelo ``codigo`` do item, quando ele já guarda o SKU da loja (é o que as
   execuções seguintes usam, porque a primeira grava esse código);
2. pelo nome normalizado (sem acentos, sem pontuação e sem as palavras de
   embalagem: "distintivo", "de", "especialidade", "insígnia"…), o que aproxima
   "Distintivo de Especialidade Acampamento" do nosso "Acampamento";
3. por semelhança de nome acima de :data:`LIMIAR_DE_SEMELHANCA`.

Sem correspondência, o produto vira um item novo. Empate técnico entre dois
itens do catálogo não escolhe nenhum: fica registrado como aviso, para não
gravar preço no item errado.

Como rodar
----------

Sempre com ``simular=True`` primeiro, para conferir o relatório antes de gravar::

    bench --site <site> execute gris.api.insignias.precos_loja.importar_precos_loja \\
        --kwargs "{'simular': True}"

    bench --site <site> execute gris.api.insignias.precos_loja.importar_precos_loja

Cada execução abre um "Log de Execucao de Job", visível em ``/app/monitor-de-jobs``.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from collections.abc import Callable, Iterator
from difflib import SequenceMatcher
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

import frappe
import requests
from frappe.utils import flt

from gris.utils.job_logger import definir_resumo, metrica, obter_logger, registrar_execucao

DOCTYPE = "Insignia ou Distintivo"

URL_CATEGORIA = "https://loja.escoteiros.org.br/educativo"

# Identifica o GRIS para a loja, em vez de fingir ser um navegador.
USER_AGENT = "GRIS/1.0 (+https://gris.gepim.com.br; integracao do catalogo de distintivos)"

TEMPO_LIMITE = 30
TEMPO_ENTRE_REQUISICOES = 1.0
LIMITE_DE_PAGINAS = 1500
LIMITE_DE_LISTAGENS = 60

LIMIAR_DE_SEMELHANCA = 0.85
# Dois candidatos com pontuação quase igual são um empate: melhor não escolher.
MARGEM_DE_EMPATE = 0.02

# Palavras que a loja usa para embalar o nome e que o catálogo do GRIS não usa.
PALAVRAS_IGNORADAS = frozenset(
	{
		"a",
		"as",
		"bordado",
		"bordada",
		"da",
		"das",
		"de",
		"do",
		"dos",
		"e",
		"emblema",
		"especialidade",
		"especialidades",
		"insignia",
		"insignias",
		"distintivo",
		"distintivos",
		"o",
		"os",
		"para",
		"un",
		"unidade",
	}
)

TIPO_PADRAO = "Outro"
RAMO_PADRAO = "Todos"

# Ordem importa: o primeiro padrão que casar decide o tipo.
TIPOS_POR_PADRAO: tuple[tuple[str, str], ...] = (
	(r"progressao", "Distintivo de Progressão"),
	(r"especialidade", "Especialidade"),
	(r"interesse especial", "Insígnia de Interesse Especial"),
	(r"insignia", "Insígnia de Interesse Especial"),
	(r"funcao|chefia|diretoria|conselho", "Distintivo de Função"),
	(r"identificacao|numeral|nome do grupo|distintivo de uf|regiao", "Distintivo de Identificação"),
)

RAMOS_POR_PADRAO: tuple[tuple[str, str], ...] = (
	(r"filhote", "Filhotes"),
	(r"lobinho|alcateia", "Lobinho"),
	(r"senior|sênior|tropa senior", "Sênior"),
	(r"pioneiro|cla ", "Pioneiro"),
	(r"escotista|dirigente|adulto|chefe", "Escotistas e Dirigentes"),
	(r"ramo escoteiro|tropa escoteira", "Escoteiro"),
)


# --------------------------------------------------------------------- leitura


class _LeitorDeHtml(HTMLParser):
	"""Recolhe de uma página só o que interessa: JSON-LD, metatags e links."""

	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.blocos_json_ld: list[str] = []
		self.metas: list[dict[str, str]] = []
		self.links: list[str] = []
		self.titulo = ""
		self._dentro_do_json = False
		self._dentro_do_titulo = False
		self._buffer: list[str] = []

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		atributos = {chave.lower(): (valor or "") for chave, valor in attrs}

		if tag == "script" and atributos.get("type", "").strip().lower() == "application/ld+json":
			self._dentro_do_json = True
			self._buffer = []
		elif tag == "meta":
			self.metas.append(atributos)
		elif tag == "a" and atributos.get("href"):
			self.links.append(atributos["href"])
		elif tag == "title":
			self._dentro_do_titulo = True
			self._buffer = []

	def handle_endtag(self, tag: str) -> None:
		if tag == "script" and self._dentro_do_json:
			self.blocos_json_ld.append("".join(self._buffer))
			self._dentro_do_json = False
			self._buffer = []
		elif tag == "title" and self._dentro_do_titulo:
			self.titulo = "".join(self._buffer).strip()
			self._dentro_do_titulo = False
			self._buffer = []

	def handle_data(self, data: str) -> None:
		if self._dentro_do_json or self._dentro_do_titulo:
			self._buffer.append(data)


def _ler_pagina(html: str) -> _LeitorDeHtml:
	leitor = _LeitorDeHtml()
	try:
		leitor.feed(html or "")
	except Exception:
		# HTML quebrado não pode derrubar a coleta inteira: fica o que deu para ler.
		pass
	return leitor


def _achatar(dados: Any) -> Iterator[dict]:
	"""Percorre o JSON-LD, que vem ora como lista, ora aninhado em ``@graph``."""
	if isinstance(dados, list):
		for item in dados:
			yield from _achatar(item)
		return

	if not isinstance(dados, dict):
		return

	yield dados

	for chave in ("@graph", "itemListElement", "item", "mainEntity", "hasVariant"):
		if chave in dados:
			yield from _achatar(dados[chave])


def _e_produto(objeto: dict) -> bool:
	tipo = objeto.get("@type") or objeto.get("type")
	if isinstance(tipo, str):
		return tipo.strip().lower() == "product"
	if isinstance(tipo, list):
		return any(str(item).strip().lower() == "product" for item in tipo)
	return False


def _para_valor(bruto: Any) -> float | None:
	"""Converte "R$ 1.234,56", "1234.56" ou 1234.56 num número."""
	if bruto is None or isinstance(bruto, bool):
		return None

	if isinstance(bruto, int | float):
		valor = float(bruto)
		return valor if valor > 0 else None

	texto = re.sub(r"[^\d,.\-]", "", str(bruto)).strip()
	if not texto:
		return None

	if "," in texto and "." in texto:
		# "1.234,56" (pt-BR) x "1,234.56" (en): manda o separador mais à direita.
		if texto.rfind(",") > texto.rfind("."):
			texto = texto.replace(".", "").replace(",", ".")
		else:
			texto = texto.replace(",", "")
	elif "," in texto:
		texto = texto.replace(",", ".")

	try:
		valor = float(texto)
	except ValueError:
		return None

	return valor if valor > 0 else None


def _preco_da_oferta(oferta: Any) -> float | None:
	if isinstance(oferta, list):
		for item in oferta:
			preco = _preco_da_oferta(item)
			if preco is not None:
				return preco
		return None

	if not isinstance(oferta, dict):
		return None

	for chave in ("price", "lowPrice", "highPrice"):
		preco = _para_valor(oferta.get(chave))
		if preco is not None:
			return preco

	return _preco_da_oferta(oferta.get("priceSpecification"))


def _codigo_do_produto(objeto: dict) -> str | None:
	for chave in ("sku", "mpn", "productID", "gtin13", "gtin", "identifier"):
		valor = objeto.get(chave)
		if isinstance(valor, str | int) and str(valor).strip():
			return str(valor).strip()
	return None


def _produto_do_json_ld(leitor: _LeitorDeHtml) -> dict | None:
	for bloco in leitor.blocos_json_ld:
		try:
			dados = json.loads(bloco)
		except ValueError:
			continue

		for objeto in _achatar(dados):
			if not _e_produto(objeto):
				continue

			nome = str(objeto.get("name") or "").strip()
			preco = _preco_da_oferta(objeto.get("offers"))
			if nome and preco is not None:
				return {"nome": nome, "preco": preco, "codigo": _codigo_do_produto(objeto)}

	return None


def _valor_da_meta(metas: list[dict[str, str]], nomes: tuple[str, ...]) -> str | None:
	procurados = {nome.lower() for nome in nomes}
	for meta in metas:
		chave = (meta.get("property") or meta.get("name") or meta.get("itemprop") or "").strip().lower()
		if chave in procurados and (meta.get("content") or "").strip():
			return meta["content"].strip()
	return None


def _produto_das_metatags(leitor: _LeitorDeHtml) -> dict | None:
	preco = _para_valor(_valor_da_meta(leitor.metas, ("product:price:amount", "og:price:amount", "price")))
	if preco is None:
		return None

	nome = _valor_da_meta(leitor.metas, ("og:title", "twitter:title", "name")) or leitor.titulo
	nome = (nome or "").strip()
	if not nome:
		return None

	return {
		"nome": nome,
		"preco": preco,
		"codigo": _valor_da_meta(leitor.metas, ("sku", "product:retailer_item_id")),
	}


def extrair_produto(html: str, url: str) -> dict | None:
	"""Devolve ``{"nome", "preco", "codigo", "url"}`` se a página descrever um produto."""
	leitor = _ler_pagina(html)
	produto = _produto_do_json_ld(leitor) or _produto_das_metatags(leitor)
	if not produto:
		return None

	return {**produto, "url": url}


def extrair_links(html: str, url: str) -> list[str]:
	"""Links absolutos, do mesmo host, sem âncora e sem repetição."""
	host = urlparse(url).netloc
	vistos: dict[str, None] = {}

	for href in _ler_pagina(html).links:
		href = href.strip()
		if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
			continue

		absoluto, _ = urldefrag(urljoin(url, href))
		partes = urlparse(absoluto)
		if partes.scheme in ("http", "https") and partes.netloc == host:
			vistos.setdefault(absoluto, None)

	return list(vistos)


# --------------------------------------------------------------------- coleta


def _baixar(url: str) -> str | None:
	"""Busca uma página; devolve ``None`` para o que não for HTML."""
	resposta = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TEMPO_LIMITE)
	resposta.raise_for_status()

	if "html" not in (resposta.headers.get("Content-Type") or "").lower():
		return None

	return resposta.text


def _e_listagem(url: str, url_inicial: str) -> bool:
	"""Paginação da vitrine: mesmo caminho da categoria, outra query."""
	atual, inicial = urlparse(url), urlparse(url_inicial)
	return atual.path.rstrip("/") == inicial.path.rstrip("/")


def coletar_produtos(
	url_inicial: str = URL_CATEGORIA,
	baixar: Callable[[str], str | None] | None = None,
	limite_paginas: int = LIMITE_DE_PAGINAS,
	pausa: float = TEMPO_ENTRE_REQUISICOES,
	logger: Any = None,
) -> list[dict]:
	"""Varre a vitrine e devolve os produtos com preço que ela expõe.

	A varredura é rasa de propósito: a página da categoria e sua paginação são
	expandidas; as páginas que elas linkam são lidas, mas não expandidas. Isso
	cobre "categoria -> produto" sem sair andando pela loja inteira.
	"""
	baixar = baixar or _baixar
	fila: list[tuple[str, bool]] = [(url_inicial, True)]
	visitadas: set[str] = set()
	listagens = 0
	produtos: dict[str, dict] = {}

	while fila and len(visitadas) < limite_paginas:
		url, expandir = fila.pop(0)
		if url in visitadas:
			continue
		visitadas.add(url)

		try:
			html = baixar(url)
		except Exception as erro:
			if logger:
				logger.warning(f"Não consegui ler {url}: {erro}")
			continue

		if pausa and len(visitadas) > 1:
			time.sleep(pausa)

		if not html:
			continue

		produto = extrair_produto(html, url)
		if produto:
			produtos.setdefault(url, produto)

		if not expandir:
			continue

		for link in extrair_links(html, url):
			if link in visitadas:
				continue
			if _e_listagem(link, url_inicial):
				if listagens < LIMITE_DE_LISTAGENS:
					listagens += 1
					fila.append((link, True))
			else:
				fila.append((link, False))

	if logger:
		logger.info(f"{len(visitadas)} página(s) lida(s), {len(produtos)} produto(s) com preço.")

	return list(produtos.values())


# ------------------------------------------------------------------ casamento


def normalizar(nome: str) -> str:
	"""Reduz o nome ao essencial, para comparar loja e catálogo em pé de igualdade."""
	texto = unicodedata.normalize("NFKD", (nome or "").lower())
	texto = "".join(letra for letra in texto if not unicodedata.combining(letra))
	texto = re.sub(r"[^a-z0-9]+", " ", texto)

	palavras = [palavra for palavra in texto.split() if palavra not in PALAVRAS_IGNORADAS]
	return " ".join(palavras).strip()


def _semelhanca(esquerda: str, direita: str) -> float:
	return SequenceMatcher(None, esquerda, direita).ratio()


def encontrar_correspondencia(
	produto: dict, itens: list[dict], limiar: float = LIMIAR_DE_SEMELHANCA
) -> tuple[dict | None, float, bool]:
	"""Casa o produto da loja com um item do catálogo.

	Devolve ``(item, pontuacao, empate)``. ``empate=True`` quer dizer que dois
	itens ficaram tecnicamente iguais — nesse caso nada deve ser gravado.
	"""
	codigo = (produto.get("codigo") or "").strip()
	if codigo:
		for item in itens:
			if (item.get("codigo") or "").strip() == codigo:
				return item, 1.0, False

	alvo = normalizar(produto.get("nome", ""))
	if not alvo:
		return None, 0.0, False

	pontuados = sorted(
		((item, _semelhanca(alvo, normalizar(item.get("nome", "")))) for item in itens),
		key=lambda par: par[1],
		reverse=True,
	)
	if not pontuados:
		return None, 0.0, False

	melhor, pontuacao = pontuados[0]
	if pontuacao < limiar:
		return None, pontuacao, False

	if len(pontuados) > 1 and pontuados[1][1] >= limiar and pontuacao - pontuados[1][1] < MARGEM_DE_EMPATE:
		return None, pontuacao, True

	return melhor, pontuacao, False


def inferir_tipo(nome: str) -> str:
	texto = normalizar(nome)
	# `normalizar` derruba as palavras de embalagem; aqui elas voltam a importar.
	bruto = unicodedata.normalize("NFKD", (nome or "").lower())
	bruto = "".join(letra for letra in bruto if not unicodedata.combining(letra))

	for padrao, tipo in TIPOS_POR_PADRAO:
		if re.search(padrao, bruto) or re.search(padrao, texto):
			return tipo

	return TIPO_PADRAO


def inferir_ramo(nome: str) -> str:
	bruto = unicodedata.normalize("NFKD", (nome or "").lower())
	bruto = "".join(letra for letra in bruto if not unicodedata.combining(letra))

	for padrao, ramo in RAMOS_POR_PADRAO:
		if re.search(padrao, bruto):
			return ramo

	return RAMO_PADRAO


# ------------------------------------------------------------------ importação


def _catalogo_atual() -> list[dict]:
	return frappe.get_all(
		DOCTYPE,
		fields=["name", "nome", "codigo", "valor_unitario", "tipo", "ramo", "ativo"],
		limit_page_length=0,
	)


def _mudancas(item: dict, produto: dict) -> dict:
	mudancas: dict[str, Any] = {}

	if flt(item.get("valor_unitario")) != flt(produto["preco"]):
		mudancas["valor_unitario"] = flt(produto["preco"])

	codigo = (produto.get("codigo") or "").strip()
	if codigo and (item.get("codigo") or "").strip() != codigo:
		mudancas["codigo"] = codigo

	return mudancas


def importar_precos_loja(
	url: str = URL_CATEGORIA,
	simular: bool = False,
	limiar: float = LIMIAR_DE_SEMELHANCA,
	criar_ausentes: bool = True,
	apenas_distintivos: bool = True,
	limite_paginas: int = LIMITE_DE_PAGINAS,
	pausa: float = TEMPO_ENTRE_REQUISICOES,
	baixar: Callable[[str], str | None] | None = None,
) -> dict:
	"""Lê os preços da loja e atualiza o catálogo de insígnias e distintivos.

	:param simular: só relata o que mudaria, sem gravar nada.
	:param criar_ausentes: cria no catálogo o produto que não casou com nada.
	:param apenas_distintivos: só cria item novo quando o nome identifica um
	        distintivo ou insígnia — evita encher o catálogo de livro e uniforme,
	        que dividem a vitrine com os distintivos.
	"""
	logger = obter_logger("importar_precos_loja")

	with registrar_execucao(
		"gris.api.insignias.precos_loja.importar_precos_loja",
		rotulo="Importação de preços da Loja Escoteira",
		parametros={"url": url, "simular": simular, "limiar": limiar},
	):
		logger.info(f"Coletando os produtos de {url}.")
		produtos = coletar_produtos(
			url, baixar=baixar, limite_paginas=limite_paginas, pausa=pausa, logger=logger
		)

		itens = _catalogo_atual()
		relatorio: dict[str, Any] = {
			"simulacao": simular,
			"url": url,
			"produtos_encontrados": len(produtos),
			"atualizados": 0,
			"criados": 0,
			"sem_alteracao": 0,
			"ignorados": 0,
			"ambiguos": 0,
			"detalhes": [],
		}

		for produto in produtos:
			item, pontuacao, empate = encontrar_correspondencia(produto, itens, limiar=limiar)

			if empate:
				relatorio["ambiguos"] += 1
				relatorio["detalhes"].append({"acao": "ambiguo", "produto": produto["nome"]})
				logger.warning(
					f"'{produto['nome']}' ficou empatado entre dois itens do catálogo; "
					"nada foi gravado para ele."
				)
				continue

			if item:
				_aplicar_atualizacao(item, produto, pontuacao, simular, relatorio, logger)
			elif criar_ausentes:
				_aplicar_criacao(produto, itens, simular, apenas_distintivos, relatorio, logger)
			else:
				relatorio["ignorados"] += 1

		for chave in (
			"produtos_encontrados",
			"atualizados",
			"criados",
			"sem_alteracao",
			"ignorados",
			"ambiguos",
		):
			metrica(chave, relatorio[chave], incrementar=False)

		prefixo = "Simulação: " if simular else ""
		definir_resumo(
			f"{prefixo}{relatorio['produtos_encontrados']} produto(s) lido(s) da loja — "
			f"{relatorio['atualizados']} item(ns) atualizado(s), {relatorio['criados']} criado(s), "
			f"{relatorio['sem_alteracao']} sem alteração e {relatorio['ignorados']} ignorado(s)."
		)

		# Sem commit manual: a gravação acompanha a transação de quem chamou — o
		# `bench execute` documentado acima fecha a transação ao terminar.
		return relatorio


def _aplicar_atualizacao(
	item: dict, produto: dict, pontuacao: float, simular: bool, relatorio: dict, logger: Any
) -> None:
	mudancas = _mudancas(item, produto)
	if not mudancas:
		relatorio["sem_alteracao"] += 1
		return

	relatorio["atualizados"] += 1
	relatorio["detalhes"].append(
		{
			"acao": "atualizar",
			"item": item["name"],
			"produto": produto["nome"],
			"semelhanca": round(pontuacao, 3),
			"mudancas": mudancas,
		}
	)

	if simular:
		return

	doc = frappe.get_doc(DOCTYPE, item["name"])
	for campo, valor in mudancas.items():
		setattr(doc, campo, valor)
	doc.save()

	item.update(mudancas)
	logger.info(f"'{item['name']}' atualizado a partir de '{produto['nome']}': {mudancas}.")


def _aplicar_criacao(
	produto: dict, itens: list[dict], simular: bool, apenas_distintivos: bool, relatorio: dict, logger: Any
) -> None:
	tipo = inferir_tipo(produto["nome"])

	if apenas_distintivos and tipo == TIPO_PADRAO:
		relatorio["ignorados"] += 1
		relatorio["detalhes"].append({"acao": "ignorar", "produto": produto["nome"]})
		return

	novo = {
		"doctype": DOCTYPE,
		"nome": produto["nome"].strip(),
		"tipo": tipo,
		"ramo": inferir_ramo(produto["nome"]),
		"codigo": (produto.get("codigo") or "").strip() or None,
		"valor_unitario": flt(produto["preco"]),
		"ativo": 1,
		"descricao": f"Importado da Loja Escoteira em {frappe.utils.today()} — {produto['url']}",
	}

	relatorio["criados"] += 1
	relatorio["detalhes"].append({"acao": "criar", "produto": produto["nome"], "dados": novo})

	if simular:
		return

	doc = frappe.get_doc(novo)
	doc.insert()

	itens.append(
		{
			"name": doc.name,
			"nome": doc.nome,
			"codigo": doc.codigo,
			"valor_unitario": doc.valor_unitario,
			"tipo": doc.tipo,
			"ramo": doc.ramo,
			"ativo": doc.ativo,
		}
	)
	logger.info(f"'{doc.name}' criado a partir de '{produto['nome']}' por R$ {produto['preco']}.")
