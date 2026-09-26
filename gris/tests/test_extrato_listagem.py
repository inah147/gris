"""Testes da listagem do extrato (grid compacto com scroll infinito).

Cobrem a montagem de filtros a partir da query string, a paginação estável dos
lotes e o contrato do endpoint que alimenta o scroll infinito.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro.transactions import (
	EXTRATO_COLUNAS,
	EXTRATO_FILTRO_VAZIO,
	EXTRATO_LARGURA_MAX,
	EXTRATO_LARGURA_MIN,
	EXTRATO_MAX_PAGE_SIZE,
	EXTRATO_ORDER_BY,
	EXTRATO_PAGE_SIZE,
	aplicar_preferencias_extrato,
	build_extrato_filters,
	get_extrato_colunas,
	get_extrato_rows,
	get_preferencias_extrato,
	normalizar_preferencias_extrato,
	render_extrato_rows,
	salvar_preferencias_extrato,
)

DOCTYPE = "Transacao Extrato Geral"


class TestExtratoFiltros(FrappeTestCase):
	def test_sem_argumentos_gera_apenas_o_filtro_padrao_de_exclusao(self):
		# `excluir_do_total` é sempre aplicado por padrão para não contar/exibir
		# duplicatas conciliadas, mesmo sem nenhum filtro explícito na URL.
		self.assertEqual(build_extrato_filters(None), {"excluir_do_total": 0})
		self.assertEqual(build_extrato_filters({}), {"excluir_do_total": 0})

	def test_filtro_de_exclusao_pode_ser_sobrescrito_explicitamente(self):
		filtros = build_extrato_filters({"excluir_do_total": "1"})
		self.assertEqual(filtros["excluir_do_total"], "1")

	def test_mostrar_excluidas_remove_o_filtro_padrao_de_exclusao(self):
		self.assertEqual(build_extrato_filters({"mostrar_excluidas": "1"}), {})
		self.assertEqual(build_extrato_filters({"mostrar_excluidas": "on"}), {})
		self.assertEqual(build_extrato_filters({"mostrar_excluidas": "0"}), {"excluir_do_total": 0})

	def test_mostrar_excluidas_nao_sobrescreve_filtro_explicito(self):
		filtros = build_extrato_filters({"mostrar_excluidas": "1", "excluir_do_total": "1"})
		self.assertEqual(filtros, {"excluir_do_total": "1"})

	def test_intervalo_de_datas_completo(self):
		filtros = build_extrato_filters({"data_inicio": "2026-01-01", "data_fim": "2026-01-31"})
		self.assertEqual(filtros["data_deposito"], ["between", ["2026-01-01", "2026-01-31"]])

	def test_apenas_data_inicio_ou_data_fim(self):
		self.assertEqual(
			build_extrato_filters({"data_inicio": "2026-01-01"})["data_deposito"],
			[">=", "2026-01-01"],
		)
		self.assertEqual(
			build_extrato_filters({"data_fim": "2026-01-31"})["data_deposito"],
			["<=", "2026-01-31"],
		)

	def test_data_invalida_e_ignorada(self):
		self.assertEqual(build_extrato_filters({"data_inicio": "não é data"}), {"excluir_do_total": 0})

	def test_campos_permitidos_viram_filtro_de_igualdade(self):
		filtros = build_extrato_filters({"instituicao": "BTG Empresas", "fonte": "Sistema"})
		self.assertEqual(filtros, {"instituicao": "BTG Empresas", "fonte": "Sistema", "excluir_do_total": 0})

	def test_valores_vazios_e_campos_desconhecidos_sao_descartados(self):
		filtros = build_extrato_filters(
			{"instituicao": "", "carteira": "null", "categoria": None, "page": "3"}
		)
		self.assertEqual(filtros, {"excluir_do_total": 0})

	def test_sem_categoria_filtra_categoria_vazia(self):
		filtros = build_extrato_filters({"categoria": EXTRATO_FILTRO_VAZIO})
		self.assertEqual(filtros["categoria"], ["is", "not set"])

	def test_valor_vazio_especial_so_vale_para_campos_previstos(self):
		filtros = build_extrato_filters({"instituicao": EXTRATO_FILTRO_VAZIO})
		self.assertEqual(filtros["instituicao"], EXTRATO_FILTRO_VAZIO)

	def test_busca_por_descricao_gera_like_case_insensitive_na_descricao_reduzida(self):
		filtros = build_extrato_filters({"descricao": "Pix"})
		self.assertEqual(filtros["descricao_reduzida"], ["like", "%Pix%"])

	def test_busca_por_descricao_vazia_e_ignorada(self):
		self.assertEqual(build_extrato_filters({"descricao": ""}), {"excluir_do_total": 0})
		self.assertEqual(build_extrato_filters({"descricao": "null"}), {"excluir_do_total": 0})

	def test_busca_por_descricao_escapa_curingas_do_like(self):
		filtros = build_extrato_filters({"descricao": "50%_off"})
		self.assertEqual(filtros["descricao_reduzida"], ["like", r"%50\%\_off%"])

	def test_busca_por_descricao_completa_e_ignorada_sem_permissao(self):
		filtros = build_extrato_filters({"descricao_completa": "Pix"})
		self.assertEqual(filtros, {"excluir_do_total": 0})
		filtros = build_extrato_filters({"descricao_completa": "Pix"}, pode_buscar_descricao_completa=False)
		self.assertEqual(filtros, {"excluir_do_total": 0})

	def test_busca_por_descricao_completa_gera_like_quando_permitido(self):
		filtros = build_extrato_filters({"descricao_completa": "Pix"}, pode_buscar_descricao_completa=True)
		self.assertEqual(filtros["descricao"], ["like", "%Pix%"])

	def test_busca_por_descricao_completa_vazia_e_ignorada(self):
		self.assertEqual(
			build_extrato_filters({"descricao_completa": ""}, pode_buscar_descricao_completa=True),
			{"excluir_do_total": 0},
		)
		self.assertEqual(
			build_extrato_filters({"descricao_completa": "null"}, pode_buscar_descricao_completa=True),
			{"excluir_do_total": 0},
		)

	def test_busca_por_descricao_completa_escapa_curingas_do_like(self):
		filtros = build_extrato_filters(
			{"descricao_completa": "50%_off"}, pode_buscar_descricao_completa=True
		)
		self.assertEqual(filtros["descricao"], ["like", r"%50\%\_off%"])

	def test_ordenacao_tem_desempate_para_paginacao_estavel(self):
		# Sem o desempate por `name`, lotes com timestamps iguais repetiriam linhas.
		self.assertIn("name desc", EXTRATO_ORDER_BY)


class TestExtratoLinhas(FrappeTestCase):
	def test_render_sem_transacoes_devolve_html_vazio(self):
		self.assertEqual(render_extrato_rows([], get_extrato_colunas()).strip(), "")

	def test_render_usa_id_da_transacao_e_escapa_descricao(self):
		transacoes = [
			{
				"name": "TX-0001",
				"transacao_revisada": 0,
				"timestamp_transacao": None,
				"valor": 1234.5,
				"descricao_reduzida": "<script>alert(1)</script>",
				"instituicao": "BTG Empresas",
				"fonte": "Sistema",
				"carteira": None,
				"categoria": None,
				"centro_de_custo": None,
				"status_conciliacao": None,
			}
		]
		html = render_extrato_rows(transacoes, get_extrato_colunas())
		self.assertIn('data-transaction-id="TX-0001"', html)
		self.assertIn("R$ 1.234,50", html)
		# O Jinja do Frappe não tem autoescape: a escapagem é explícita no template.
		self.assertNotIn("<script>alert(1)</script>", html)
		self.assertIn("&lt;script&gt;", html)

	def test_render_escapa_texto_dos_badges(self):
		transacoes = [
			{
				"name": "TX-0003",
				"transacao_revisada": 0,
				"timestamp_transacao": None,
				"valor": 0,
				"descricao_reduzida": "Compra",
				"instituicao": '<img src=x onerror="alert(1)">',
				"fonte": "Planilha",
				"carteira": None,
				"categoria": None,
				"centro_de_custo": None,
				"status_conciliacao": None,
			}
		]
		html = render_extrato_rows(transacoes, get_extrato_colunas())
		self.assertNotIn("<img", html)
		self.assertIn("&lt;img", html)

	def test_todas_as_colunas_do_doctype_estao_disponiveis(self):
		meta = frappe.get_meta(DOCTYPE)
		campos_do_doctype = {
			f.fieldname
			for f in meta.fields
			if f.fieldtype not in ("Section Break", "Column Break", "Tab Break", "HTML", "Table")
		}
		self.assertEqual(campos_do_doctype - {c["key"] for c in EXTRATO_COLUNAS}, set())

	def test_colunas_padrao_sao_um_subconjunto_util(self):
		padrao = [c for c in EXTRATO_COLUNAS if c.get("padrao")]
		self.assertTrue(padrao)
		self.assertLess(len(padrao), len(EXTRATO_COLUNAS))
		# As demais existem, mas entram escondidas até o usuário ligar.
		self.assertIn("observacoes", {c["key"] for c in EXTRATO_COLUNAS if not c.get("padrao")})

	def test_origem_da_venda_vem_visivel_por_padrao(self):
		# Diz se o recebimento Infinitepay veio do site (Link Integrado), da
		# maquininha etc.; oculta, a informação importada não aparecia na lista.
		self.assertIn("origem_venda", {c["key"] for c in EXTRATO_COLUNAS if c.get("padrao")})

	def test_coluna_restrita_so_aparece_para_gestor_financeiro(self):
		chaves_livres = {c["key"] for c in get_extrato_colunas(False)}
		chaves_gestor = {c["key"] for c in get_extrato_colunas(True)}
		self.assertNotIn("descricao", chaves_livres)
		self.assertIn("descricao", chaves_gestor)

	def test_render_marca_cada_celula_com_a_chave_da_coluna(self):
		colunas = get_extrato_colunas()
		html = render_extrato_rows(
			[{"name": "TX-0004", "descricao_reduzida": "Compra", "fonte": "Sistema"}], colunas
		)
		for coluna in colunas:
			self.assertIn(f'data-col="{coluna["key"]}"', html)

	def test_render_so_inclui_descricao_completa_quando_permitido(self):
		transacoes = [
			{
				"name": "TX-0002",
				"transacao_revisada": 1,
				"timestamp_transacao": None,
				"valor": None,
				"descricao_reduzida": "Compra",
				"descricao": "Descricao completa da compra",
				"instituicao": None,
				"fonte": "Planilha",
				"carteira": None,
				"categoria": None,
				"centro_de_custo": None,
				"status_conciliacao": None,
			}
		]
		self.assertIn(
			"Descricao completa da compra", render_extrato_rows(transacoes, get_extrato_colunas(True))
		)
		self.assertNotIn(
			"Descricao completa da compra", render_extrato_rows(transacoes, get_extrato_colunas())
		)


class TestExtratoRowsEndpoint(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.form_dict = frappe._dict()

	def test_guest_nao_acessa(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				get_extrato_rows()
		finally:
			frappe.set_user("Administrator")

	def test_retorno_tem_contrato_esperado(self):
		resposta = get_extrato_rows(filtros="{}", start=0, page_length=5)
		self.assertIn("html", resposta)
		self.assertIsInstance(resposta["count"], int)
		self.assertIsInstance(resposta["has_more"], bool)
		self.assertLessEqual(resposta["count"], 5)

	def test_filtros_invalidos_nao_quebram_a_chamada(self):
		resposta = get_extrato_rows(filtros="isto não é json", start=-10)
		self.assertIn("html", resposta)

	def test_page_length_respeita_o_teto(self):
		total = frappe.db.count(DOCTYPE)
		resposta = get_extrato_rows(page_length=10_000)
		self.assertLessEqual(resposta["count"], min(EXTRATO_MAX_PAGE_SIZE, max(total, 0)))

	def test_page_size_padrao_e_maior_que_a_paginacao_antiga(self):
		self.assertGreaterEqual(EXTRATO_PAGE_SIZE, 100)


class TestExtratoPreferenciasColunas(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.chaves = [coluna["key"] for coluna in EXTRATO_COLUNAS]

	def tearDown(self):
		frappe.set_user("Administrator")
		salvar_preferencias_extrato(None)

	def test_normalizacao_descarta_colunas_desconhecidas_e_duplicadas(self):
		preferencias = normalizar_preferencias_extrato(
			{
				"ordem": ["valor", "nao_existe", "valor", 3, "categoria"],
				"larguras": {"valor": 5, "categoria": 10_000, "nao_existe": 100, "carteira": "abc"},
				"visiveis": {"valor": False, "nao_existe": True, "categoria": "sim"},
				"extra": "ignorado",
			}
		)
		self.assertEqual(preferencias["ordem"], ["valor", "categoria"])
		self.assertEqual(
			preferencias["larguras"], {"valor": EXTRATO_LARGURA_MIN, "categoria": EXTRATO_LARGURA_MAX}
		)
		self.assertEqual(preferencias["visiveis"], {"valor": False})
		self.assertNotIn("extra", preferencias)

	def test_normalizacao_de_valor_invalido_vira_padrao(self):
		self.assertEqual(normalizar_preferencias_extrato(None), {})
		self.assertEqual(normalizar_preferencias_extrato("texto"), {})

	def test_sem_preferencia_mantem_ordem_e_visibilidade_padrao(self):
		colunas = aplicar_preferencias_extrato(list(EXTRATO_COLUNAS), None)
		self.assertEqual([coluna["key"] for coluna in colunas], self.chaves)
		for coluna in colunas:
			self.assertEqual(coluna["visivel"], bool(coluna.get("padrao")))
			self.assertIsNone(coluna["largura_px"])

	def test_ordem_salva_vem_primeiro_e_colunas_novas_vao_para_o_fim(self):
		colunas = aplicar_preferencias_extrato(
			list(EXTRATO_COLUNAS),
			{"ordem": ["valor", "categoria"], "larguras": {"valor": 150}, "visiveis": {"id": True}},
		)
		chaves = [coluna["key"] for coluna in colunas]
		self.assertEqual(chaves[:2], ["valor", "categoria"])
		# As demais seguem na ordem do sistema.
		self.assertEqual(chaves[2:], [c for c in self.chaves if c not in ("valor", "categoria")])
		por_chave = {coluna["key"]: coluna for coluna in colunas}
		self.assertEqual(por_chave["valor"]["largura_px"], 150)
		self.assertTrue(por_chave["id"]["visivel"])
		# A ordem padrão fica disponível para o "Restaurar padrão" da tela.
		self.assertEqual(por_chave["valor"]["ordem_padrao"], self.chaves.index("valor"))

	def test_nao_altera_o_registro_global_de_colunas(self):
		aplicar_preferencias_extrato(list(EXTRATO_COLUNAS), {"larguras": {"valor": 150}})
		self.assertNotIn("largura_px", EXTRATO_COLUNAS[0])

	def test_salvar_e_ler_preferencias_do_usuario(self):
		salvar_preferencias_extrato('{"ordem": ["valor"], "larguras": {"valor": 200}}')
		self.assertEqual(get_preferencias_extrato(), {"ordem": ["valor"], "larguras": {"valor": 200}})
		gravado = frappe.db.sql(
			"select data from `__UserSettings` where user=%s and doctype=%s",
			("Administrator", DOCTYPE),
		)
		self.assertIn("gris_extrato_portal", gravado[0][0])

	def test_preferencias_sao_por_usuario(self):
		salvar_preferencias_extrato({"ordem": ["valor"]})
		frappe.set_user("Guest")
		self.assertIsNone(get_preferencias_extrato())

	def test_restaurar_padrao_limpa_a_preferencia(self):
		salvar_preferencias_extrato({"ordem": ["valor"]})
		salvar_preferencias_extrato(None)
		self.assertEqual(get_preferencias_extrato(), {})

	def test_guest_nao_salva(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			salvar_preferencias_extrato({"ordem": ["valor"]})

	def test_linhas_do_scroll_seguem_a_ordem_salva(self):
		salvar_preferencias_extrato({"ordem": ["valor", "transacao_revisada"]})
		html = render_extrato_rows(
			[{"name": "T-1", "valor": 10, "transacao_revisada": 0}],
			aplicar_preferencias_extrato(get_extrato_colunas(), get_preferencias_extrato()),
		)
		self.assertLess(html.index('data-col="valor"'), html.index('data-col="transacao_revisada"'))
