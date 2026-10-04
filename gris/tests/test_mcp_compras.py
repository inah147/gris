"""Testes das ferramentas MCP do módulo de Compras."""

from types import SimpleNamespace
from typing import ClassVar
from unittest import TestCase
from unittest.mock import patch

import frappe

from gris.api.mcp import compras
from gris.api.mcp.registry import ErroDeFerramenta

SESSAO_ESCOTISTA = SimpleNamespace(user="escotista@exemplo.com")
PE = "Programa Educativo"
MANUTENCAO = "Manutenção"


def _registro(status, area=PE):
	return frappe._dict(status=status, area=area)


def _pode_comprar(valor=True):
	return patch.object(compras.permissoes, "pode_comprar", return_value=valor)


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


class TestListarCatalogoCompras(TestCase):
	def test_apenas_ativos_por_padrao(self):
		with patch.object(compras.consultas, "listar_catalogo_completo", return_value=CATALOGO):
			resultado = compras.listar_catalogo_compras()

		self.assertEqual(resultado["total"], 1)
		self.assertEqual(resultado["catalogo"][0]["name"], "Distintivo de Progressão I")

	def test_filtra_por_tipo_e_ramo(self):
		with patch.object(compras.consultas, "listar_catalogo_completo", return_value=CATALOGO):
			resultado = compras.listar_catalogo_compras(apenas_ativos=False, tipo="Especialidade")

		self.assertEqual(resultado["total"], 1)
		self.assertEqual(resultado["catalogo"][0]["name"], "Insígnia Inativa")


class TestSalvarItemCatalogo(TestCase):
	def test_recusa_tipo_invalido(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			compras.salvar_item_catalogo_compras(area=PE, tipo="Fantasia", ramo="Todos", valor_unitario=1)
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_recusa_grafia_antiga_insignia_especial(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			compras.salvar_item_catalogo_compras(
				area=PE, tipo="Insígnia Especial", ramo="Todos", valor_unitario=1
			)
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_aceita_insignia_de_interesse_especial(self):
		with (
			patch.object(compras.frappe.db, "exists", return_value=False),
			patch.object(
				compras.endpoints,
				"salvar_item_catalogo",
				return_value={"success": True, "name": "Item Novo", "criado": True},
			) as salvar,
		):
			resultado = compras.salvar_item_catalogo_compras(
				area=PE,
				nome="Item Novo",
				tipo="Insígnia de Interesse Especial",
				ramo="Todos",
				valor_unitario=5,
			)

		salvar.assert_called_once()
		self.assertTrue(resultado["salvo"])

	def test_recusa_ramo_invalido(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			compras.salvar_item_catalogo_compras(
				area=PE, tipo="Especialidade", ramo="Marte", valor_unitario=1
			)
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_recusa_valor_negativo(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			compras.salvar_item_catalogo_compras(
				area=PE, tipo="Especialidade", ramo="Todos", valor_unitario=-1
			)
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_criacao_exige_nome_com_tres_caracteres(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			compras.salvar_item_catalogo_compras(
				area=PE, nome="Ab", tipo="Especialidade", ramo="Todos", valor_unitario=1
			)
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_edicao_de_item_inexistente(self):
		with patch.object(compras.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.salvar_item_catalogo_compras(
					area=PE, name="ITEM-9", tipo="Especialidade", ramo="Todos", valor_unitario=1
				)
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_quem_nao_e_gestor_de_metodos_nao_cadastra_distintivo(self):
		with patch.object(compras.permissoes, "pode_cadastrar_item", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.salvar_item_catalogo_compras(
					area=PE, nome="Distintivo Novo", tipo="Especialidade", ramo="Todos", valor_unitario=1
				)
		self.assertEqual(ctx.exception.codigo, "PERMISSAO_NEGADA")

	def test_item_de_manutencao_ignora_tipo_e_ramo(self):
		with (
			patch.object(compras.permissoes, "pode_cadastrar_item", return_value=True),
			patch.object(compras.frappe.db, "exists", return_value=False),
			patch.object(compras.endpoints, "salvar_item_catalogo") as salvar,
		):
			resultado = compras.salvar_item_catalogo_compras(
				area=MANUTENCAO,
				nome="Lâmpada LED",
				tipo="Fantasia",
				ramo="Marte",
				valor_unitario=15,
				simular=True,
			)

		salvar.assert_not_called()
		self.assertIsNone(resultado["previa"]["tipo"])
		self.assertIsNone(resultado["previa"]["ramo"])

	def test_recusa_area_invalida(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			compras.salvar_item_catalogo_compras(area="Cozinha", nome="Panela", valor_unitario=1)
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_simulacao_nao_grava(self):
		with (
			patch.object(compras.frappe.db, "exists", return_value=False),
			patch.object(compras.endpoints, "salvar_item_catalogo") as salvar,
		):
			resultado = compras.salvar_item_catalogo_compras(
				area=PE, nome="Item Novo", tipo="Especialidade", ramo="Todos", valor_unitario=5, simular=True
			)

		salvar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertTrue(resultado["criado"])
		self.assertFalse(resultado["salvo"])

	def test_gravacao_delega_para_o_endpoint(self):
		with (
			patch.object(compras.frappe.db, "exists", return_value=False),
			patch.object(
				compras.endpoints,
				"salvar_item_catalogo",
				return_value={"success": True, "name": "Item Novo", "criado": True},
			) as salvar,
		):
			resultado = compras.salvar_item_catalogo_compras(
				area=PE, nome="Item Novo", tipo="Especialidade", ramo="Todos", valor_unitario=5
			)

		salvar.assert_called_once()
		self.assertTrue(resultado["salvo"])
		self.assertEqual(resultado["name"], "Item Novo")


class TestAlternarItemCatalogo(TestCase):
	def test_item_inexistente(self):
		with patch.object(compras.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.alternar_item_catalogo_compras("ITEM-9")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_simulacao_mostra_alteracao_sem_gravar(self):
		atual = SimpleNamespace(ativo=1, area=PE, owner="gestor@exemplo.com")
		with (
			patch.object(compras.frappe.db, "get_value", return_value=atual),
			patch.object(compras.permissoes, "pode_editar_item", return_value=True),
			patch.object(compras.endpoints, "alternar_item_catalogo") as alternar,
		):
			resultado = compras.alternar_item_catalogo_compras("ITEM-1", simular=True)

		alternar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["alteracao"]["ativo"], {"de": True, "para": False})


class TestListarSolicitacoesCompra(TestCase):
	LINHAS: ClassVar[list[dict]] = [
		{"name": "SOL-1", "status": "Solicitada"},
		{"name": "SOL-2", "status": "Comprada"},
		{"name": "SOL-3", "status": "Entregue"},
	]

	def _listar(self, areas_fila, **kwargs):
		with (
			patch.object(compras.permissoes, "areas_para", return_value=list(areas_fila)),
			patch.object(compras.frappe, "session", SESSAO_ESCOTISTA, create=True),
			patch.object(compras.consultas, "listar_solicitacoes", return_value=list(self.LINHAS)) as listar,
		):
			resultado = compras.listar_solicitacoes_compra(**kwargs)
		return resultado, listar.call_args

	def test_quem_nao_ve_fila_so_enxerga_o_proprio(self):
		_, chamada = self._listar([], solicitante="outro@exemplo.com")
		self.assertEqual(chamada.args[0]["solicitante"], "escotista@exemplo.com")
		self.assertIsNone(chamada.kwargs["or_filtros"])

	def test_gestor_ve_a_fila_da_area_e_os_proprios(self):
		_, chamada = self._listar([MANUTENCAO])
		self.assertEqual(
			chamada.kwargs["or_filtros"],
			{"area": ["in", [MANUTENCAO]], "solicitante": "escotista@exemplo.com"},
		)

	def test_gestor_filtra_por_solicitante_dentro_das_suas_areas(self):
		_, chamada = self._listar([MANUTENCAO], solicitante="ana@exemplo.com")
		self.assertEqual(chamada.args[0]["solicitante"], "ana@exemplo.com")
		self.assertEqual(chamada.args[0]["area"], ["in", [MANUTENCAO]])

	def test_por_padrao_lista_so_aguardando_compra(self):
		resultado, _ = self._listar([PE])
		self.assertEqual([linha["name"] for linha in resultado["solicitacoes"]], ["SOL-1"])
		self.assertEqual(resultado["status_listados"], ["Solicitada"])
		# O resumo continua contando todos os status.
		self.assertEqual(resultado["resumo_por_status"]["Entregue"], 1)

	def test_status_explicito_traz_os_comprados(self):
		resultado, _ = self._listar([PE], status="Comprada")
		self.assertEqual([linha["name"] for linha in resultado["solicitacoes"]], ["SOL-2"])

	def test_incluir_todas_traz_tudo(self):
		resultado, _ = self._listar([PE], incluir_todas=True)
		self.assertEqual(len(resultado["solicitacoes"]), 3)

	def test_area_invalida(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			compras.listar_solicitacoes_compra(area="Cozinha")
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_pagina_em_memoria(self):
		linhas = [{"name": f"SOL-{i}", "status": "Solicitada"} for i in range(5)]
		with (
			patch.object(compras.permissoes, "areas_para", return_value=[PE]),
			patch.object(compras.frappe, "session", SESSAO_ESCOTISTA, create=True),
			patch.object(compras.consultas, "listar_solicitacoes", return_value=linhas),
		):
			resultado = compras.listar_solicitacoes_compra(limite=2, inicio=1)

		self.assertEqual([linha["name"] for linha in resultado["solicitacoes"]], ["SOL-1", "SOL-2"])
		self.assertEqual(resultado["paginacao"]["total_com_filtros"], 5)


class TestObterSolicitacaoCompra(TestCase):
	def test_inexistente_vira_erro_de_ferramenta(self):
		with patch.object(compras.consultas, "carregar_solicitacao", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.obter_solicitacao_compra("SOL-9")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_encontrada_retorna_envelope(self):
		with patch.object(compras.consultas, "carregar_solicitacao", return_value={"name": "SOL-1"}):
			resultado = compras.obter_solicitacao_compra("SOL-1")
		self.assertEqual(resultado["solicitacao"]["name"], "SOL-1")


class TestCriarSolicitacaoCompra(TestCase):
	def test_recusa_ramo_invalido(self):
		with self.assertRaises(ErroDeFerramenta) as ctx:
			compras.criar_solicitacao_compra(area=PE, ramo="Marte", itens=[])
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_simulacao_calcula_valor_estimado_sem_gravar(self):
		itens_normalizados = [
			{"item_catalogo": "Distintivo de Progressão I", "quantidade": 2, "valor_unitario": 12.5},
		]
		with (
			patch.object(compras.endpoints, "_normalizar_itens", return_value=itens_normalizados),
			patch.object(compras.endpoints, "criar_solicitacao") as criar,
		):
			resultado = compras.criar_solicitacao_compra(
				area=PE,
				ramo="Lobinho",
				itens=[{"item_catalogo": "Distintivo de Progressão I", "quantidade": 2}],
				simular=True,
			)

		criar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["valor_estimado"], 25.0)

	def test_gravacao_delega_para_o_endpoint(self):
		itens_normalizados = [
			{"item_catalogo": "Distintivo de Progressão I", "quantidade": 2, "valor_unitario": 12.5},
		]
		with (
			patch.object(compras.endpoints, "_normalizar_itens", return_value=itens_normalizados),
			patch.object(
				compras.endpoints,
				"criar_solicitacao",
				return_value={"success": True, "name": "SOL-INS-2026-0001"},
			) as criar,
		):
			resultado = compras.criar_solicitacao_compra(
				area=PE,
				ramo="Lobinho",
				itens=[{"item_catalogo": "Distintivo de Progressão I", "quantidade": 2}],
			)

		criar.assert_called_once()
		self.assertTrue(resultado["criada"])
		self.assertEqual(resultado["name"], "SOL-INS-2026-0001")


class TestRegistrarCompra(TestCase):
	def test_solicitacao_inexistente(self):
		with patch.object(compras.frappe.db, "get_value", return_value=None):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.registrar_compra("SOL-9", "2026-01-01", 10)
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_status_incompativel(self):
		with (
			patch.object(compras.frappe.db, "get_value", return_value=_registro("Comprada")),
			_pode_comprar(),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.registrar_compra("SOL-1", "2026-01-01", 10)
		self.assertEqual(ctx.exception.codigo, "VALIDACAO")

	def test_gestor_de_outra_area_nao_registra_compra(self):
		with (
			patch.object(compras.frappe.db, "get_value", return_value=_registro("Solicitada", MANUTENCAO)),
			_pode_comprar(False),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.registrar_compra("SOL-1", "2026-01-01", 10)
		self.assertEqual(ctx.exception.codigo, "PERMISSAO_NEGADA")

	def test_simulacao_nao_chama_o_endpoint(self):
		with (
			patch.object(compras.frappe.db, "get_value", return_value=_registro("Solicitada")),
			_pode_comprar(),
			patch.object(compras.endpoints, "registrar_compra") as registrar,
		):
			resultado = compras.registrar_compra("SOL-1", "2026-01-01", 10, simular=True)

		registrar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(resultado["alteracao"]["status"], {"de": "Solicitada", "para": "Comprada"})


class TestRegistrarRecebimentoCompra(TestCase):
	def test_status_incompativel(self):
		with (
			patch.object(compras.frappe.db, "get_value", return_value=_registro("Solicitada")),
			_pode_comprar(),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.registrar_recebimento_compra("SOL-1", "2026-01-01")
		self.assertEqual(ctx.exception.codigo, "VALIDACAO")

	def test_gravacao_delega_para_o_endpoint(self):
		with (
			patch.object(compras.frappe.db, "get_value", return_value=_registro("Comprada")),
			_pode_comprar(),
			patch.object(
				compras.endpoints,
				"registrar_recebimento",
				return_value={"success": True, "name": "SOL-1", "status": "Recebida"},
			) as registrar,
		):
			resultado = compras.registrar_recebimento_compra("SOL-1", "2026-01-01")

		registrar.assert_called_once()
		self.assertTrue(resultado["registrado"])
		self.assertEqual(resultado["status"], "Recebida")


class TestRegistrarEntregaCompra(TestCase):
	def test_solicitacao_inexistente(self):
		with patch.object(compras.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.registrar_entrega_compra("SOL-9", "2026-01-01")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_sem_permissao(self):
		doc = SimpleNamespace(status="Recebida")
		with (
			patch.object(compras.frappe.db, "exists", return_value=True),
			patch.object(compras.frappe, "get_doc", return_value=doc),
			patch.object(compras.permissoes, "pode_registrar_entrega", return_value=False),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.registrar_entrega_compra("SOL-1", "2026-01-01")
		self.assertEqual(ctx.exception.codigo, "PERMISSAO_NEGADA")

	def test_simulacao_nao_chama_o_endpoint(self):
		doc = SimpleNamespace(status="Recebida")
		with (
			patch.object(compras.frappe.db, "exists", return_value=True),
			patch.object(compras.frappe, "get_doc", return_value=doc),
			patch.object(compras.permissoes, "pode_registrar_entrega", return_value=True),
			patch.object(compras.endpoints, "registrar_entrega") as registrar,
		):
			resultado = compras.registrar_entrega_compra("SOL-1", "2026-01-01", simular=True)

		registrar.assert_not_called()
		self.assertTrue(resultado["simulacao"])


class TestCancelarSolicitacaoCompra(TestCase):
	def test_solicitacao_inexistente(self):
		with patch.object(compras.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.cancelar_solicitacao_compra("SOL-9", "Motivo")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_sem_permissao(self):
		doc = SimpleNamespace(status="Comprada")
		with (
			patch.object(compras.frappe.db, "exists", return_value=True),
			patch.object(compras.frappe, "get_doc", return_value=doc),
			patch.object(compras.permissoes, "pode_cancelar", return_value=False),
		):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				compras.cancelar_solicitacao_compra("SOL-1", "Motivo")
		self.assertEqual(ctx.exception.codigo, "PERMISSAO_NEGADA")

	def test_gravacao_delega_para_o_endpoint(self):
		doc = SimpleNamespace(status="Solicitada")
		with (
			patch.object(compras.frappe.db, "exists", return_value=True),
			patch.object(compras.frappe, "get_doc", return_value=doc),
			patch.object(compras.permissoes, "pode_cancelar", return_value=True),
			patch.object(
				compras.endpoints,
				"cancelar_solicitacao",
				return_value={"success": True, "name": "SOL-1", "status": "Cancelada"},
			) as cancelar,
		):
			resultado = compras.cancelar_solicitacao_compra("SOL-1", "Motivo")

		cancelar.assert_called_once()
		self.assertTrue(resultado["cancelada"])
		self.assertEqual(resultado["status"], "Cancelada")
