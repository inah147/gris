"""API e helpers para a página pública /festas/convite_confirmado.

Responsabilidades:
- Gerar e validar tokens HMAC que protegem o acesso à página de confirmação.
- Montar a `redirect_url` que a Infinitepay usa após o checkout.
- Endpoint AJAX leve (`get_status`) para o polling do estado do pagamento.
- Utilitários de segurança: mascarar e-mails e validar a `receipt_url` retornada
  pela Infinitepay (evitando renderizar links arbitrários).

A página em si (`gris.www.festas.convite_confirmado`) chama estes helpers no
`get_context`. Nenhuma rota desta API dispara side-effects (envio de WhatsApp,
e-mail, alteração de dados). Side-effects acontecem só no fluxo do webhook.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from urllib.parse import urlparse

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import get_url
from frappe.utils.verified_command import get_secret

CONVITE_NAME_RE = re.compile(r"^CF-\d{4}-\d+$")
RECEIPT_URL_ALLOWED_HOSTS = {
	"api.infinitepay.io",
	"checkout.infinitepay.io",
	"recibo.infinitepay.io",
}
TOKEN_PURPOSE = "convite_confirmado.v1"
PAGE_PATH = "/festas/convite_confirmado"


# ─── Validação / construção de identificador ──────────────────────────────────


def _is_valid_convite_name(name: str | None) -> bool:
	return bool(name) and bool(CONVITE_NAME_RE.match(name))


def _build_token(convite_name: str) -> str:
	"""HMAC-SHA256 do nome do convite usando o secret do site.

	Determinístico (mesmo nome → mesmo token), o que é aceitável porque a página
	sempre reflete o estado atual da cobrança — não há "ação" persistida no token.
	"""
	if not _is_valid_convite_name(convite_name):
		raise ValueError("Invalid convite name")
	message = f"{TOKEN_PURPOSE}:{convite_name}".encode()
	return hmac.new(get_secret().encode(), message, hashlib.sha256).hexdigest()


def _validate_token(convite_name: str | None, token: str | None) -> bool:
	if not _is_valid_convite_name(convite_name) or not token:
		return False
	try:
		expected = _build_token(convite_name)
	except ValueError:
		return False
	return hmac.compare_digest(expected, token)


def _build_redirect_url(convite_name: str) -> str:
	"""URL absoluta para onde a Infinitepay redireciona após o pagamento."""
	if not _is_valid_convite_name(convite_name):
		raise ValueError("Invalid convite name")
	token = _build_token(convite_name)
	return f"{_site_base_url()}{PAGE_PATH}?c={convite_name}&t={token}"


def _site_base_url() -> str:
	"""Base URL do site, resiliente a contextos sem request HTTP completo.

	`frappe.utils.get_url()` espera `frappe.local.request.host`; em jobs de
	background ou testes com request stub, esse atributo pode não existir.
	Tentamos o caminho normal e caímos no nome do site quando necessário.
	"""
	try:
		return get_url()
	except (AttributeError, TypeError):
		conf = getattr(frappe.local, "conf", None) or {}
		host_name = conf.get("host_name") or conf.get("hostname")
		if host_name:
			return host_name if host_name.startswith(("http://", "https://")) else f"http://{host_name}"
		site = getattr(frappe.local, "site", "") or ""
		protocol = "https://" if conf.get("ssl_certificate") else "http://"
		return f"{protocol}{site}" if site else "http://127.0.0.1"


# ─── Mascaramento / validação de URLs ─────────────────────────────────────────


def _mask_email(email: str | None) -> str:
	"""Retorna e-mail no formato 'a***@dominio.com'.

	Conservador: se algo estiver fora do esperado, retorna string vazia para o
	template, em vez de vazar o valor cru.
	"""
	if not email or "@" not in email:
		return ""
	local, _, domain = email.partition("@")
	if not local or "." not in domain:
		return ""
	if len(local) <= 1:
		mascara_local = f"{local}***"
	else:
		mascara_local = f"{local[0]}***"
	return f"{mascara_local}@{domain}"


def _is_safe_receipt_url(url: str | None) -> bool:
	"""True quando a URL é HTTPS e aponta para domínio conhecido da Infinitepay."""
	if not url:
		return False
	try:
		parsed = urlparse(url)
	except ValueError:
		return False
	if parsed.scheme != "https":
		return False
	host = (parsed.hostname or "").lower()
	return host in RECEIPT_URL_ALLOWED_HOSTS


# ─── Endpoint AJAX para polling ───────────────────────────────────────────────


# Público por necessidade: polling da página de confirmação, acessada pelo comprador
# sem login. Exige o par convite+token, tem rate limit e devolve só status e data.
@frappe.whitelist(allow_guest=True)  # nosemgrep
@rate_limit(key="convite-confirmado-status", limit=30, seconds=60)
def get_status(c: str | None = None, t: str | None = None) -> dict:
	"""Retorna apenas o status de pagamento + timestamp. Sem dados sensíveis.

	Usado pelo polling client-side enquanto a página estiver em modo "aguardando".
	"""
	convite_name = (c or "").strip()
	token = (t or "").strip()

	if not _validate_token(convite_name, token):
		frappe.local.response["http_status_code"] = 404
		return {"status": "Indisponivel", "atualizado_em": None}

	row = frappe.db.get_value(
		"Convite Festa",
		convite_name,
		["cobranca_infinitepay", "modified"],
		as_dict=True,
	)
	if not row:
		frappe.local.response["http_status_code"] = 404
		return {"status": "Indisponivel", "atualizado_em": None}

	if not row.cobranca_infinitepay:
		return {
			"status": "Pendente",
			"atualizado_em": row.modified.isoformat() if row.modified else None,
		}

	cobranca = (
		frappe.db.get_value(
			"Cobranca Infinitepay",
			row.cobranca_infinitepay,
			["status", "modified"],
			as_dict=True,
		)
		or {}
	)
	status = cobranca.get("status") or "Pendente"
	modified = cobranca.get("modified")
	return {
		"status": status,
		"atualizado_em": modified.isoformat() if modified else None,
	}
