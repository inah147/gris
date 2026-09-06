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
			resultado = sugestoes.atualizar_sugestao(
				"SUG-1", status="Concluído", responsavel="dev@example.com"
			)

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


class TestAssumirSugestao(TestCase):
	def test_simulacao_nao_chama_o_servico(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(
				sugestoes.frappe.db,
				"get_value",
				return_value={
					"status": "Selecionado para desenvolvimento",
					"responsavel": None,
					"branch": None,
				},
			),
			patch.object(sugestoes.servico, "assumir") as assumir,
		):
			resultado = sugestoes.assumir_sugestao("SUG-1", branch="claude/x", simular=True)

		assumir.assert_not_called()
		self.assertTrue(resultado["simulacao"])
		self.assertFalse(resultado["assumido"])

	def test_repassa_branch_responsavel_e_forcar(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(
				sugestoes.servico,
				"assumir",
				return_value={"ok": True, "name": "SUG-1", "status": "Em desenvolvimento"},
			) as assumir,
			patch.object(sugestoes.servico, "adicionar_comentario") as comentar,
		):
			resultado = sugestoes.assumir_sugestao(
				"SUG-1", branch="claude/x", responsavel="dev@example.com", forcar=True
			)

		assumir.assert_called_once_with(
			"SUG-1", branch="claude/x", responsavel="dev@example.com", forcar=True
		)
		comentar.assert_not_called()
		self.assertTrue(resultado["assumido"])
		self.assertNotIn("ok", resultado)

	def test_comentario_opcional_vai_junto(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(sugestoes.servico, "assumir", return_value={"ok": True, "name": "SUG-1"}),
			patch.object(sugestoes.servico, "adicionar_comentario") as comentar,
		):
			sugestoes.assumir_sugestao("SUG-1", comentario="Peguei para desenvolver hoje.")

		comentar.assert_called_once_with("SUG-1", "Peguei para desenvolver hoje.")


class TestRegistrarPullRequest(TestCase):
	def test_simulacao_mostra_a_troca_sem_gravar(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(sugestoes.frappe.db, "get_value", return_value=""),
			patch.object(sugestoes.servico, "registrar_pull_request") as registrar,
		):
			resultado = sugestoes.registrar_pull_request(
				"SUG-1", "https://github.com/inah147/gris/pull/42", simular=True
			)

		registrar.assert_not_called()
		self.assertEqual(resultado["para"], "https://github.com/inah147/gris/pull/42")

	def test_delega_ao_portal_e_comenta_quando_pedido(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(
				sugestoes.servico,
				"registrar_pull_request",
				return_value={"ok": True, "name": "SUG-1", "pull_request": "https://x/pull/1"},
			) as registrar,
			patch.object(sugestoes.servico, "adicionar_comentario") as comentar,
		):
			resultado = sugestoes.registrar_pull_request(
				"SUG-1", " https://x/pull/1 ", comentario="PR aberto."
			)

		registrar.assert_called_once_with("SUG-1", "https://x/pull/1")
		comentar.assert_called_once_with("SUG-1", "PR aberto.")
		self.assertTrue(resultado["registrado"])


class TestPedirEsclarecimento(TestCase):
	def test_pergunta_vazia_e_recusada(self):
		with patch.object(sugestoes.frappe.db, "exists", return_value=True):
			with self.assertRaises(ErroDeFerramenta) as ctx:
				sugestoes.pedir_esclarecimento("SUG-1", "   ")
		self.assertEqual(ctx.exception.codigo, "ARGUMENTO_INVALIDO")

	def test_delega_ao_portal(self):
		with (
			patch.object(sugestoes.frappe.db, "exists", return_value=True),
			patch.object(
				sugestoes.servico,
				"pedir_esclarecimento",
				return_value={"ok": True, "comentarios": [{"texto": "Em qual navegador?"}]},
			) as pedir,
		):
			resultado = sugestoes.pedir_esclarecimento("SUG-1", "Em qual navegador?")

		pedir.assert_called_once_with("SUG-1", "Em qual navegador?")
		self.assertTrue(resultado["perguntado"])
		self.assertTrue(resultado["aguardando_esclarecimento"])


class TestFiltroDePendencia(TestCase):
	def test_aguardando_esclarecimento_vira_zero_ou_um(self):
		for valor, esperado in ((True, 1), (False, 0)):
			with (
				patch.object(sugestoes.frappe.db, "count", return_value=0),
				patch.object(sugestoes.frappe, "get_all", return_value=[]) as get_all,
			):
				sugestoes.listar_sugestoes(aguardando_esclarecimento=valor)

			self.assertEqual(get_all.call_args.kwargs["filters"]["aguardando_esclarecimento"], esperado)

	def test_sem_o_filtro_nao_entra_no_where(self):
		with (
			patch.object(sugestoes.frappe.db, "count", return_value=0),
			patch.object(sugestoes.frappe, "get_all", return_value=[]) as get_all,
		):
			sugestoes.listar_sugestoes()

		self.assertNotIn("aguardando_esclarecimento", get_all.call_args.kwargs["filters"])
