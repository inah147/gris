"""Testes da listagem do extrato (grid compacto com scroll infinito).

Cobrem a montagem de filtros a partir da query string, a paginação estável dos
lotes e o contrato do endpoint que alimenta o scroll infinito.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gris.api.financeiro.transactions import (
	EXTRATO_COLUNAS,
	EXTRATO_MAX_PAGE_SIZE,
	EXTRATO_ORDER_BY,
	EXTRATO_PAGE_SIZE,
	build_extrato_filters,
	get_extrato_colunas,
	get_extrato_rows,
	render_extrato_rows,
)

DOCTYPE = "Transacao Extrato Geral"


class TestExtratoFiltros(FrappeTestCase):
	def test_sem_argumentos_nao_gera_filtro(self):
		self.assertEqual(build_extrato_filters(None), {})
		self.assertEqual(build_extrato_filters({}), {})

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
		self.assertEqual(build_extrato_filters({"data_inicio": "não é data"}), {})

	def test_campos_permitidos_viram_filtro_de_igualdade(self):
		filtros = build_extrato_filters({"instituicao": "BTG Empresas", "fonte": "Sistema"})
		self.assertEqual(filtros, {"instituicao": "BTG Empresas", "fonte": "Sistema"})

	def test_valores_vazios_e_campos_desconhecidos_sao_descartados(self):
		filtros = build_extrato_filters(
			{"instituicao": "", "carteira": "null", "categoria": None, "descricao": "x", "page": "3"}
		)
		self.assertEqual(filtros, {})

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
