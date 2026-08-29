"""Testes das ferramentas MCP de insígnias e distintivos."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from gris.api.mcp import insignias
from gris.api.mcp.registry import ErroDeFerramenta

SESSAO_ESCOTISTA = SimpleNamespace(user="escotista@exemplo.com")

CATALOGO = [
	{
		"name": "Distintivo de Progressão I",
		"nome": "Distintivo de Progressão I",
		"tipo": "Distintivo de Progressão",
		"ramo": "Lobinho",
		"ativo": True,
		"valor_unitario": 12.5,
	},
	{
		"name": "Insígnia Inativa",
		"nome": "Insígnia Inativa",
		"tipo": "Especialidade",
		"ramo": "Todos",
		"ativo": False,
		"valor_unitario": 8.0,
	},
]


class TestListarCatalogoInsignias(TestCase):
	def test_apenas_ativos_por_padrao(self):
		with patch.object(insignias.consultas, "listar_catalogo_completo", return_value=CATALOGO):
			resultado = insignias.listar_catalogo_insignias()

		self.assertEqual(resultado["total"], 1)
		self.assertEqual(resultado["catalogo"][0]["name"], "Distintivo de Progressão I")

	def test_filtra_por_tipo_e_ramo(self):
		with patch.object(insignias.consultas, "listar_catalogo_completo", return_value=CATALOGO):
			resultado = insignias.listar_catalogo_insignias(apenas_ativos=False, tipo="Especialidade")

		self.assertEqual(resultado["total"], 1)
		self.assertEqual(resultado["catalogo"][0]["name"], "Insígnia Inativa")


class TestSalvarItemCatalogo(TestCase):
	def test_recusa_tipo_invalido(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			insignias.salvar_item_catalogo_insignias(tipo="Fantasia", ramo="Todos", valor_unitario=1)
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_recusa_ramo_invalido(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			insignias.salvar_item_catalogo_insignias(tipo="Especialidade", ramo="Marte", valor_unitario=1)
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_recusa_valor_negativo(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			insignias.salvar_item_catalogo_insignias(tipo="Especialidade", ramo="Todos", valor_unitario=-1)
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_criacao_exige_nome_com_tres_caracteres(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			insignias.salvar_item_catalogo_insignias(
				nome="Ab", tipo="Especialidade", ramo="Todos", valor_unitario=1
			)
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_edicao_de_item_inexistente(self):
		with patch.object(insignias.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				insignias.salvar_item_catalogo_insignias(
					name="ITEM-9", tipo="Especialidade", ramo="Todos", valor_unitario=1
				)
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_simulacao_nao_grava(self):
		with (
			patch.object(insignias.frappe.db, "exists", return_value=False),
			patch.object(insignias.endpoints, "salvar_item_catalogo") as salvar,
		):
			resultado = insignias.salvar_item_catalogo_insignias(
				nome="Item Novo", tipo="Especialidade", ramo="Todos", valor_unitario=5, simular=True
			)

		salvar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertTrue(resultado["criado"])
		self.assertFalse(resultado["salvo"])

	def test_gravacao_delega_para_o_endpoint(self):
		with (
			patch.object(insignias.frappe.db, "exists", return_value=False),
			patch.object(
				insignias.endpoints,
				"salvar_item_catalogo",
				return_value={"success": True, "name": "Item Novo", "criado": True},
			) as salvar,
		):
			resultado = insignias.salvar_item_catalogo_insignias(
				nome="Item Novo", tipo="Especialidade", ramo="Todos", valor_unitario=5
			)

		salvar.assert_called_once()
		self.assertTrue(resultado["salvo"])
		self.assertEqual(resultado["name"], "Item Novo")


class TestAlternarItemCatalogo(TestCase):
	def test_item_inexistente(self):
		with patch.object(insignias.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				insignias.alternar_item_catalogo_insignias("ITEM-9")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_simulacao_mostra_alteracao_sem_gravar(self):
		atual = SimpleNamespace(ativo=1)
		with (
			patch.object(insignias.frappe.db, "get_value", return_value=atual),
			patch.object(insignias.endpoints, "alternar_item_catalogo") as alternar,
		):
			resultado = insignias.alternar_item_catalogo_insignias("ITEM-1", simular=True)

		alternar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["alteracao"]["ativo"], {"de": True, "para": False})


class TestListarSolicitacoesInsignias(TestCase):
	def test_quem_nao_ve_tudo_so_enxerga_o_proprio(self):
		with (
			patch.object(insignias.permissoes, "pode_ver_todas", return_value=False),
			patch.object(insignias.frappe, "session", SESSAO_ESCOTISTA, create=True),
			patch.object(insignias.consultas, "listar_solicitacoes", return_value=[]) as listar,
			patch.object(insignias.consultas, "resumo_por_status", return_value={}),
		):
			insignias.listar_solicitacoes_insignias(solicitante="outro@exemplo.com")

		filtros = listar.call_args.args[0]
		self.assertEqual(filtros["solicitante"], "escotista@exemplo.com")

	def test_quem_ve_tudo_pode_filtrar_por_solicitante(self):
		with (
			patch.object(insignias.permissoes, "pode_ver_todas", return_value=True),
			patch.object(insignias.consultas, "listar_solicitacoes", return_value=[]) as listar,
			patch.object(insignias.consultas, "resumo_por_status", return_value={}),
		):
			insignias.listar_solicitacoes_insignias(solicitante="ana@exemplo.com")

		filtros = listar.call_args.args[0]
		self.assertEqual(filtros["solicitante"], "ana@exemplo.com")

	def test_pagina_em_memoria(self):
		linhas = [{"name": f"SOL-{i}"} for i in range(5)]
		with (
			patch.object(insignias.permissoes, "pode_ver_todas", return_value=True),
			patch.object(insignias.consultas, "listar_solicitacoes", return_value=linhas),
			patch.object(insignias.consultas, "resumo_por_status", return_value={}),
		):
			resultado = insignias.listar_solicitacoes_insignias(limite=2, inicio=1)

		self.assertEqual([linha["name"] for linha in resultado["solicitacoes"]], ["SOL-1", "SOL-2"])
		self.assertEqual(resultado["paginacao"]["total_com_filtros"], 5)


class TestObterSolicitacaoInsignias(TestCase):
	def test_inexistente_vira_erro_de_ferramenta(self):
		with patch.object(insignias.consultas, "carregar_solicitacao", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				insignias.obter_solicitacao_insignias("SOL-9")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_encontrada_retorna_envelope(self):
		with patch.object(insignias.consultas, "carregar_solicitacao", return_value={"name": "SOL-1"}):
			resultado = insignias.obter_solicitacao_insignias("SOL-1")
		self.assertEqual(resultado["solicitacao"]["name"], "SOL-1")


class TestCriarSolicitacaoInsignias(TestCase):
	def test_recusa_ramo_invalido(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			insignias.criar_solicitacao_insignias(ramo="Marte", itens=[])
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_simulacao_calcula_valor_estimado_sem_gravar(self):
		itens_normalizados = [
			{"insignia": "Distintivo de Progressão I", "quantidade": 2, "valor_unitario": 12.5},
		]
		with (
			patch.object(insignias.endpoints, "_normalizar_itens", return_value=itens_normalizados),
			patch.object(insignias.endpoints, "criar_solicitacao") as criar,
		):
			resultado = insignias.criar_solicitacao_insignias(
				ramo="Lobinho",
				itens=[{"insignia": "Distintivo de Progressão I", "quantidade": 2}],
				simular=True,
			)

		criar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["valor_estimado"], 25.0)

	def test_gravacao_delega_para_o_endpoint(self):
		itens_normalizados = [
			{"insignia": "Distintivo de Progressão I", "quantidade": 2, "valor_unitario": 12.5},
		]
		with (
			patch.object(insignias.endpoints, "_normalizar_itens", return_value=itens_normalizados),
			patch.object(
				insignias.endpoints,
				"criar_solicitacao",
				return_value={"success": True, "name": "SOL-INS-2026-0001"},
			) as criar,
		):
			resultado = insignias.criar_solicitacao_insignias(
				ramo="Lobinho", itens=[{"insignia": "Distintivo de Progressão I", "quantidade": 2}]
			)

		criar.assert_called_once()
		self.assertTrue(resultado["criada"])
		self.assertEqual(resultado["name"], "SOL-INS-2026-0001")


class TestRegistrarCompraInsignias(TestCase):
	def test_solicitacao_inexistente(self):
		with patch.object(insignias.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				insignias.registrar_compra_insignias("SOL-9", "2026-01-01", 10)
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_status_incompativel(self):
		with patch.object(insignias.frappe.db, "get_value", return_value="Comprada"):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				insignias.registrar_compra_insignias("SOL-1", "2026-01-01", 10)
		self.assertEqual(ctx.exception.codigo, "VALIDACAO")

	def test_simulacao_nao_chama_o_endpoint(self):
		with (
			patch.object(insignias.frappe.db, "get_value", return_value="Solicitada"),
			patch.object(insignias.endpoints, "registrar_compra") as registrar,
		):
			resultado = insignias.registrar_compra_insignias("SOL-1", "2026-01-01", 10, simular=True)

		registrar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["alteracao"]["status"], {"de": "Solicitada", "para": "Comprada"})


class TestRegistrarRecebimentoInsignias(TestCase):
	def test_status_incompativel(self):
		with patch.object(insignias.frappe.db, "get_value", return_value="Solicitada"):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				insignias.registrar_recebimento_insignias("SOL-1", "2026-01-01")
		self.assertEqual(ctx.exception.codigo, "VALIDACAO")

	def test_gravacao_delega_para_o_endpoint(self):
		with (
			patch.object(insignias.frappe.db, "get_value", return_value="Comprada"),
			patch.object(
				insignias.endpoints,
				"registrar_recebimento",
				return_value={"success": True, "name": "SOL-1", "status": "Recebida"},
			) as registrar,
		):
			resultado = insignias.registrar_recebimento_insignias("SOL-1", "2026-01-01")

		registrar.assert_called_once()
		self.assertTrue(resultado["registrado"])
		self.assertEqual(resultado["status"], "Recebida")


class TestRegistrarEntregaInsignias(TestCase):
	def test_solicitacao_inexistente(self):
		with patch.object(insignias.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				insignias.registrar_entrega_insignias("SOL-9", "2026-01-01")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_sem_permissao(self):
		doc = SimpleNamespace(status="Recebida")
		with (
			patch.object(insignias.frappe.db, "exists", return_value=True),
			patch.object(insignias.frappe, "get_doc", return_value=doc),
			patch.object(insignias.permissoes, "pode_registrar_entrega", return_value=False),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				insignias.registrar_entrega_insignias("SOL-1", "2026-01-01")
		self.assertEqual(ctx.exception.codigo, "PERMISSAO_NEGADA")

	def test_simulacao_nao_chama_o_endpoint(self):
		doc = SimpleNamespace(status="Recebida")
		with (
			patch.object(insignias.frappe.db, "exists", return_value=True),
			patch.object(insignias.frappe, "get_doc", return_value=doc),
			patch.object(insignias.permissoes, "pode_registrar_entrega", return_value=True),
			patch.object(insignias.endpoints, "registrar_entrega") as registrar,
		):
			resultado = insignias.registrar_entrega_insignias("SOL-1", "2026-01-01", simular=True)

		registrar.assert_not_called()
		self.assertTrue(resultado["simulacao"])


class TestCancelarSolicitacaoInsignias(TestCase):
	def test_solicitacao_inexistente(self):
		with patch.object(insignias.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				insignias.cancelar_solicitacao_insignias("SOL-9", "Motivo")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_sem_permissao(self):
		doc = SimpleNamespace(status="Comprada")
		with (
			patch.object(insignias.frappe.db, "exists", return_value=True),
			patch.object(insignias.frappe, "get_doc", return_value=doc),
			patch.object(insignias.permissoes, "pode_cancelar", return_value=False),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				insignias.cancelar_solicitacao_insignias("SOL-1", "Motivo")
		self.assertEqual(ctx.exception.codigo, "PERMISSAO_NEGADA")

	def test_gravacao_delega_para_o_endpoint(self):
		doc = SimpleNamespace(status="Solicitada")
		with (
			patch.object(insignias.frappe.db, "exists", return_value=True),
			patch.object(insignias.frappe, "get_doc", return_value=doc),
			patch.object(insignias.permissoes, "pode_cancelar", return_value=True),
			patch.object(
				insignias.endpoints,
				"cancelar_solicitacao",
				return_value={"success": True, "name": "SOL-1", "status": "Cancelada"},
			) as cancelar,
		):
			resultado = insignias.cancelar_solicitacao_insignias("SOL-1", "Motivo")

		cancelar.assert_called_once()
		self.assertTrue(resultado["cancelada"])
		self.assertEqual(resultado["status"], "Cancelada")
