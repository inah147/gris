"""Testes do bridge MCP stdio (rodam sem Frappe: `python3 -m unittest discover`).

Um servidor HTTP local finge ser o site do GRIS, então o teste cobre o caminho
completo: mensagem MCP -> chamada HTTP autenticada -> resposta MCP.
"""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gris_mcp

FERRAMENTAS_FALSAS = [
	{
		"nome": "listar_associados",
		"titulo": "Listar associados",
		"descricao": "Lista associados.",
		"input_schema": {"type": "object", "properties": {"ramo": {"type": "string"}}},
		"roles": ["Gestor de Associados"],
		"somente_leitura": True,
		"autorizada": True,
	},
	{
		"nome": "categorizar_transacoes",
		"titulo": "Categorizar transações",
		"descricao": "Categoriza em lote.",
		"input_schema": {"type": "object", "properties": {"ids": {"type": "array"}}},
		"roles": ["Gestor Financeiro"],
		"somente_leitura": False,
		"autorizada": True,
	},
]


class FrappeFalso(BaseHTTPRequestHandler):
	status_forcado: ClassVar[int | None] = None
	chamadas: ClassVar[list] = []

	def do_POST(self):  # nome exigido pela stdlib
		tamanho = int(self.headers.get("Content-Length", 0))
		corpo = json.loads(self.rfile.read(tamanho).decode("utf-8") or "{}")
		FrappeFalso.chamadas.append(
			{
				"caminho": self.path,
				"corpo": corpo,
				"autorizacao": self.headers.get("Authorization"),
			}
		)

		if FrappeFalso.status_forcado:
			self.send_response(FrappeFalso.status_forcado)
			self.end_headers()
			self.wfile.write(b'{"exc_type": "AuthenticationError"}')
			return

		if self.path.endswith("listar_ferramentas"):
			payload = {"message": {"ok": True, "data": {"ferramentas": FERRAMENTAS_FALSAS}}}
		elif corpo.get("ferramenta") == "listar_associados":
			payload = {
				"message": {"ok": True, "data": {"associados": [{"name": "123", "nome_completo": "Ana"}]}}
			}
		elif corpo.get("ferramenta") == "ferramenta_invalida":
			payload = {
				"message": {
					"ok": False,
					"error": {
						"code": "FERRAMENTA_DESCONHECIDA",
						"message": "Não existe.",
						"details": {"a": 1},
					},
				}
			}
		else:
			payload = {"message": {"ok": True, "data": {"atualizadas": 2}}}

		corpo_bytes = json.dumps(payload).encode("utf-8")
		self.send_response(200)
		self.send_header("Content-Type", "application/json")
		self.send_header("Content-Length", str(len(corpo_bytes)))
		self.end_headers()
		self.wfile.write(corpo_bytes)

	def log_message(self, *args):  # silencia o log do servidor de teste
		pass


class BaseComServidor(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.servidor = HTTPServer(("127.0.0.1", 0), FrappeFalso)
		cls.thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
		cls.thread.start()
		cls.url = f"http://127.0.0.1:{cls.servidor.server_port}"

	@classmethod
	def tearDownClass(cls):
		cls.servidor.shutdown()
		cls.servidor.server_close()

	def setUp(self):
		FrappeFalso.chamadas = []
		FrappeFalso.status_forcado = None
		os.environ.pop("GRIS_MCP_SOMENTE_LEITURA", None)
		self.cliente = gris_mcp.ClienteGris(url=self.url, api_key="chave", api_secret="segredo")
		self.servidor_mcp = gris_mcp.ServidorMCP(self.cliente)

	def enviar(self, mensagens: list[dict]) -> list[dict]:
		entrada = io.StringIO("\n".join(json.dumps(m) for m in mensagens) + "\n")
		saida = io.StringIO()
		self.servidor_mcp.executar_loop(entrada, saida)
		return [json.loads(linha) for linha in saida.getvalue().splitlines() if linha.strip()]


class TestProtocolo(BaseComServidor):
	def test_initialize_responde_capacidades(self):
		(resposta,) = self.enviar([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])
		self.assertEqual(resposta["id"], 1)
		self.assertIn("tools", resposta["result"]["capabilities"])
		self.assertEqual(resposta["result"]["serverInfo"]["name"], "gris")

	def test_notificacao_nao_gera_resposta(self):
		respostas = self.enviar([{"jsonrpc": "2.0", "method": "notifications/initialized"}])
		self.assertEqual(respostas, [])

	def test_metodo_desconhecido_retorna_32601(self):
		(resposta,) = self.enviar([{"jsonrpc": "2.0", "id": 9, "method": "recursos/listar"}])
		self.assertEqual(resposta["error"]["code"], -32601)

	def test_json_invalido_retorna_32700(self):
		entrada = io.StringIO("{isso não é json}\n")
		saida = io.StringIO()
		self.servidor_mcp.executar_loop(entrada, saida)
		self.assertEqual(json.loads(saida.getvalue())["error"]["code"], -32700)

	def test_ping(self):
		(resposta,) = self.enviar([{"jsonrpc": "2.0", "id": 2, "method": "ping"}])
		self.assertEqual(resposta["result"], {})


class TestFerramentas(BaseComServidor):
	def test_tools_list_traduz_catalogo_remoto(self):
		(resposta,) = self.enviar([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
		nomes = [t["name"] for t in resposta["result"]["tools"]]
		self.assertIn("diagnostico_conexao", nomes)
		self.assertIn("listar_associados", nomes)
		self.assertIn("categorizar_transacoes", nomes)

		listar = next(t for t in resposta["result"]["tools"] if t["name"] == "listar_associados")
		self.assertTrue(listar["annotations"]["readOnlyHint"])
		self.assertEqual(listar["inputSchema"]["properties"]["ramo"]["type"], "string")

		categorizar = next(t for t in resposta["result"]["tools"] if t["name"] == "categorizar_transacoes")
		self.assertFalse(categorizar["annotations"]["readOnlyHint"])

	def test_tools_call_envia_token_e_devolve_dados(self):
		(resposta,) = self.enviar(
			[
				{
					"jsonrpc": "2.0",
					"id": 3,
					"method": "tools/call",
					"params": {"name": "listar_associados", "arguments": {"ramo": "Lobinho"}},
				}
			]
		)
		self.assertNotIn("isError", resposta["result"])
		self.assertIn("Ana", resposta["result"]["content"][0]["text"])

		chamada = FrappeFalso.chamadas[-1]
		self.assertEqual(chamada["autorizacao"], "token chave:segredo")
		self.assertEqual(
			chamada["corpo"], {"ferramenta": "listar_associados", "argumentos": {"ramo": "Lobinho"}}
		)

	def test_erro_de_negocio_vira_is_error(self):
		(resposta,) = self.enviar(
			[
				{
					"jsonrpc": "2.0",
					"id": 4,
					"method": "tools/call",
					"params": {"name": "ferramenta_invalida", "arguments": {}},
				}
			]
		)
		self.assertTrue(resposta["result"]["isError"])
		self.assertIn("FERRAMENTA_DESCONHECIDA", resposta["result"]["content"][0]["text"])

	def test_tools_call_sem_nome(self):
		(resposta,) = self.enviar([{"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {}}])
		self.assertEqual(resposta["error"]["code"], -32602)

	def test_credenciais_recusadas_geram_mensagem_orientada(self):
		FrappeFalso.status_forcado = 403
		(resposta,) = self.enviar(
			[
				{
					"jsonrpc": "2.0",
					"id": 6,
					"method": "tools/call",
					"params": {"name": "listar_associados", "arguments": {}},
				}
			]
		)
		texto = resposta["result"]["content"][0]["text"]
		self.assertTrue(resposta["result"]["isError"])
		self.assertIn("GRIS_API_KEY", texto)

	def test_site_fora_do_ar_nao_derruba_tools_list(self):
		cliente = gris_mcp.ClienteGris(url="http://127.0.0.1:9", api_key="a", api_secret="b", timeout=1)
		servidor = gris_mcp.ServidorMCP(cliente)
		ferramentas = servidor.listar_ferramentas()
		self.assertEqual([f["name"] for f in ferramentas], ["diagnostico_conexao"])


class TestSomenteLeitura(BaseComServidor):
	def setUp(self):
		super().setUp()
		os.environ["GRIS_MCP_SOMENTE_LEITURA"] = "1"

	def tearDown(self):
		os.environ.pop("GRIS_MCP_SOMENTE_LEITURA", None)

	def test_ferramentas_de_escrita_ficam_ocultas(self):
		(resposta,) = self.enviar([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
		nomes = [t["name"] for t in resposta["result"]["tools"]]
		self.assertIn("listar_associados", nomes)
		self.assertNotIn("categorizar_transacoes", nomes)

	def test_chamada_de_escrita_e_bloqueada(self):
		(resposta,) = self.enviar(
			[
				{
					"jsonrpc": "2.0",
					"id": 2,
					"method": "tools/call",
					"params": {"name": "categorizar_transacoes", "arguments": {"ids": ["T1"]}},
				}
			]
		)
		self.assertTrue(resposta["result"]["isError"])
		self.assertIn("somente leitura", resposta["result"]["content"][0]["text"])
		self.assertTrue(all(c["caminho"].endswith("listar_ferramentas") for c in FrappeFalso.chamadas))


class TestDiagnostico(BaseComServidor):
	def test_diagnostico_reporta_configuracao_incompleta(self):
		servidor = gris_mcp.ServidorMCP(gris_mcp.ClienteGris(url="", api_key="", api_secret=""))
		resultado = servidor.chamar_ferramenta("diagnostico_conexao", {})
		dados = json.loads(resultado["content"][0]["text"])
		self.assertFalse(dados["conectado"])
		self.assertIn("GRIS_URL", dados["erro"])

	def test_diagnostico_conectado_lista_ferramentas(self):
		resultado = self.servidor_mcp.chamar_ferramenta("diagnostico_conexao", {})
		dados = json.loads(resultado["content"][0]["text"])
		self.assertTrue(dados["conectado"])
		self.assertIn("listar_associados", dados["ferramentas_disponiveis"])


if __name__ == "__main__":
	unittest.main()
