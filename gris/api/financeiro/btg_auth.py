# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""
Autenticação OAuth 2.0 com o BTG Id (Authorization Code flow).

Fluxo esperado:
1. Admin abre a URL gerada por `gerar_url_autorizacao()` no browser.
2. O BTG redireciona para `redirect_uri?code=...`.
3. `www/financeiro/btg_oauth_callback.py` captura o `code` e chama `trocar_codigo_por_token`.
4. Os tokens são salvos em `Configuracao BTG Empresas`.
5. `get_valid_token()` é chamado por todos os outros módulos BTG; ele renova automaticamente
   o token quando está próximo de expirar usando o refresh_token.

Referências:
  https://developers.empresas.btgpactual.com/docs/authorization-code
  https://developers.empresas.btgpactual.com/docs/client-credentials
"""

import base64
from datetime import timedelta
from urllib.parse import urlencode

import frappe
import requests

BTG_AUTH_BASE_SANDBOX = "https://id.sandbox.btgpactual.com"
BTG_AUTH_BASE_PROD = "https://id.btgpactual.com"

BTG_API_BASE_SANDBOX = "https://api.sandbox.empresas.btgpactual.com"
BTG_API_BASE_PROD = "https://api.empresas.btgpactual.com"

_CONFIG_DOCTYPE = "Configuracao BTG Empresas"


def _get_config():
	return frappe.get_single(_CONFIG_DOCTYPE)


def _auth_base() -> str:
	config = _get_config()
	return BTG_AUTH_BASE_SANDBOX if config.sandbox_mode else BTG_AUTH_BASE_PROD


def get_api_base() -> str:
	config = _get_config()
	return BTG_API_BASE_SANDBOX if config.sandbox_mode else BTG_API_BASE_PROD


def _basic_credentials(config) -> str:
	raw = f"{config.client_id}:{config.get_password('client_secret')}"
	return base64.b64encode(raw.encode()).decode()


@frappe.whitelist()
def gerar_url_autorizacao() -> str:
	"""Constrói a URL de autorização OAuth2 para o fluxo Authorization Code.

	O admin deve abrir esta URL no browser para conceder consentimento.
	Após o login, o BTG redireciona para `redirect_uri?code=...`.
	"""
	config = _get_config()
	if not config.client_id or not config.redirect_uri:
		frappe.throw("Configure client_id e redirect_uri em Configuracao BTG Empresas.")

	scope = (config.scope or "").strip() or "openid"
	params = {
		"client_id": config.client_id,
		"response_type": "code",
		"redirect_uri": config.redirect_uri,
		"scope": scope,
		"prompt": "login",
	}
	return f"{_auth_base()}/oauth2/authorize?{urlencode(params)}"


@frappe.whitelist()
def trocar_codigo_por_token(code: str) -> dict:
	"""Troca o authorization code por access_token + refresh_token.

	Chamado pelo endpoint de callback OAuth após o redirect do BTG.
	"""
	config = _get_config()
	response = requests.post(
		f"{_auth_base()}/oauth2/token",
		headers={
			"Authorization": f"Basic {_basic_credentials(config)}",
			"Content-Type": "application/x-www-form-urlencoded",
		},
		data={
			"grant_type": "authorization_code",
			"code": code,
			"redirect_uri": config.redirect_uri,
		},
		timeout=30,
	)
	response.raise_for_status()
	data = response.json()
	_salvar_tokens(data)
	frappe.logger().info("BTG: authorization code trocado por tokens com sucesso.")
	return {"ok": True, "scope": data.get("scope", "")}


def renovar_token() -> str:
	"""Renova o access_token usando o refresh_token.

	Retorna o novo access_token.
	Levanta frappe.ValidationError se o refresh_token não estiver configurado.
	"""
	config = _get_config()
	refresh_token = config.get_password("refresh_token") or ""
	if not refresh_token:
		frappe.throw(
			"Refresh token não disponível. Faça a autorização OAuth novamente em "
			"Configuracao BTG Empresas.",
			frappe.ValidationError,
		)

	response = requests.post(
		f"{_auth_base()}/oauth2/token",
		headers={
			"Authorization": f"Basic {_basic_credentials(config)}",
			"Content-Type": "application/x-www-form-urlencoded",
		},
		data={
			"grant_type": "refresh_token",
			"refresh_token": refresh_token,
		},
		timeout=30,
	)
	response.raise_for_status()
	data = response.json()
	_salvar_tokens(data)
	frappe.logger().info("BTG: access_token renovado via refresh_token.")
	return data["access_token"]


def get_valid_token() -> str:
	"""Retorna um access_token válido, renovando automaticamente se necessário.

	Deve ser chamado por todos os módulos BTG antes de fazer requisições à API.
	"""
	config = _get_config()
	expires_at = config.token_expires_at

	# Considera expirado se estiver a menos de 5 minutos do prazo
	if expires_at and frappe.utils.now_datetime() < (expires_at - timedelta(minutes=5)):
		token = config.get_password("access_token") or ""
		if token:
			return token

	return renovar_token()


def get_api_headers() -> dict:
	"""Retorna headers prontos para requisições à API BTG, com token válido."""
	return {
		"Authorization": f"Bearer {get_valid_token()}",
		"Content-Type": "application/json",
		"Accept": "application/json",
	}


def _salvar_tokens(data: dict) -> None:
	"""Persiste access_token, refresh_token e data de expiração no Single doctype."""
	expires_in = int(data.get("expires_in") or 86400)
	expires_at = frappe.utils.now_datetime() + timedelta(seconds=expires_in)

	# set_value em Single doctypes usa (doctype, None, field, value) ou dict
	frappe.db.set_single_value(
		_CONFIG_DOCTYPE,
		{
			"access_token": data["access_token"],
			"refresh_token": data.get("refresh_token") or "",
			"token_expires_at": expires_at,
		},
	)
	frappe.db.commit()


def renovar_token_se_necessario() -> None:
	"""Scheduled task: renova o token BTG se estiver prestes a expirar."""
	try:
		config = _get_config()
		if not (config.get_password("access_token") or ""):
			return  # Ainda não autorizado

		expires_at = config.token_expires_at
		if expires_at and frappe.utils.now_datetime() < (expires_at - timedelta(hours=2)):
			return  # Ainda válido por mais de 2 horas

		renovar_token()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "BTG Token Renewal")
