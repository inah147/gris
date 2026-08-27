"""Testes das ferramentas MCP de previsão orçamentária e das séries do painel."""

from unittest import TestCase
from unittest.mock import patch

from gris.api.financeiro import dashboard
from gris.api.mcp import financeiro, orcamento
from gris.api.mcp.registry import ErroDeFerramenta

PREVISAO = {"name": "PREV-1", "titulo": "Orçamento 2026", "status": "Rascunho"}


class TestLeituraDoOrcamento(TestCase):
	def test_listar_delega_com_filtros(self):
		with patch.object(orcamento.servico, "listar_previsoes", return_value=[PREVISAO]) as servico:
			resultado = orcamento.listar_previsoes_orcamentarias(exercicio=2026, status="Rascunho")

		servico.assert_called_once_with(exercicio=2026, status="Rascunho")
		self.assertEqual(resultado["total"], 1)

	def test_obter_previsao_inexistente(self):
		with patch.object(orcamento.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				orcamento.obter_previsao_orcamentaria("PREV-9")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")


COMPARATIVO = {
	"success": True,
	"previsao": PREVISAO,
	"meses_decorridos": 3,
	"labels": ["01/26", "02/26"],
	"series": {
		"receitas_previstas": [100.0, 100.0],
		"receitas_realizadas": [90.0, 120.0],
	},
	"totais": {"receitas_previstas": 200.0, "receitas_realizadas": 210.0},
	"por_categoria": {"receitas": [], "despesas": []},
	"por_centro_de_custo": {"receitas": [], "despesas": []},
}

GRAFICO = {
	"labels": ["01/26", "02/26"],
	"datasets": [
		{"name": "Entradas", "values": [100.0, 150.0]},
		{"name": "Saídas", "values": [80.0, 90.0]},
	],
}


class TestComparativo(TestCase):
	def test_omite_series_por_padrao(self):
		with (
			patch.object(orcamento.frappe.db, "get_value", return_value=PREVISAO),
			patch.object(orcamento.servico, "obter_comparativo", return_value=COMPARATIVO),
		):
			resultado = orcamento.comparar_previsto_realizado("PREV-1")

		self.assertNotIn("por_mes", resultado)
		self.assertNotIn("success", resultado)
		self.assertEqual(resultado["totais"]["receitas_realizadas"], 210.0)

	def test_series_viram_linhas_por_mes(self):
		with (
			patch.object(orcamento.frappe.db, "get_value", return_value=PREVISAO),
			patch.object(orcamento.servico, "obter_comparativo", return_value=COMPARATIVO),
		):
			resultado = orcamento.comparar_previsto_realizado("PREV-1", incluir_series_mensais=True)

		self.assertEqual(
			resultado["por_mes"][1],
			{"mes": "02/26", "receitas_previstas": 100.0, "receitas_realizadas": 120.0},
		)


class TestCriarPrevisao(TestCase):
	def test_recusa_periodo_invertido(self):
		with self.assertRaises(ErroDeFerramenta):
			orcamento.criar_previsao_orcamentaria("Orçamento", 2027, "2027-12-31", "2027-01-01")

	def test_recusa_centro_de_custo_inexistente(self):
		with patch.object(orcamento.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				orcamento.criar_previsao_orcamentaria(
					"Orçamento", 2027, "2027-01-01", "2027-12-31", centro_de_custo="Sede"
				)
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_simulacao_nao_cria(self):
		with patch.object(orcamento.servico, "criar_previsao") as servico:
			resultado = orcamento.criar_previsao_orcamentaria(
				"Orçamento 2027", 2027, "2027-01-01", "2027-12-31", itens=[{"tipo": "Receita"}], simular=True
			)

		servico.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["previsao"]["quantidade_de_itens"], 1)

	def test_execucao_delega(self):
		with patch.object(orcamento.servico, "criar_previsao", return_value={"name": "PREV-2"}) as servico:
			resultado = orcamento.criar_previsao_orcamentaria(
				"Orçamento 2027", 2027, "2027-01-01", "2027-12-31"
			)

		self.assertEqual(servico.call_args.kwargs["titulo"], "Orçamento 2027")
		self.assertEqual(resultado["name"], "PREV-2")


class TestAtualizarPrevisao(TestCase):
	def test_exige_algum_campo(self):
		with patch.object(orcamento.frappe.db, "get_value", return_value=PREVISAO):
			with self.assertRaises(ErroDeFerramenta):
				orcamento.atualizar_previsao_orcamentaria("PREV-1")

	def test_sem_mudanca_nao_grava(self):
		with (
			patch.object(orcamento.frappe.db, "get_value", side_effect=[PREVISAO, {"status": "Rascunho"}]),
			patch.object(orcamento.servico, "atualizar_previsao") as servico,
		):
			resultado = orcamento.atualizar_previsao_orcamentaria("PREV-1", status="Rascunho")

		servico.assert_not_called()
		self.assertFalse(resultado["atualizada"])

	def test_simulacao_mostra_alteracoes(self):
		with (
			patch.object(orcamento.frappe.db, "get_value", side_effect=[PREVISAO, {"status": "Rascunho"}]),
			patch.object(orcamento.servico, "atualizar_previsao") as servico,
		):
			resultado = orcamento.atualizar_previsao_orcamentaria("PREV-1", status="Aprovada", simular=True)

		servico.assert_not_called()
		self.assertEqual(resultado["alteracoes"]["status"], {"de": "Rascunho", "para": "Aprovada"})

	def test_execucao_delega(self):
		with (
			patch.object(orcamento.frappe.db, "get_value", side_effect=[PREVISAO, {"status": "Rascunho"}]),
			patch.object(orcamento.servico, "atualizar_previsao") as servico,
		):
			resultado = orcamento.atualizar_previsao_orcamentaria("PREV-1", status="Aprovada")

		servico.assert_called_once_with(name="PREV-1", status="Aprovada")
		self.assertTrue(resultado["atualizada"])


class TestItensDaPrevisao(TestCase):
	def test_recusa_previsao_encerrada(self):
		encerrada = dict(PREVISAO, status="Encerrada")
		with patch.object(orcamento.frappe.db, "get_value", return_value=encerrada):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				orcamento.salvar_item_previsao("PREV-1", "Receita", "Rifa", 500)
		self.assertEqual(ctx.exception.codigo, "VALIDACAO")

	def test_mes_especifico_exige_mes_referencia(self):
		with patch.object(orcamento.frappe.db, "get_value", return_value=PREVISAO):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				orcamento.salvar_item_previsao(
					"PREV-1",
					"Receita",
					"Rifa",
					500,
					distribuicao=orcamento.servico.DISTRIBUICAO_MES_ESPECIFICO,
				)
		self.assertIn("mes_referencia", ctx.exception.mensagem)

	def test_recusa_categoria_inexistente(self):
		with (
			patch.object(orcamento.frappe.db, "get_value", return_value=PREVISAO),
			patch.object(orcamento.frappe.db, "exists", return_value=False),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				orcamento.salvar_item_previsao("PREV-1", "Receita", "Rifa", 500, categoria="Fantasia")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_simulacao_nao_grava_item(self):
		with (
			patch.object(orcamento.frappe.db, "get_value", return_value=PREVISAO),
			patch.object(orcamento.servico, "salvar_item") as servico,
		):
			resultado = orcamento.salvar_item_previsao("PREV-1", "Despesa", "Sede", 300, simular=True)

		servico.assert_not_called()
		self.assertEqual(resultado["operacao"], "criacao")
		self.assertTrue(resultado["simulacao"])

	def test_execucao_identifica_atualizacao(self):
		with (
			patch.object(orcamento.frappe.db, "get_value", return_value=PREVISAO),
			patch.object(orcamento.servico, "salvar_item") as servico,
		):
			resultado = orcamento.salvar_item_previsao("PREV-1", "Despesa", "Sede", 300, item_name="ITEM-1")

		servico.assert_called_once()
		self.assertEqual(servico.call_args.kwargs["item_name"], "ITEM-1")
		self.assertEqual(resultado["operacao"], "atualizacao")

	def test_excluir_item_inexistente(self):
		with (
			patch.object(orcamento.frappe.db, "get_value", return_value=PREVISAO),
			patch.object(orcamento.servico, "obter_previsao", return_value={"itens": []}),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				orcamento.excluir_item_previsao("PREV-1", "ITEM-9")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_excluir_item_simulado_e_real(self):
		itens = {"itens": [{"name": "ITEM-1", "descricao": "Sede"}]}
		with (
			patch.object(orcamento.frappe.db, "get_value", return_value=PREVISAO),
			patch.object(orcamento.servico, "obter_previsao", return_value=itens),
			patch.object(orcamento.servico, "excluir_item") as servico,
		):
			simulado = orcamento.excluir_item_previsao("PREV-1", "ITEM-1", simular=True)
			real = orcamento.excluir_item_previsao("PREV-1", "ITEM-1")

		servico.assert_called_once_with(previsao="PREV-1", item_name="ITEM-1")
		self.assertTrue(simulado["simulacao"])
		self.assertTrue(real["excluido"])


class TestSerieFinanceira(TestCase):
	def test_serie_invalida(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			financeiro.serie_financeira(serie="inexistente")
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_tabula_por_mes_e_totaliza(self):
		with patch.object(dashboard, "get_entradas_saidas_mensal", autospec=True, return_value=GRAFICO):
			resultado = financeiro.serie_financeira()

		self.assertEqual(resultado["por_mes"][0], {"mes": "01/26", "Entradas": 100.0, "Saídas": 80.0})
		self.assertEqual(resultado["totais"], {"Entradas": 250.0, "Saídas": 170.0})

	def test_passa_apenas_filtros_aceitos_pela_serie(self):
		with patch.object(
			dashboard, "get_entradas_credito_mensal_por_tipo", autospec=True, return_value=GRAFICO
		) as funcao:
			resultado = financeiro.serie_financeira(
				serie="entradas_por_tipo",
				carteira="Caixa",
				ordinaria_extraordinaria="Ordinária",
			)

		funcao.assert_called_once_with(carteira="Caixa")
		self.assertEqual(resultado["filtros_ignorados"], ["ordinaria_extraordinaria"])

	def test_serie_sem_filtros_nao_recebe_argumentos(self):
		with patch.object(
			dashboard, "get_contribuicoes_mensais_inadimplencia", autospec=True, return_value=GRAFICO
		) as funcao:
			financeiro.serie_financeira(serie="inadimplencia_mensal", categoria="Doações")

		funcao.assert_called_once_with()
