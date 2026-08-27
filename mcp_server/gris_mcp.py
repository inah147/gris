#!/usr/bin/env python3
"""Servidor MCP (stdio) que expõe as ferramentas do GRIS ao Claude.

Este processo é uma ponte fina: o catálogo de ferramentas, as regras de
permissão e a lógica de negócio ficam no app Frappe
(``gris.api.mcp``). Aqui só há tradução entre o protocolo MCP e a API REST
``/api/method/gris.api.mcp.endpoints.*``.

Sem dependências além da biblioteca padrão — basta Python 3.10+.

Configuração por variáveis de ambiente:
    GRIS_URL                   URL base do site (ex.: https://gris.gepim.com.br)
    GRIS_API_KEY               API key do usuário do GRIS
    GRIS_API_SECRET            API secret do usuário do GRIS
    GRIS_MCP_SOMENTE_LEITURA   "1" para esconder as ferramentas que gravam dados
    GRIS_MCP_TIMEOUT           timeout em segundos das chamadas HTTP (padrão: 30)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

NOME_SERVIDOR = "gris"
VERSAO = "1.0.0"
VERSAO_PROTOCOLO = "2025-06-18"

CAMINHO_LISTAR = "/api/method/gris.api.mcp.endpoints.listar_ferramentas"
CAMINHO_EXECUTAR = "/api/method/gris.api.mcp.endpoints.executar_ferramenta"

INSTRUCOES = (
	"Ferramentas do GRIS, sistema de gestão do Grupo Escoteiro. Permite consultar e atualizar "
	"associados, listar e categorizar transações financeiras e obter resumos. Sempre confirme "
	"com o usuário antes de gravar dados e use 'listar_opcoes_financeiras' ou 'obter_associado' "
	"para descobrir valores válidos antes de atualizar."
)

FERRAMENTA_DIAGNOSTICO = {
	"name": "diagnostico_conexao",
	"title": "Diagnosticar conexão com o GRIS",
	"description": (
		"Verifica a configuração local (URL e credenciais) e a conectividade com o site do GRIS. "
		"Use quando qualquer outra ferramenta falhar por conexão ou autenticação."
	),
	"inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
	"annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True},
}


class ErroDeConfiguracao(Exception):
	pass


class ErroDeConexao(Exception):
	pass


def log(mensagem: str) -> None:
	"""Logs vão para stderr: stdout é exclusivo do protocolo MCP."""
	print(f"[gris-mcp] {mensagem}", file=sys.stderr, flush=True)


class ClienteGris:
	"""Cliente HTTP mínimo para a API MCP do GRIS."""

	def __init__(
		self,
		url: str | None = None,
		api_key: str | None = None,
		api_secret: str | None = None,
		timeout: float | None = None,
	):
		self.url = (url or os.environ.get("GRIS_URL", "")).strip().rstrip("/")
		self.api_key = (api_key or os.environ.get("GRIS_API_KEY", "")).strip()
		self.api_secret = (api_secret or os.environ.get("GRIS_API_SECRET", "")).strip()
		try:
			self.timeout = float(timeout or os.environ.get("GRIS_MCP_TIMEOUT", "30"))
		except ValueError:
			self.timeout = 30.0

	def validar_configuracao(self) -> None:
		faltando = [
			nome
			for nome, valor in (
				("GRIS_URL", self.url),
				("GRIS_API_KEY", self.api_key),
				("GRIS_API_SECRET", self.api_secret),
			)
			if not valor
		]
		if faltando:
			raise ErroDeConfiguracao(
				"Configuração incompleta. Defina: " + ", ".join(faltando) + ". Veja mcp_server/README.md."
			)
		if not self.url.startswith(("http://", "https://")):
			raise ErroDeConfiguracao(f"GRIS_URL precisa começar com http:// ou https:// (atual: {self.url}).")

	def _requisitar(self, caminho: str, payload: dict) -> dict:
		self.validar_configuracao()
		corpo = json.dumps(payload).encode("utf-8")
		requisicao = urllib.request.Request(
			f"{self.url}{caminho}",
			data=corpo,
			method="POST",
			headers={
				"Content-Type": "application/json",
				"Accept": "application/json",
				"Authorization": f"token {self.api_key}:{self.api_secret}",
				"User-Agent": f"{NOME_SERVIDOR}-mcp/{VERSAO}",
			},
		)

		try:
			with urllib.request.urlopen(requisicao, timeout=self.timeout) as resposta:
				dados = json.loads(resposta.read().decode("utf-8") or "{}")
		except urllib.error.HTTPError as exc:
			detalhe = exc.read().decode("utf-8", errors="replace")[:500]
			if exc.code in (401, 403):
				raise ErroDeConexao(
					"Credenciais recusadas pelo GRIS (HTTP "
					f"{exc.code}). Confira GRIS_API_KEY/GRIS_API_SECRET e as permissões do usuário."
				)
			if exc.code == 404:
				raise ErroDeConexao(
					"Endpoint não encontrado (HTTP 404). O app precisa estar na versão com "
					"gris.api.mcp instalado e o site migrado."
				)
			raise ErroDeConexao(f"O GRIS respondeu HTTP {exc.code}: {detalhe}")
		except urllib.error.URLError as exc:
			raise ErroDeConexao(f"Não foi possível conectar em {self.url}: {exc.reason}")
		except json.JSONDecodeError:
			raise ErroDeConexao("O GRIS devolveu uma resposta que não é JSON (proxy ou login pelo meio?).")

		# Frappe embrulha o retorno do método whitelisted em "message".
		return dados.get("message", dados)

	def listar_ferramentas(self) -> list[dict]:
		resposta = self._requisitar(CAMINHO_LISTAR, {})
		if not resposta.get("ok"):
			erro = resposta.get("error") or {}
			raise ErroDeConexao(erro.get("message", "Falha ao listar as ferramentas do GRIS."))
		return (resposta.get("data") or {}).get("ferramentas", [])

	def executar(self, nome: str, argumentos: dict) -> dict:
		return self._requisitar(CAMINHO_EXECUTAR, {"ferramenta": nome, "argumentos": argumentos})

	def diagnostico(self) -> dict:
		resultado: dict[str, Any] = {
			"url": self.url or "(não definida)",
			"api_key_definida": bool(self.api_key),
			"api_secret_definida": bool(self.api_secret),
			"timeout_segundos": self.timeout,
			"somente_leitura": somente_leitura_ativo(),
		}
		try:
			ferramentas = self.listar_ferramentas()
		except (ErroDeConfiguracao, ErroDeConexao) as exc:
			resultado["conectado"] = False
			resultado["erro"] = str(exc)
			return resultado

		resultado["conectado"] = True
		resultado["ferramentas_disponiveis"] = [f["nome"] for f in ferramentas]
		return resultado


def somente_leitura_ativo() -> bool:
	return os.environ.get("GRIS_MCP_SOMENTE_LEITURA", "").strip().lower() in {"1", "true", "sim", "yes"}


def json_texto(valor: Any) -> str:
	return json.dumps(valor, ensure_ascii=False, indent=2, default=str)


def ferramenta_para_mcp(dados: dict) -> dict:
	somente_leitura = bool(dados.get("somente_leitura", True))
	return {
		"name": dados["nome"],
		"title": dados.get("titulo") or dados["nome"],
		"description": dados.get("descricao", ""),
		"inputSchema": dados.get("input_schema") or {"type": "object", "properties": {}},
		"annotations": {
			"title": dados.get("titulo") or dados["nome"],
			"readOnlyHint": somente_leitura,
			"destructiveHint": False,
			"idempotentHint": somente_leitura,
		},
	}


def conteudo_texto(texto: str, erro: bool = False) -> dict:
	resultado = {"content": [{"type": "text", "text": texto}]}
	if erro:
		resultado["isError"] = True
	return resultado


def resultado_para_mcp(resposta: dict) -> dict:
	if resposta.get("ok"):
		return conteudo_texto(json_texto(resposta.get("data")))

	erro = resposta.get("error") or {}
	texto = f"[{erro.get('code', 'ERRO')}] {erro.get('message', 'Falha desconhecida.')}"
	if erro.get("details"):
		texto = f"{texto}\n{json_texto(erro['details'])}"
	return conteudo_texto(texto, erro=True)


class ServidorMCP:
	def __init__(self, cliente: ClienteGris | None = None):
		self.cliente = cliente or ClienteGris()
		self._catalogo: dict[str, dict] = {}

	# -- protocolo ---------------------------------------------------------
	def processar(self, mensagem: dict) -> dict | None:
		metodo = mensagem.get("method")
		identificador = mensagem.get("id")
		parametros = mensagem.get("params") or {}
		is_notificacao = identificador is None

		def ok(payload: dict) -> dict | None:
			return None if is_notificacao else {"jsonrpc": "2.0", "id": identificador, "result": payload}

		def falha(codigo: int, texto: str) -> dict | None:
			if is_notificacao:
				return None
			return {"jsonrpc": "2.0", "id": identificador, "error": {"code": codigo, "message": texto}}

		if metodo == "initialize":
			return ok(
				{
					"protocolVersion": parametros.get("protocolVersion") or VERSAO_PROTOCOLO,
					"capabilities": {"tools": {"listChanged": False}},
					"serverInfo": {"name": NOME_SERVIDOR, "version": VERSAO},
					"instructions": INSTRUCOES,
				}
			)

		if metodo is not None and metodo.startswith("notifications/"):
			return None

		if metodo == "ping":
			return ok({})

		if metodo == "tools/list":
			return ok({"tools": self.listar_ferramentas()})

		if metodo == "tools/call":
			nome = parametros.get("name")
			if not nome:
				return falha(-32602, "Parâmetro 'name' é obrigatório em tools/call.")
			return ok(self.chamar_ferramenta(nome, parametros.get("arguments") or {}))

		return falha(-32601, f"Método não suportado: {metodo}")

	# -- ferramentas -------------------------------------------------------
	def listar_ferramentas(self) -> list[dict]:
		ferramentas = [FERRAMENTA_DIAGNOSTICO]
		try:
			remotas = self.cliente.listar_ferramentas()
		except (ErroDeConfiguracao, ErroDeConexao) as exc:
			log(f"não foi possível carregar o catálogo: {exc}")
			return ferramentas

		self._catalogo = {item["nome"]: item for item in remotas}
		for item in remotas:
			if somente_leitura_ativo() and not item.get("somente_leitura", True):
				continue
			ferramentas.append(ferramenta_para_mcp(item))
		return ferramentas

	def chamar_ferramenta(self, nome: str, argumentos: dict) -> dict:
		if nome == FERRAMENTA_DIAGNOSTICO["name"]:
			return conteudo_texto(json_texto(self.cliente.diagnostico()))

		if somente_leitura_ativo():
			definicao = self._catalogo.get(nome)
			if definicao is None:
				# Catálogo ainda não carregado nesta sessão: recarrega para decidir.
				self.listar_ferramentas()
				definicao = self._catalogo.get(nome)
			if definicao is not None and not definicao.get("somente_leitura", True):
				return conteudo_texto(
					f"A ferramenta '{nome}' grava dados e o servidor está em modo somente leitura "
					"(GRIS_MCP_SOMENTE_LEITURA).",
					erro=True,
				)

		try:
			resposta = self.cliente.executar(nome, argumentos)
		except (ErroDeConfiguracao, ErroDeConexao) as exc:
			return conteudo_texto(f"[CONEXAO] {exc}", erro=True)

		return resultado_para_mcp(resposta)

	# -- loop --------------------------------------------------------------
	def executar_loop(self, entrada=None, saida=None) -> None:
		entrada = entrada or sys.stdin
		saida = saida or sys.stdout

		for linha in entrada:
			linha = linha.strip()
			if not linha:
				continue

			try:
				mensagem = json.loads(linha)
			except json.JSONDecodeError:
				self._escrever(
					saida,
					{"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON inválido."}},
				)
				continue

			try:
				resposta = self.processar(mensagem)
			except Exception as exc:  # nunca derruba o servidor por causa de uma mensagem
				log(f"erro inesperado: {exc!r}")
				resposta = {
					"jsonrpc": "2.0",
					"id": mensagem.get("id"),
					"error": {"code": -32603, "message": f"Erro interno do bridge: {exc}"},
				}

			if resposta is not None:
				self._escrever(saida, resposta)

	@staticmethod
	def _escrever(saida, payload: dict) -> None:
		saida.write(json.dumps(payload, ensure_ascii=False) + "\n")
		saida.flush()


def main() -> int:
	cliente = ClienteGris()
	try:
		cliente.validar_configuracao()
	except ErroDeConfiguracao as exc:
		# Não aborta: o Claude ainda consegue chamar 'diagnostico_conexao'.
		log(str(exc))

	log(f"iniciado (site: {cliente.url or 'não configurado'}, somente_leitura={somente_leitura_ativo()})")
	ServidorMCP(cliente).executar_loop()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
