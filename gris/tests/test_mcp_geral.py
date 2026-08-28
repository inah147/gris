"""Testes das ferramentas MCP transversais (listar_usuarios e listar_papeis)."""

from unittest import TestCase
from unittest.mock import patch

from gris.api.mcp import geral
from gris.api.mcp.registry import ErroDeFerramenta


class TestListarUsuarios(TestCase):
	def test_sem_filtros_pagina_corretamente_e_limita_a_100(self):
		with (
			patch.object(geral.frappe, "get_all", return_value=[]) as get_all,
			patch.object(geral.frappe.db, "count", return_value=0),
		):
			resultado = geral.listar_usuarios(limite=500)

		_, kwargs = get_all.call_args
		self.assertEqual(kwargs["filters"], {"user_type": "System User", "enabled": 1})
		self.assertIsNone(kwargs["or_filters"])
		self.assertEqual(kwargs["limit_page_length"], 100)
		self.assertEqual(resultado["paginacao"]["limite"], 100)

	def test_papel_inexistente_levanta_erro_argumento_invalido(self):
		with patch.object(geral.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				geral.listar_usuarios(papel="Papel Fantasma")

		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_papel_existente_sem_usuarios_devolve_lista_vazia_sem_erro(self):
		with (
			patch.object(geral.frappe.db, "exists", return_value=True),
			patch.object(geral.frappe, "get_all", return_value=[]) as get_all,
		):
			resultado = geral.listar_usuarios(papel="Gestor de Metodos")

		self.assertEqual(resultado["usuarios"], [])
		self.assertEqual(resultado["paginacao"]["total_com_filtros"], 0)
		# A única query feita deve ser a de "Has Role" (procurando quem tem o papel);
		# a query principal de User não deve ser disparada.
		get_all.assert_called_once()
		self.assertEqual(get_all.call_args.args[0], "Has Role")

	def test_papel_existente_com_usuarios_filtra_por_name_in(self):
		def get_all(doctype, **kwargs):
			if doctype == "Has Role" and kwargs.get("filters", {}).get("role") == "Gestor de Metodos":
				return ["ana@example.com", "bruno@example.com"]
			if doctype == "User":
				return [
					{
						"name": "ana@example.com",
						"full_name": "Ana",
						"enabled": 1,
						"last_login": None,
					}
				]
			if doctype == "Has Role":
				return []
			return []

		with (
			patch.object(geral.frappe.db, "exists", return_value=True),
			patch.object(geral.frappe, "get_all", side_effect=get_all) as mocked,
			patch.object(geral.frappe.db, "count", return_value=1),
		):
			resultado = geral.listar_usuarios(papel="Gestor de Metodos")

		chamadas_user = [c for c in mocked.call_args_list if c.args[0] == "User"]
		self.assertEqual(len(chamadas_user), 1)
		self.assertEqual(
			chamadas_user[0].kwargs["filters"]["name"],
			["in", ["ana@example.com", "bruno@example.com"]],
		)
		self.assertEqual(len(resultado["usuarios"]), 1)

	def test_busca_gera_or_filters(self):
		with (
			patch.object(geral.frappe, "get_all", return_value=[]) as get_all,
			patch.object(geral.frappe.db, "count", return_value=0),
		):
			geral.listar_usuarios(busca="ana")

		or_filters = get_all.call_args.kwargs["or_filters"]
		self.assertEqual(or_filters["full_name"], ["like", "%ana%"])
		self.assertEqual(or_filters["name"], ["like", "%ana%"])

	def test_monta_mapa_usuario_para_papeis_a_partir_de_multiplas_linhas(self):
		usuarios = [
			{"name": "ana@example.com", "full_name": "Ana", "enabled": 1, "last_login": "2026-01-01"},
			{"name": "bruno@example.com", "full_name": "Bruno", "enabled": 1, "last_login": None},
		]
		linhas_has_role = [
			{"parent": "ana@example.com", "role": "Gestor Financeiro"},
			{"parent": "ana@example.com", "role": "Gestor de Associados"},
			{"parent": "bruno@example.com", "role": "Recepcao"},
		]

		def get_all(doctype, **kwargs):
			if doctype == "User":
				return usuarios
			if doctype == "Has Role":
				return linhas_has_role
			return []

		with (
			patch.object(geral.frappe, "get_all", side_effect=get_all),
			patch.object(geral.frappe.db, "count", return_value=2),
		):
			resultado = geral.listar_usuarios()

		por_usuario = {u["usuario"]: u["papeis"] for u in resultado["usuarios"]}
		self.assertEqual(por_usuario["ana@example.com"], ["Gestor Financeiro", "Gestor de Associados"])
		self.assertEqual(por_usuario["bruno@example.com"], ["Recepcao"])


class TestListarPapeis(TestCase):
	def test_aplica_filtro_busca_como_like(self):
		with patch.object(geral.frappe, "get_all", return_value=[]) as get_all:
			geral.listar_papeis(busca="Gestor")

		filtros = get_all.call_args.kwargs["filters"]
		self.assertEqual(filtros["name"], ["like", "%Gestor%"])
		self.assertEqual(filtros["disabled"], 0)

	def test_sem_busca_nao_filtra_por_nome(self):
		with patch.object(geral.frappe, "get_all", return_value=[]) as get_all:
			geral.listar_papeis()

		filtros = get_all.call_args.kwargs["filters"]
		self.assertNotIn("name", filtros)
