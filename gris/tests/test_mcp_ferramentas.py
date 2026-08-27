"""Testes das ferramentas MCP de associados e financeiro (guardas de escrita e filtros)."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from gris.api.mcp import associados, financeiro
from gris.api.mcp.registry import ErroDeFerramenta


def _campo(fieldtype="Data", options=None):
	return SimpleNamespace(fieldtype=fieldtype, options=options)


class TestListarAssociados(TestCase):
	def test_filtra_ativos_por_padrao_e_limita_pagina(self):
		with (
			patch.object(associados.frappe, "get_all", return_value=[]) as get_all,
			patch.object(associados.frappe.db, "count", return_value=0),
		):
			resultado = associados.listar_associados(limite=500)

		_, kwargs = get_all.call_args
		self.assertEqual(kwargs["filters"], {"status_no_grupo": "Ativo"})
		self.assertIsNone(kwargs["or_filters"])
		self.assertEqual(kwargs["limit_page_length"], 100)
		self.assertEqual(resultado["paginacao"]["limite"], 100)

	def test_status_todos_nao_filtra(self):
		with (
			patch.object(associados.frappe, "get_all", return_value=[]) as get_all,
			patch.object(associados.frappe.db, "count", return_value=0),
		):
			associados.listar_associados(status_no_grupo="Todos", ramo="Lobinho")

		self.assertEqual(get_all.call_args.kwargs["filters"], {"ramo": "Lobinho"})

	def test_busca_gera_or_filters(self):
		with (
			patch.object(associados.frappe, "get_all", return_value=[]) as get_all,
			patch.object(associados.frappe.db, "count", return_value=0),
		):
			associados.listar_associados(busca="ana")

		or_filters = get_all.call_args.kwargs["or_filters"]
		self.assertEqual(or_filters["nome_completo"], ["like", "%ana%"])
		self.assertIn("cpf", or_filters)


class TestAtualizarAssociado(TestCase):
	def test_recusa_campo_fora_da_allowlist(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			associados.atualizar_associado("123", {"cpf": "999", "telefone": "11999"})
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")
		self.assertIn("cpf", ctx.exception.mensagem)

	def test_recusa_dicionario_vazio(self):
		with self.assertRaises(ErroDeFerramenta):
			associados.atualizar_associado("123", {})

	def test_associado_inexistente(self):
		with patch.object(associados.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				associados.atualizar_associado("123", {"telefone": "11999"})
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_valida_opcoes_de_select(self):
		meta = MagicMock()
		meta.get_field.return_value = _campo("Select", "Ativo\nInativo")
		with (
			patch.object(associados.frappe.db, "exists", return_value=True),
			patch.object(associados.frappe, "get_doc", return_value=MagicMock()),
			patch.object(associados.frappe, "get_meta", return_value=meta),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				associados.atualizar_associado("123", {"status_no_grupo": "Afastado"})

		self.assertEqual(ctx.exception.detalhes["opcoes"], ["Ativo", "Inativo"])

	def test_valida_existencia_de_link(self):
		meta = MagicMock()
		meta.get_field.return_value = _campo("Link", "Unidade Organizacional")
		with (
			patch.object(associados.frappe.db, "exists", side_effect=[True, False]),
			patch.object(associados.frappe, "get_doc", return_value=MagicMock()),
			patch.object(associados.frappe, "get_meta", return_value=meta),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				associados.atualizar_associado("123", {"area": "Alcateia Fantasma"})

		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_nao_salva_quando_valor_e_igual(self):
		doc = MagicMock()
		doc.get.return_value = "11999999999"
		meta = MagicMock()
		meta.get_field.return_value = _campo("Data")
		with (
			patch.object(associados.frappe.db, "exists", return_value=True),
			patch.object(associados.frappe, "get_doc", return_value=doc),
			patch.object(associados.frappe, "get_meta", return_value=meta),
		):
			resultado = associados.atualizar_associado("123", {"telefone": "11999999999"})

		self.assertFalse(resultado["atualizado"])
		doc.save.assert_not_called()

	def test_grava_e_reporta_alteracoes(self):
		doc = MagicMock(name="doc")
		doc.name = "123"
		doc.get.return_value = "antigo"
		meta = MagicMock()
		meta.get_field.return_value = _campo("Data")
		with (
			patch.object(associados.frappe.db, "exists", return_value=True),
			patch.object(associados.frappe, "get_doc", return_value=doc),
			patch.object(associados.frappe, "get_meta", return_value=meta),
			patch.object(associados.frappe.db, "commit"),
		):
			resultado = associados.atualizar_associado("123", {"telefone": "11988887777"})

		doc.check_permission.assert_called_once_with("write")
		doc.set.assert_called_once_with("telefone", "11988887777")
		doc.save.assert_called_once_with()
		self.assertTrue(resultado["atualizado"])
		self.assertEqual(resultado["alteracoes"]["telefone"], {"de": "antigo", "para": "11988887777"})


class TestListarTransacoes(TestCase):
	def test_sem_categoria_filtra_vazios(self):
		with (
			patch.object(financeiro, "_pode_ver_descricao_completa", return_value=False),
			patch.object(financeiro.frappe, "get_all", return_value=[]) as get_all,
			patch.object(financeiro.frappe.db, "count", return_value=0),
		):
			financeiro.listar_transacoes(sem_categoria=True, revisada=False)

		filtros = get_all.call_args.kwargs["filters"]
		self.assertEqual(filtros["categoria"], ["in", [None, ""]])
		self.assertEqual(filtros["transacao_revisada"], 0)

	def test_periodo_usa_between(self):
		with (
			patch.object(financeiro, "_pode_ver_descricao_completa", return_value=True),
			patch.object(financeiro.frappe, "get_all", return_value=[]) as get_all,
			patch.object(financeiro.frappe.db, "count", return_value=0),
		):
			financeiro.listar_transacoes(data_inicio="2026-01-01", data_fim="2026-01-31")

		self.assertEqual(
			get_all.call_args.kwargs["filters"]["data_deposito"],
			["between", ["2026-01-01", "2026-01-31"]],
		)
		self.assertIn("descricao", get_all.call_args.kwargs["fields"])

	def test_descricao_completa_apenas_para_gestor(self):
		with (
			patch.object(financeiro, "_pode_ver_descricao_completa", return_value=False),
			patch.object(financeiro.frappe, "get_all", return_value=[]) as get_all,
			patch.object(financeiro.frappe.db, "count", return_value=0),
		):
			financeiro.listar_transacoes()

		self.assertNotIn("descricao", get_all.call_args.kwargs["fields"])

	def test_campo_data_invalido(self):
		with self.assertRaises(ErroDeFerramenta):
			financeiro.listar_transacoes(campo_data="criacao", data_inicio="2026-01-01")


class TestCategorizarTransacoes(TestCase):
	def test_exige_algum_campo(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			financeiro.categorizar_transacoes(["T1"])
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_exige_ids(self):
		with self.assertRaises(ErroDeFerramenta):
			financeiro.categorizar_transacoes(["", "  "], categoria="Doações")

	def test_valida_categoria_antes_de_gravar(self):
		with (
			patch.object(financeiro.frappe.db, "exists", return_value=False),
			patch.object(financeiro.frappe, "get_doc") as get_doc,
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				financeiro.categorizar_transacoes(["T1"], categoria="Inexistente")

		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")
		get_doc.assert_not_called()

	def test_aplica_campos_e_reporta_falhas(self):
		doc_ok = MagicMock()

		def get_doc(_doctype, name):
			if name == "T2":
				raise financeiro.frappe.DoesNotExistError("sumiu")
			return doc_ok

		with (
			patch.object(financeiro.frappe.db, "exists", return_value=True),
			patch.object(financeiro.frappe, "get_doc", side_effect=get_doc),
			patch.object(financeiro.frappe.db, "commit"),
		):
			resultado = financeiro.categorizar_transacoes(
				["T1", "T2"], categoria="Doações", marcar_revisada=True
			)

		self.assertEqual(resultado["atualizadas"], 1)
		self.assertEqual(resultado["solicitadas"], 2)
		self.assertEqual(resultado["falhas"][0]["id"], "T2")
		doc_ok.set.assert_any_call("categoria", "Doações")
		doc_ok.set.assert_any_call("transacao_revisada", 1)
		doc_ok.save.assert_called_once_with()


class TestResumoFinanceiro(TestCase):
	def test_agrupa_creditos_e_debitos(self):
		linhas = [
			{
				"categoria": "Contribuições",
				"debito_credito": "Crédito",
				"total_absoluto": 1000.0,
				"quantidade": 4,
			},
			{
				"categoria": "Contribuições",
				"debito_credito": "Débito",
				"total_absoluto": 250.0,
				"quantidade": 1,
			},
			{"categoria": None, "debito_credito": "Débito", "total_absoluto": 100.0, "quantidade": 2},
		]
		with patch.object(financeiro.frappe, "get_all", return_value=linhas) as get_all:
			resultado = financeiro.resumo_financeiro(data_inicio="2026-01-01", data_fim="2026-01-31")

		self.assertEqual(get_all.call_args.kwargs["filters"]["excluir_do_total"], 0)
		self.assertEqual(resultado["totais"], {"credito": 1000.0, "debito": 350.0, "saldo": 650.0})

		por_grupo = {g["grupo"]: g for g in resultado["grupos"]}
		self.assertEqual(por_grupo["Contribuições"]["saldo"], 750.0)
		self.assertEqual(por_grupo["Contribuições"]["quantidade"], 5)
		self.assertEqual(por_grupo["(sem valor)"]["debito"], 100.0)

	def test_usa_valor_liquido_quando_absoluto_esta_vazio(self):
		linhas = [
			{
				"carteira": "Caixa",
				"debito_credito": "Débito",
				"total_absoluto": None,
				"total_liquido": -300.0,
				"quantidade": 1,
			}
		]
		with patch.object(financeiro.frappe, "get_all", return_value=linhas):
			resultado = financeiro.resumo_financeiro(agrupar_por="carteira")

		self.assertEqual(resultado["totais"]["debito"], 300.0)


class TestSimulacaoNasEscritas(TestCase):
	def test_atualizar_associado_simulado_nao_salva(self):
		doc = MagicMock()
		doc.name = "123"
		doc.get.return_value = "antigo"
		meta = MagicMock()
		meta.get_field.return_value = _campo("Data")
		with (
			patch.object(associados.frappe.db, "exists", return_value=True),
			patch.object(associados.frappe, "get_doc", return_value=doc),
			patch.object(associados.frappe, "get_meta", return_value=meta),
		):
			resultado = associados.atualizar_associado("123", {"telefone": "11988887777"}, simular=True)

		doc.save.assert_not_called()
		doc.set.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["alteracoes"]["telefone"], {"de": "antigo", "para": "11988887777"})

	def test_categorizar_simulado_monta_previa_sem_abrir_documentos(self):
		def get_value(_doctype, name, _campos, as_dict=True):
			if name == "T2":
				return None
			return {"categoria": "Outros"}

		with (
			patch.object(financeiro.frappe.db, "exists", return_value=True),
			patch.object(financeiro.frappe, "has_permission", return_value=True),
			patch.object(financeiro.frappe.db, "get_value", side_effect=get_value),
			patch.object(financeiro.frappe, "get_doc") as get_doc,
		):
			resultado = financeiro.categorizar_transacoes(["T1", "T2"], categoria="Doações", simular=True)

		get_doc.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["atualizadas"], 0)
		self.assertEqual(
			resultado["previa"][0]["alteracoes"]["categoria"], {"de": "Outros", "para": "Doações"}
		)
		self.assertEqual(resultado["falhas"][0]["id"], "T2")

	def test_categorizar_simulado_sem_permissao_de_escrita(self):
		with (
			patch.object(financeiro.frappe.db, "exists", return_value=True),
			patch.object(financeiro.frappe, "has_permission", return_value=False),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				financeiro.categorizar_transacoes(["T1"], categoria="Doações", simular=True)

		self.assertEqual(ctx.exception.codigo, "PERMISSAO_NEGADA")
