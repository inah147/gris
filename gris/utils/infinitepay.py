"""Utilitários comuns às telas que mostram dados devolvidos pela InfinitePay."""

from __future__ import annotations

from urllib.parse import urlparse

RECEIPT_URL_ALLOWED_HOSTS = {
	"api.infinitepay.io",
	"checkout.infinitepay.io",
	"recibo.infinitepay.io",
}


def is_safe_receipt_url(url: str | None) -> bool:
	"""True quando a URL é HTTPS e aponta para domínio conhecido da InfinitePay.

	O `receipt_url` chega pelo webhook; antes de virar link numa página ele precisa
	passar por aqui, para não renderizar um endereço arbitrário.
	"""
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
