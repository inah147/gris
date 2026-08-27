"""Testes do transporte MCP sobre HTTP e do envelope de erros dos endpoints."""

import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from gris.api.mcp import endpoints, http, registry


class TestTraducaoDeProtocolo(TestCase):
	def test_initialize(self):
		resposta = http.processar_mensagem({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
		self.assertEqual(resposta["result"]["protocolVersion"], http.VERSAO_PROTOCOLO)
		self.assertEqual(resposta["result"]["serverInfo"]["name"], "gris")
		self.assertIn("tools", resposta["result"]["capabilities"])

	def test_notificacao_nao_responde(self):
		self.assertIsNone(http.processar_mensagem({"jsonrpc": "2.0", "method": "notifications/initialized"}))

	def test_metodo_desconhecido(self):
		resposta = http.processar_mensagem({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})
		self.assertEqual(resposta["error"]["code"], -32601)

	def test_tools_list_usa_o_registro(self):
		catalogo = [
			{
				"nome": "listar_associados",
				"titulo": "Listar associados",
				"descricao": "Lista.",
				"input_schema": {"type": "object", "properties": {}},
				"roles": ["Gestor de Associados"],
				"somente_leitura": True,
			}
		]
		with patch.object(registry, "listar", return_value=catalogo):
			resposta = http.processar_mensagem({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})

		(ferramenta,) = resposta["result"]["tools"]
		self.assertEqual(ferramenta["name"], "listar_associados")
		self.assertTrue(ferramenta["annotations"]["readOnlyHint"])

	def test_tools_call_devolve_texto_json(self):
		with patch.object(registry, "executar", return_value={"ok": True, "data": {"total": 3}}) as executar:
			resposta = http.processar_mensagem(
				{
					"jsonrpc": "2.0",
					"id": 4,
					"method": "tools/call",
					"params": {"name": "estatisticas_associados", "arguments": {"somente_ativos": True}},
				}
			)

		executar.assert_called_once_with("estatisticas_associados", {"somente_ativos": True})
		self.assertNotIn("isError", resposta["result"])
		self.assertEqual(json.loads(resposta["result"]["content"][0]["text"]), {"total": 3})

	def test_tools_call_sem_nome(self):
		resposta = http.processar_mensagem({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {}})
		self.assertEqual(resposta["error"]["code"], -32602)

	def test_erro_de_ferramenta_vira_is_error(self):
		erro = registry.ErroDeFerramenta("PERMISSAO_NEGADA", "Sem acesso.", {"roles_necessarias": ["X"]})
		with patch.object(registry, "executar", side_effect=erro):
			resposta = http.processar_mensagem(
				{
					"jsonrpc": "2.0",
					"id": 6,
					"method": "tools/call",
					"params": {"name": "categorizar_transacoes", "arguments": {}},
				}
			)

		texto = resposta["result"]["content"][0]["text"]
		self.assertTrue(resposta["result"]["isError"])
		self.assertIn("PERMISSAO_NEGADA", texto)
		self.assertIn("roles_necessarias", texto)


class TestEnvelopeDeErro(TestCase):
	def test_erro_de_ferramenta(self):
		def falhar():
			raise registry.ErroDeFerramenta("NAO_ENCONTRADO", "Sumiu.")

		resposta = endpoints.responder(falhar)
		self.assertEqual(resposta, {"ok": False, "error": {"code": "NAO_ENCONTRADO", "message": "Sumiu."}})

	def test_permission_error_do_frappe(self):
		def falhar():
			raise frappe.PermissionError("Sem permissão para Associado")

		self.assertEqual(endpoints.responder(falhar)["error"]["code"], "PERMISSAO_NEGADA")

	def test_validation_error_preserva_mensagem(self):
		def falhar():
			raise frappe.ValidationError("CPF inválido")

		resposta = endpoints.responder(falhar)
		self.assertEqual(resposta["error"]["code"], "VALIDACAO")
		self.assertIn("CPF inválido", resposta["error"]["message"])

	def test_erro_inesperado_nao_vaza_detalhes(self):
		def falhar():
			raise RuntimeError("connection to 10.0.0.5 refused")

		with patch.object(endpoints.frappe, "log_error") as log_error:
			resposta = endpoints.responder(falhar)

		log_error.assert_called_once()
		self.assertEqual(resposta["error"]["code"], "ERRO_INTERNO")
		self.assertNotIn("10.0.0.5", resposta["error"]["message"])


class TestExecutarFerramenta(TestCase):
	def test_exige_nome_da_ferramenta(self):
		resposta = endpoints.executar_ferramenta()
		self.assertEqual(resposta["error"]["code"], "ARGUMENTO_INVALIDO")

	def test_aceita_argumentos_em_json_string(self):
		with patch.object(registry, "executar", return_value={"ok": True, "data": {}}) as executar:
			endpoints.executar_ferramenta("listar_associados", '{"ramo": "Lobinho"}')
		executar.assert_called_once_with("listar_associados", {"ramo": "Lobinho"})

	def test_recusa_argumentos_que_nao_sao_objeto(self):
		resposta = endpoints.executar_ferramenta("listar_associados", "[1, 2]")
		self.assertEqual(resposta["error"]["code"], "ARGUMENTO_INVALIDO")

	def test_lista_ferramentas_inclui_versao_e_usuario(self):
		with (
			patch.object(registry, "listar", return_value=[]),
			patch.object(endpoints.frappe, "session", SimpleNamespace(user="ana@example.com"), create=True),
		):
			resposta = endpoints.listar_ferramentas()

		self.assertTrue(resposta["ok"])
		self.assertEqual(resposta["data"]["versao"], endpoints.VERSAO_API)
		self.assertEqual(resposta["data"]["usuario"], "ana@example.com")
