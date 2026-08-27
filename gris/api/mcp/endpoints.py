"""API REST da integração MCP.

Consumida pelo bridge stdio (``mcp_server/gris_mcp.py``) e por qualquer outro
cliente que prefira REST simples ao protocolo MCP:

    POST /api/method/gris.api.mcp.endpoints.listar_ferramentas
    POST /api/method/gris.api.mcp.endpoints.executar_ferramenta
         {"ferramenta": "listar_associados", "argumentos": {"ramo": "Lobinho"}}

Autenticação: header ``Authorization: token <api_key>:<api_secret>`` de um
usuário do GRIS. Não existe acesso guest — as permissões do usuário valem
integralmente, tanto pelos papéis declarados em cada ferramenta quanto pelas
permissões de DocType do Frappe.

Todas as respostas usam o mesmo envelope:
    {"ok": true, "data": {...}}
    {"ok": false, "error": {"code": "...", "message": "..."}}
"""

from __future__ import annotations

import frappe

from gris.api.mcp import registry

VERSAO_API = "1.0.0"


def _erro(codigo: str, mensagem: str, detalhes: dict | None = None) -> dict:
	erro: dict = {"code": codigo, "message": mensagem}
	if detalhes:
		erro["details"] = detalhes
	return {"ok": False, "error": erro}


def responder(callback, *args, **kwargs) -> dict:
	"""Executa ``callback`` traduzindo exceções para o envelope de erro."""
	try:
		return callback(*args, **kwargs)
	except registry.ErroDeFerramenta as exc:
		return exc.as_dict()
	except frappe.PermissionError as exc:
		return _erro("PERMISSAO_NEGADA", str(exc) or "Permissão negada para esta operação.")
	except frappe.DoesNotExistError as exc:
		return _erro("NAO_ENCONTRADO", str(exc) or "Registro não encontrado.")
	except frappe.ValidationError as exc:
		# frappe.throw em validações de negócio: a mensagem já é para o usuário.
		return _erro("VALIDACAO", str(exc) or "Dados inválidos.")
	except Exception:
		frappe.log_error(title="Erro na integração MCP", message=frappe.get_traceback())
		return _erro("ERRO_INTERNO", "Erro interno ao executar a ferramenta. Verifique o Error Log.")


@frappe.whitelist(methods=["GET", "POST"])
def listar_ferramentas(incluir_indisponiveis: int | str | bool = 0) -> dict:
	"""Catálogo de ferramentas visíveis para o usuário autenticado."""

	def _executar() -> dict:
		incluir = str(incluir_indisponiveis).strip().lower() in {"1", "true", "sim", "yes"}
		return {
			"ok": True,
			"data": {
				"versao": VERSAO_API,
				"usuario": frappe.session.user,
				"ferramentas": registry.listar(incluir_indisponiveis=incluir),
			},
		}

	return responder(_executar)


@frappe.whitelist(methods=["POST"])
def executar_ferramenta(ferramenta: str | None = None, argumentos=None) -> dict:
	"""Executa uma ferramenta do catálogo com os argumentos informados."""

	def _executar() -> dict:
		if not ferramenta:
			return _erro("ARGUMENTO_INVALIDO", "Informe o nome da ferramenta em 'ferramenta'.")

		args = argumentos
		if isinstance(args, str):
			args = frappe.parse_json(args or "{}")
		if args is None:
			args = {}
		if not isinstance(args, dict):
			return _erro("ARGUMENTO_INVALIDO", "'argumentos' precisa ser um objeto JSON.")

		return registry.executar(ferramenta, args)

	return responder(_executar)
