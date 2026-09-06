"""Testes das ferramentas MCP de Sugestões e Problemas."""

from unittest import TestCase
from unittest.mock import patch

from gris.api.mcp import sugestoes
from gris.api.mcp.registry import ErroDeFerramenta


class TestListarSugestoes(TestCase):
	def test_filtros_viram_where(self):
		with (
			patch.object(sugestoes.frappe.db, "count", return_value=0),
			patch.object(sugestoes.frappe, "get_all", return_value=[]) as get_all,
		):
			sugestoes.listar_sugestoes(status="Em desenvolvimento", tipo="Problema", modulo="Financeiro")

		filtros = get_all.call_args.kwargs["filters"]
		self.assertEqual(filtros["status"], "Em desenvolvimento")
		self.assertEqual(filtros["tipo"], "Problema")
		self.assertEqual(filtros["modulo"], "Financeiro")

	def test_sem_responsavel_filtra_vazios_e_ignora_responsavel(self):
		with (
			patch.object(sugestoes.frappe.db, "count", return_value=0),
			patch.object(sugestoes.frappe, "get_all", return_value=[]) as get_all,
		):
			sugestoes.listar_sugestoes(sem_responsavel=True, responsavel="dev@example.com")

		self.assertEqual(get_all.call_args.kwargs["filters"]["responsavel"], ["in", [None, ""]])

	def test_busca_usa_like(self):
		with (
			patch.object(sugestoes.frappe.db, "count", return_value=0),
			patch.object(sugestoes.frappe, "get_all", return_value=[]) as get_all,
		):
			sugestoes.listar_sugestoes(busca="contribuição")

		self.assertEqual(get_all.call_args.kwargs["filters"]["titulo"], ["like", "%contribuição%"])


class TestObterSugestao(TestCase):
	def test_nao_encontrado(self):
		with patch.object(sugestoes.frappe.db, "exists", return_value=False):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				sugestoes.obter_sugestao("SUG-99999")
		self.assertEqual(ctx.exception.codigo, "NAO_ENCONTRADO")

	def test_devolve_dados_sem_o_envelope_ok(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(sugestoes.servico, "detalhes", return_value={"ok": True, "item": {"name": "SUG-1"}}),
		):
			resultado = sugestoes.obter_sugestao("SUG-1")

		self.assertNotIn("ok", resultado)
		self.assertEqual(resultado["item"]["name"], "SUG-1")


class TestAtualizarSugestao(TestCase):
	def test_exige_ao_menos_um_campo(self):
		with patch.object(sugestoes.frappe.db, "exists", return_value=True):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				sugestoes.atualizar_sugestao("SUG-1")
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_simulacao_nao_chama_o_servico(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(
				sugestoes.frappe.db,
				"get_value",
				return_value={"status": "Problemas reportados", "tipo": "Problema", "responsavel": None},
			),
			patch.object(sugestoes.servico, "atualizar_status") as atualizar_status,
		):
			resultado = sugestoes.atualizar_sugestao("SUG-1", status="Em desenvolvimento", simular=True)

		atualizar_status.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertEqual(
			resultado["alteracoes"]["status"], {"de": "Problemas reportados", "para": "Em desenvolvimento"}
		)

	def test_delega_cada_campo_ao_endpoint_do_portal(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(
				sugestoes.servico, "atualizar_status", return_value={"ok": True, "status": "Concluído"}
			) as atualizar_status,
			patch.object(
				sugestoes.servico,
				"alocar_responsavel",
				return_value={"ok": True, "responsavel": "dev@example.com", "responsavel_nome": "Dev"},
			) as alocar,
		):
			resultado = sugestoes.atualizar_sugestao("SUG-1", status="Concluído", responsavel="dev@example.com")

		atualizar_status.assert_called_once_with("SUG-1", "Concluído")
		alocar.assert_called_once_with("SUG-1", "dev@example.com")
		self.assertTrue(resultado["atualizado"])
		self.assertEqual(resultado["status"], "Concluído")
		self.assertEqual(resultado["responsavel"], "dev@example.com")


class TestComentarSugestao(TestCase):
	def test_texto_vazio_e_recusado(self):
		with patch.object(sugestoes.frappe.db, "exists", return_value=True):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				sugestoes.comentar_sugestao("SUG-1", "   ")
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_simulacao_nao_grava_comentario(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(sugestoes.servico, "adicionar_comentario") as adicionar,
		):
			resultado = sugestoes.comentar_sugestao("SUG-1", "Já comecei a olhar isso.", simular=True)

		adicionar.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertFalse(resultado["comentado"])

	def test_delega_ao_endpoint_do_portal_que_dispara_o_aviso(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(
				sugestoes.servico,
				"adicionar_comentario",
				return_value={"ok": True, "comentarios": [{"texto": "Já comecei a olhar isso."}]},
			) as adicionar,
		):
			resultado = sugestoes.comentar_sugestao("SUG-1", "Já comecei a olhar isso.")

		adicionar.assert_called_once_with("SUG-1", "Já comecei a olhar isso.")
		self.assertTrue(resultado["comentado"])
		self.assertEqual(resultado["comentarios"], [{"texto": "Já comecei a olhar isso."}])
