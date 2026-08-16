"""Regras de acesso do fluxo de insígnias e distintivos.

Reaproveita os papéis já existentes no Gris:
- solicitação e entrega: Equipe de Metodos / Gestor de Metodos;
- compra e recebimento: Gestor Financeiro.
"""

from __future__ import annotations

import frappe

ROLES_SOLICITANTE = ("Equipe de Metodos", "Gestor de Metodos")
ROLES_GESTOR_METODOS = ("Gestor de Metodos",)
ROLES_FINANCEIRO = ("Gestor Financeiro",)
ROLE_ADMIN = "System Manager"


def _roles(user: str | None = None) -> set[str]:
	return set(frappe.get_roles(user or frappe.session.user))


def is_admin(user: str | None = None) -> bool:
	return ROLE_ADMIN in _roles(user)


def pode_solicitar(user: str | None = None) -> bool:
	roles = _roles(user)
	return bool(roles & set(ROLES_SOLICITANTE)) or ROLE_ADMIN in roles


def pode_comprar(user: str | None = None) -> bool:
	roles = _roles(user)
	return bool(roles & set(ROLES_FINANCEIRO)) or ROLE_ADMIN in roles


def pode_ver_todas(user: str | None = None) -> bool:
	"""Quem enxerga a fila completa: financeiro e gestão de métodos."""
	roles = _roles(user)
	return bool(roles & (set(ROLES_FINANCEIRO) | set(ROLES_GESTOR_METODOS))) or ROLE_ADMIN in roles


def pode_gerenciar_catalogo(user: str | None = None) -> bool:
	"""Quem cadastra e edita o catálogo de insígnias: gestão de métodos."""
	roles = _roles(user)
	return bool(roles & set(ROLES_GESTOR_METODOS)) or ROLE_ADMIN in roles


def garantir_gestor_catalogo(user: str | None = None) -> None:
	if not pode_gerenciar_catalogo(user):
		frappe.throw(
			"Apenas a gestão de métodos pode manter o catálogo de insígnias e distintivos.",
			frappe.PermissionError,
		)


def garantir_solicitante(user: str | None = None) -> None:
	if not pode_solicitar(user):
		frappe.throw(
			"Você não tem permissão para solicitar insígnias e distintivos.",
			frappe.PermissionError,
		)


def garantir_financeiro(user: str | None = None) -> None:
	if not pode_comprar(user):
		frappe.throw(
			"Apenas o responsável do financeiro pode registrar a compra.",
			frappe.PermissionError,
		)


def pode_ver_solicitacao(doc, user: str | None = None) -> bool:
	user = user or frappe.session.user
	return doc.solicitante == user or pode_ver_todas(user)


def garantir_acesso_solicitacao(doc, user: str | None = None) -> None:
	if not pode_ver_solicitacao(doc, user):
		frappe.throw("Você não tem acesso a esta solicitação.", frappe.PermissionError)


def pode_cancelar(doc, user: str | None = None) -> bool:
	"""O próprio solicitante ou a gestão de métodos cancelam, enquanto não houver compra."""
	from gris.gris.doctype.solicitacao_de_insignias.solicitacao_de_insignias import (
		STATUS_COMPRADA,
		STATUS_SOLICITADA,
	)

	user = user or frappe.session.user
	if doc.status not in {STATUS_SOLICITADA, STATUS_COMPRADA}:
		return False

	roles = _roles(user)
	if doc.status == STATUS_COMPRADA:
		# Depois da compra, só financeiro/admin desfazem (ex.: pedido cancelado no fornecedor).
		return bool(roles & set(ROLES_FINANCEIRO)) or ROLE_ADMIN in roles

	if doc.solicitante == user:
		return True
	return bool(roles & set(ROLES_GESTOR_METODOS)) or ROLE_ADMIN in roles


def pode_registrar_entrega(doc, user: str | None = None) -> bool:
	"""Entrega é confirmada por quem pediu ou pela gestão de métodos."""
	from gris.gris.doctype.solicitacao_de_insignias.solicitacao_de_insignias import STATUS_RECEBIDA

	user = user or frappe.session.user
	if doc.status != STATUS_RECEBIDA:
		return False

	if doc.solicitante == user:
		return True

	roles = _roles(user)
	return bool(roles & (set(ROLES_GESTOR_METODOS) | set(ROLES_FINANCEIRO))) or ROLE_ADMIN in roles
