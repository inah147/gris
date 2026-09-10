# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Cobertura da importação de preços da Loja Escoteira para o catálogo."""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.insignias import precos_loja

URL_CATEGORIA = "https://loja.exemplo.test/educativo"


def _pagina_json_ld(nome: str, preco: str, sku: str = "") -> str:
	sku_json = f'"sku": "{sku}",' if sku else ""
	return f"""
	<html><head><title>{nome}</title>
	<script type="application/ld+json">
	{{
		"@context": "https://schema.org",
		"@type": "Product",
		"name": "{nome}",
		{sku_json}
		"offers": [{{"@type": "Offer", "price": "{preco}", "priceCurrency": "BRL"}}]
	}}
	</script>
	</head><body><h1>{nome}</h1></body></html>
	"""


def _pagina_de_listagem(links: list[str]) -> str:
	itens = "".join(f'<a href="{link}">produto</a>' for link in links)
	return f"<html><body><nav>{itens}</nav></body></html>"


class TestExtracaoDeProduto(FrappeTestCase):
	def test_le_nome_preco_e_sku_do_json_ld(self):
		produto = precos_loja.extrair_produto(
			_pagina_json_ld("Distintivo de Especialidade Acampamento", "12,90", sku="EDU-001"),
			"https://loja.exemplo.test/acampamento",
		)

		self.assertEqual(produto["nome"], "Distintivo de Especialidade Acampamento")
		self.assertEqual(produto["preco"], 12.90)
		self.assertEqual(produto["codigo"], "EDU-001")
		self.assertEqual(produto["url"], "https://loja.exemplo.test/acampamento")

	def test_le_produto_aninhado_em_graph(self):
		html = """
		<html><head>
		<script type="application/ld+json">
		{"@context": "https://schema.org", "@graph": [
			{"@type": "BreadcrumbList"},
			{"@type": ["Product"], "name": "Insígnia Mundial", "mpn": "INS-9",
			 "offers": {"@type": "AggregateOffer", "lowPrice": 7.5}}
		]}
		</script>
		</head><body></body></html>
		"""

		produto = precos_loja.extrair_produto(html, "https://loja.exemplo.test/mundial")

		self.assertEqual(produto["nome"], "Insígnia Mundial")
		self.assertEqual(produto["preco"], 7.5)
		self.assertEqual(produto["codigo"], "INS-9")

	def test_cai_para_as_metatags_quando_nao_ha_json_ld(self):
		html = """
		<html><head>
		<meta property="og:title" content="Distintivo de Progressão Lobinho">
		<meta property="product:price:amount" content="R$ 1.234,56">
		<meta itemprop="sku" content="PRG-2">
		</head><body></body></html>
		"""

		produto = precos_loja.extrair_produto(html, "https://loja.exemplo.test/lobinho")

		self.assertEqual(produto["nome"], "Distintivo de Progressão Lobinho")
		self.assertEqual(produto["preco"], 1234.56)
		self.assertEqual(produto["codigo"], "PRG-2")

	def test_pagina_sem_produto_nao_vira_produto(self):
		self.assertIsNone(precos_loja.extrair_produto(_pagina_de_listagem(["/a", "/b"]), URL_CATEGORIA))

	def test_produto_sem_preco_e_descartado(self):
		html = """
		<html><head>
		<script type="application/ld+json">
		{"@type": "Product", "name": "Esgotado"}
		</script>
		</head><body></body></html>
		"""

		self.assertIsNone(precos_loja.extrair_produto(html, "https://loja.exemplo.test/esgotado"))


class TestConversaoDeValor(FrappeTestCase):
	def test_aceita_os_formatos_que_a_vitrine_usa(self):
		self.assertEqual(precos_loja._para_valor("R$ 12,90"), 12.90)
		self.assertEqual(precos_loja._para_valor("1.234,56"), 1234.56)
		self.assertEqual(precos_loja._para_valor("1,234.56"), 1234.56)
		self.assertEqual(precos_loja._para_valor("15.00"), 15.0)
		self.assertEqual(precos_loja._para_valor(9.9), 9.9)

	def test_descarta_o_que_nao_e_preco(self):
		self.assertIsNone(precos_loja._para_valor(""))
		self.assertIsNone(precos_loja._para_valor("sob consulta"))
		self.assertIsNone(precos_loja._para_valor(0))
		self.assertIsNone(precos_loja._para_valor(None))


class TestLinksDaVitrine(FrappeTestCase):
	def test_resolve_relativos_e_fica_no_mesmo_host(self):
		html = """
		<html><body>
		<a href="/educativo?page=2">2</a>
		<a href="produto-a">A</a>
		<a href="https://outra.test/produto-b">B</a>
		<a href="#topo">topo</a>
		<a href="/educativo?page=2">2 de novo</a>
		</body></html>
		"""

		links = precos_loja.extrair_links(html, URL_CATEGORIA)

		self.assertEqual(
			links,
			["https://loja.exemplo.test/educativo?page=2", "https://loja.exemplo.test/produto-a"],
		)


class TestColeta(FrappeTestCase):
	def test_segue_a_paginacao_e_recolhe_os_produtos(self):
		paginas = {
			URL_CATEGORIA: _pagina_de_listagem(["/p/acampamento", "/educativo?page=2"]),
			"https://loja.exemplo.test/educativo?page=2": _pagina_de_listagem(["/p/natacao"]),
			"https://loja.exemplo.test/p/acampamento": _pagina_json_ld("Acampamento", "12,90", "A-1"),
			"https://loja.exemplo.test/p/natacao": _pagina_json_ld("Natação", "13,50", "N-1"),
		}

		produtos = precos_loja.coletar_produtos(URL_CATEGORIA, baixar=paginas.get, pausa=0)

		self.assertEqual(sorted(produto["nome"] for produto in produtos), ["Acampamento", "Natação"])

	def test_nao_expande_links_de_pagina_de_produto(self):
		paginas = {
			URL_CATEGORIA: _pagina_de_listagem(["/p/acampamento"]),
			"https://loja.exemplo.test/p/acampamento": (
				_pagina_json_ld("Acampamento", "12,90") + _pagina_de_listagem(["/p/fundo-do-site"])
			),
			"https://loja.exemplo.test/p/fundo-do-site": _pagina_json_ld("Não deveria entrar", "99"),
		}
		lidas = []

		def baixar(url):
			lidas.append(url)
			return paginas.get(url)

		produtos = precos_loja.coletar_produtos(URL_CATEGORIA, baixar=baixar, pausa=0)

		self.assertEqual([produto["nome"] for produto in produtos], ["Acampamento"])
		self.assertNotIn("https://loja.exemplo.test/p/fundo-do-site", lidas)

	def test_pagina_que_falha_nao_derruba_a_coleta(self):
		def baixar(url):
			if url.endswith("/p/quebrada"):
				raise RuntimeError("500")
			return {
				URL_CATEGORIA: _pagina_de_listagem(["/p/quebrada", "/p/acampamento"]),
				"https://loja.exemplo.test/p/acampamento": _pagina_json_ld("Acampamento", "12,90"),
			}.get(url)

		produtos = precos_loja.coletar_produtos(URL_CATEGORIA, baixar=baixar, pausa=0)

		self.assertEqual([produto["nome"] for produto in produtos], ["Acampamento"])


class TestCasamento(FrappeTestCase):
	def test_ignora_a_embalagem_do_nome(self):
		self.assertEqual(
			precos_loja.normalizar("Distintivo de Especialidade Acampamento"),
			precos_loja.normalizar("Acampamento"),
		)

	def test_casa_pelo_codigo_antes_do_nome(self):
		itens = [
			{"name": "Acampamento", "nome": "Acampamento", "codigo": "A-1"},
			{"name": "Natação", "nome": "Natação", "codigo": None},
		]

		item, pontuacao, empate = precos_loja.encontrar_correspondencia(
			{"nome": "Nome completamente diferente", "codigo": "A-1"}, itens
		)

		self.assertEqual(item["name"], "Acampamento")
		self.assertEqual(pontuacao, 1.0)
		self.assertFalse(empate)

	def test_casa_por_semelhanca_de_nome(self):
		itens = [{"name": "Acampamento", "nome": "Acampamento", "codigo": None}]

		item, _, empate = precos_loja.encontrar_correspondencia(
			{"nome": "Distintivo de Especialidade Acampamento", "codigo": "A-1"}, itens
		)

		self.assertEqual(item["name"], "Acampamento")
		self.assertFalse(empate)

	def test_nome_distante_nao_casa(self):
		itens = [{"name": "Acampamento", "nome": "Acampamento", "codigo": None}]

		item, _, empate = precos_loja.encontrar_correspondencia(
			{"nome": "Camiseta Institucional", "codigo": None}, itens
		)

		self.assertIsNone(item)
		self.assertFalse(empate)

	def test_empate_tecnico_nao_escolhe_ninguem(self):
		itens = [
			{"name": "Ciclismo", "nome": "Ciclismo", "codigo": None},
			{"name": "Ciclismo ", "nome": "Ciclismo", "codigo": None},
		]

		item, _, empate = precos_loja.encontrar_correspondencia(
			{"nome": "Distintivo de Especialidade Ciclismo", "codigo": None}, itens
		)

		self.assertIsNone(item)
		self.assertTrue(empate)


class TestInferencia(FrappeTestCase):
	def test_tipo_vem_do_nome_do_produto(self):
		self.assertEqual(precos_loja.inferir_tipo("Distintivo de Especialidade Acampamento"), "Especialidade")
		self.assertEqual(
			precos_loja.inferir_tipo("Distintivo de Progressão Lobinho"), "Distintivo de Progressão"
		)
		self.assertEqual(precos_loja.inferir_tipo("Insígnia Mundial"), "Insígnia de Interesse Especial")
		self.assertEqual(precos_loja.inferir_tipo("Caneca do Grupo"), "Outro")

	def test_ramo_vem_do_nome_do_produto(self):
		self.assertEqual(precos_loja.inferir_ramo("Distintivo de Progressão Lobinho"), "Lobinho")
		self.assertEqual(precos_loja.inferir_ramo("Distintivo Sênior"), "Sênior")
		self.assertEqual(precos_loja.inferir_ramo("Distintivo de Especialidade Acampamento"), "Todos")


class TestImportacao(FrappeTestCase):
	def setUp(self):
		self.item = frappe.get_doc(
			{
				"doctype": precos_loja.DOCTYPE,
				"nome": "Teste Importação Acampamento",
				"tipo": "Especialidade",
				"ramo": "Todos",
				"valor_unitario": 1,
				"ativo": 1,
			}
		).insert()
		self.addCleanup(self._limpar)

	def _limpar(self):
		for nome in frappe.get_all(
			precos_loja.DOCTYPE, filters={"nome": ["like", "%Teste Importação%"]}, pluck="name"
		):
			frappe.delete_doc(precos_loja.DOCTYPE, nome, force=True)
		frappe.db.commit()

	def _paginas(self):
		return {
			URL_CATEGORIA: _pagina_de_listagem(["/p/acampamento", "/p/nova", "/p/caneca"]),
			"https://loja.exemplo.test/p/acampamento": _pagina_json_ld(
				"Distintivo de Especialidade Teste Importação Acampamento", "12,90", "TI-1"
			),
			"https://loja.exemplo.test/p/nova": _pagina_json_ld(
				"Distintivo de Especialidade Teste Importação Astronomia", "13,50", "TI-2"
			),
			"https://loja.exemplo.test/p/caneca": _pagina_json_ld("Caneca Teste Importação", "25,00", "TI-3"),
		}

	def test_atualiza_o_que_existe_e_cria_o_que_falta(self):
		relatorio = precos_loja.importar_precos_loja(url=URL_CATEGORIA, baixar=self._paginas().get, pausa=0)

		self.assertEqual(relatorio["atualizados"], 1)
		self.assertEqual(relatorio["criados"], 1)

		atualizado = frappe.get_doc(precos_loja.DOCTYPE, self.item.name)
		self.assertEqual(atualizado.valor_unitario, 12.90)
		self.assertEqual(atualizado.codigo, "TI-1")

		criado = frappe.get_doc(
			precos_loja.DOCTYPE, "Distintivo de Especialidade Teste Importação Astronomia"
		)
		self.assertEqual(criado.valor_unitario, 13.50)
		self.assertEqual(criado.codigo, "TI-2")
		self.assertEqual(criado.tipo, "Especialidade")

	def test_nao_cria_o_que_nao_e_distintivo(self):
		relatorio = precos_loja.importar_precos_loja(url=URL_CATEGORIA, baixar=self._paginas().get, pausa=0)

		self.assertEqual(relatorio["ignorados"], 1)
		self.assertFalse(frappe.db.exists(precos_loja.DOCTYPE, "Caneca Teste Importação"))

	def test_simulacao_relata_sem_gravar(self):
		relatorio = precos_loja.importar_precos_loja(
			url=URL_CATEGORIA, baixar=self._paginas().get, pausa=0, simular=True
		)

		self.assertTrue(relatorio["simulacao"])
		self.assertEqual(relatorio["atualizados"], 1)
		self.assertEqual(relatorio["criados"], 1)

		inalterado = frappe.get_doc(precos_loja.DOCTYPE, self.item.name)
		self.assertEqual(inalterado.valor_unitario, 1)
		self.assertIsNone(inalterado.codigo)
		self.assertFalse(
			frappe.db.exists(precos_loja.DOCTYPE, "Distintivo de Especialidade Teste Importação Astronomia")
		)

	def test_segunda_execucao_casa_pelo_codigo_e_nao_muda_nada(self):
		precos_loja.importar_precos_loja(url=URL_CATEGORIA, baixar=self._paginas().get, pausa=0)

		relatorio = precos_loja.importar_precos_loja(url=URL_CATEGORIA, baixar=self._paginas().get, pausa=0)

		self.assertEqual(relatorio["atualizados"], 0)
		self.assertEqual(relatorio["criados"], 0)
		self.assertEqual(relatorio["sem_alteracao"], 2)
