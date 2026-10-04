# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Código do link público da contribuição mensal (`/contribuicao/<código>`).

Cada beneficiário tem um código fixo, gerado no primeiro uso. É ele que o
WhatsApp leva no lugar do link da InfinitePay. O gestor pode regenerá-lo, o que
invalida o link anterior.
"""

from __future__ import annotations

import re

import frappe
from frappe import _

from gris.api.financeiro.contribuicoes import ROLE_GESTOR

COMPRIMENTO_TOKEN = 32
PADRAO_TOKEN = re.compile(rf"^[0-9a-z]{{{COMPRIMENTO_TOKEN}}}$")
CAMPO_TOKEN = "token_contribuicao"
ROTA_PUBLICA = "/contribuicao"


def token_valido(token: str | None) -> bool:
	return bool(token) and bool(PADRAO_TOKEN.match(token))


def _gerar_token() -> str:
	return frappe.generate_hash(length=COMPRIMENTO_TOKEN).lower()


def obter_token(associado: str) -> str:
	"""Código do associado; gera no primeiro uso."""
	atual = frappe.db.get_value("Associado", associado, CAMPO_TOKEN)
	if atual:
		return atual
	if not frappe.db.exists("Associado", associado):
		frappe.throw(_("Associado {0} não encontrado.").format(associado), frappe.DoesNotExistError)
	return _gravar_token(associado)


def _gravar_token(associado: str) -> str:
	token = _gerar_token()
	# Sem passar pelo documento: o campo é só de sistema (permlevel 3, somente leitura).
	frappe.db.set_value("Associado", associado, CAMPO_TOKEN, token, update_modified=False)
	# O código pode nascer durante a renderização de uma página (GET), que o Frappe
	# desfaria no fim da requisição; sem isto o link mostrado mudaria a cada visita.
	frappe.local.flags.commit = True
	return token


def regenerar_token(associado: str) -> str:
	"""Troca o código e invalida o link antigo. Só o gestor da contribuição pode."""
	if ROLE_GESTOR not in frappe.get_roles():
		frappe.throw(
			_("Requer acesso Gestor Contribuição Mensal para regenerar o link."),
			frappe.PermissionError,
		)
	if not frappe.db.exists("Associado", associado):
		frappe.throw(_("Associado {0} não encontrado.").format(associado), frappe.DoesNotExistError)
	return _gravar_token(associado)


def associado_do_token(token: str | None) -> str | None:
	"""Associado dono do código, ou `None` para código inexistente ou malformado."""
	if not token_valido(token):
		return None
	return frappe.db.get_value("Associado", {CAMPO_TOKEN: token}, "name")


def url_publica(associado: str, *, criar: bool = True) -> str | None:
	"""Link público absoluto do beneficiário.

	Com `criar=False` só devolve o link de quem já tem código, sem gravar nada —
	para as leituras (MCP) que não podem ter efeito colateral.
	"""
	if criar:
		token = obter_token(associado)
	else:
		token = frappe.db.get_value("Associado", associado, CAMPO_TOKEN)
		if not token:
			return None
	try:
		base = frappe.utils.get_url()
	except Exception:
		base = f"https://{frappe.local.site}"
	return f"{base.rstrip('/')}{ROTA_PUBLICA}/{token}"
