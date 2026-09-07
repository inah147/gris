"""Descoberta OAuth para o transporte MCP sobre HTTP.

Só camada de protocolo, sem regra de negócio — no mesmo espírito de
``gris.api.mcp.http``. O endpoint MCP em si não precisa mudar (ver
``gris/tests/test_mcp_oauth.py`` e a seção de OAuth em MCP_CLAUDE.md): um
access token OAuth já autentica a sessão exatamente como a API key. O que
falta é a camada de descoberta na frente dele:

- RFC 9728 (``oauth_protected_resource``) — diz qual é o authorization
  server do recurso protegido.
- RFC 8414 (``oauth_authorization_server``) — espelha
  ``frappe.integrations.oauth2.openid_configuration`` e acrescenta o que ele
  não anuncia (PKCE, grant types, método de autenticação do client, escopos).
  Não altera o ``openid-configuration`` do Frappe, só reaproveita o que ele
  devolve.
- ``anunciar_recurso_protegido`` — hook ``after_request`` que acrescenta
  ``WWW-Authenticate`` numa chamada ao MCP sem token válido, apontando para
  os metadados do item anterior. Restrito ao caminho do MCP: não faz sentido
  anunciar o recurso em toda resposta 401/403 do site.

Ver PLANO_OAUTH_MCP.md (Fase 1) e MCP_CLAUDE.md#oauth-o-que-falta-para-virar-connector.
"""

from __future__ import annotations

import frappe
from frappe.integrations.oauth2 import openid_configuration
from frappe.oauth import get_server_url

CAMINHO_MCP = "/api/method/gris.api.mcp.http.mcp"
ESCOPO_MCP = "gris.mcp"


def _url_recurso_protegido() -> str:
	return f"{get_server_url()}/.well-known/oauth-protected-resource"


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep
def oauth_protected_resource() -> None:
	"""RFC 9728 — metadados do recurso protegido (o endpoint MCP)."""
	servidor = get_server_url()
	frappe.local.response = frappe._dict(
		{
			"resource": f"{servidor}{CAMINHO_MCP}",
			"authorization_servers": [servidor],
			"scopes_supported": [ESCOPO_MCP],
			"bearer_methods_supported": ["header"],
		}
	)


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep
def oauth_authorization_server() -> None:
	"""RFC 8414 — espelha ``openid_configuration`` e acrescenta o que falta lá.

	Sem ``code_challenge_methods_supported`` o cliente não descobre que o
	servidor suporta PKCE — e como o ``OAuth Client`` do Frappe não confere
	``client_secret`` (ver MCP_CLAUDE.md), o PKCE é a única proteção real do
	fluxo.
	"""
	openid_configuration()
	frappe.local.response.update(
		{
			"code_challenge_methods_supported": ["S256", "plain"],
			"grant_types_supported": ["authorization_code", "refresh_token"],
			"token_endpoint_auth_methods_supported": ["none"],
			"scopes_supported": [ESCOPO_MCP, "all", "openid"],
		}
	)


def anunciar_recurso_protegido(response, request) -> None:
	"""Acrescenta ``WWW-Authenticate`` numa chamada ao MCP sem token válido.

	Hook ``after_request``. Duas situações chegam aqui com o caminho do MCP:
	token ausente ou malformado (``is_whitelisted`` recusa o Guest com 403) e
	token inválido/expirado/revogado (``validate_auth`` já levanta
	``AuthenticationError``, 401). Nenhuma delas é erro de negócio — o
	``registry`` nunca propaga ``PermissionError`` até aqui, ele devolve um
	envelope JSON-RPC comum (200) para falhas de papel. Por isso as duas são
	tratadas como a mesma falta de credencial válida, com 401 nas duas.
	"""
	if response is None or request is None or request.path != CAMINHO_MCP:
		return
	if response.status_code not in (401, 403):
		return

	response.status_code = 401
	response.headers["WWW-Authenticate"] = f'Bearer resource_metadata="{_url_recurso_protegido()}"'
