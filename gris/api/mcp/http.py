"""Transporte MCP (JSON-RPC 2.0) sobre HTTP.

Alternativa ao bridge stdio para clientes que suportam servidores MCP remotos
com header de autenticação:

    claude mcp add --transport http gris \\
        https://<site>/api/method/gris.api.mcp.http.mcp \\
        --header "Authorization: token <api_key>:<api_secret>"

O catálogo e as regras de autorização são os mesmos de ``gris.api.mcp.registry``
— aqui só há tradução de protocolo. Respostas são JSON puro (sem SSE), o que o
protocolo permite para servidores sem streaming.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from gris.api.mcp import registry
from gris.api.mcp.endpoints import VERSAO_API, responder

VERSAO_PROTOCOLO = "2025-06-18"
NOME_SERVIDOR = "gris"

INSTRUCOES = (
	"Ferramentas do GRIS, sistema de gestão do Grupo Escoteiro. Permite consultar e atualizar "
	"associados, listar e categorizar transações financeiras e obter resumos. Sempre confirme "
	"com o usuário antes de gravar dados e use 'listar_opcoes_financeiras' ou "
	"'obter_associado' para descobrir valores válidos antes de atualizar."
)


def _json_seguro(valor: Any) -> str:
	return json.dumps(valor, ensure_ascii=False, indent=2, default=str)


def ferramenta_para_mcp(dados: dict) -> dict:
	return {
		"name": dados["nome"],
		"title": dados["titulo"],
		"description": dados["descricao"],
		"inputSchema": dados["input_schema"],
		"annotations": {
			"title": dados["titulo"],
			"readOnlyHint": dados["somente_leitura"],
			"destructiveHint": False,
			"idempotentHint": dados["somente_leitura"],
		},
	}


def resultado_para_mcp(resposta: dict) -> dict:
	"""Converte o envelope {"ok": ...} em um resultado de tools/call."""
	if resposta.get("ok"):
		return {"content": [{"type": "text", "text": _json_seguro(resposta.get("data"))}]}

	erro = resposta.get("error") or {}
	texto = f"[{erro.get('code', 'ERRO')}] {erro.get('message', 'Falha desconhecida.')}"
	if erro.get("details"):
		texto = f"{texto}\n{_json_seguro(erro['details'])}"
	return {"content": [{"type": "text", "text": texto}], "isError": True}


def processar_mensagem(mensagem: dict) -> dict | None:
	"""Processa uma mensagem JSON-RPC. Retorna None para notificações."""
	metodo = mensagem.get("method")
	identificador = mensagem.get("id")
	parametros = mensagem.get("params") or {}
	is_notificacao = identificador is None

	def resultado(payload: dict) -> dict | None:
		if is_notificacao:
			return None
		return {"jsonrpc": "2.0", "id": identificador, "result": payload}

	def erro(codigo: int, mensagem_erro: str) -> dict | None:
		if is_notificacao:
			return None
		return {"jsonrpc": "2.0", "id": identificador, "error": {"code": codigo, "message": mensagem_erro}}

	if metodo == "initialize":
		return resultado(
			{
				"protocolVersion": VERSAO_PROTOCOLO,
				"capabilities": {"tools": {"listChanged": False}},
				"serverInfo": {"name": NOME_SERVIDOR, "version": VERSAO_API},
				"instructions": INSTRUCOES,
			}
		)

	if metodo in ("notifications/initialized", "notifications/cancelled"):
		return None

	if metodo == "ping":
		return resultado({})

	if metodo == "tools/list":
		catalogo = responder(lambda: {"ok": True, "data": registry.listar()})
		if not catalogo.get("ok"):
			return erro(-32603, (catalogo.get("error") or {}).get("message", "Falha ao listar ferramentas."))
		return resultado({"tools": [ferramenta_para_mcp(item) for item in catalogo["data"]]})

	if metodo == "tools/call":
		nome = parametros.get("name")
		argumentos = parametros.get("arguments") or {}
		if not nome:
			return erro(-32602, "Parâmetro 'name' é obrigatório em tools/call.")
		resposta = responder(registry.executar, nome, argumentos)
		return resultado(resultado_para_mcp(resposta))

	return erro(-32601, f"Método não suportado: {metodo}")


@frappe.whitelist(methods=["POST"])
def mcp(**kwargs) -> None:
	"""Endpoint MCP. Escreve JSON-RPC puro em ``frappe.local.response``."""
	corpo = frappe.request.get_data(as_text=True) if frappe.request else ""

	try:
		mensagem = json.loads(corpo or "{}")
	except json.JSONDecodeError:
		resposta = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON inválido."}}
		_escrever(resposta, 400)
		return

	if not isinstance(mensagem, dict):
		resposta = {
			"jsonrpc": "2.0",
			"id": None,
			"error": {"code": -32600, "message": "Requisição JSON-RPC inválida."},
		}
		_escrever(resposta, 400)
		return

	resposta = processar_mensagem(mensagem)
	if resposta is None:
		_escrever({}, 202)
		return

	_escrever(resposta, 200)


def _escrever(payload: dict, http_status_code: int) -> None:
	frappe.local.response.clear()
	frappe.local.response.update(payload)
	frappe.local.response["http_status_code"] = http_status_code
