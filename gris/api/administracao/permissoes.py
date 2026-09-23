"""Quem edita a estrutura da UEL.

A leitura é aberta a qualquer pessoa logada — a estrutura do grupo é informação de
todo mundo, e as páginas são mapeadas como `All` em `PAGE_ROLES`. Editar é da
diretoria: `Gestor da UEL`.
"""

from __future__ import annotations

import frappe
from frappe import _

ROLE_GESTOR_UEL = "Gestor da UEL"
ROLE_ADMIN = "System Manager"


def _roles(user: str | None = None) -> set[str]:
	return set(frappe.get_roles(user or frappe.session.user))


def pode_gerenciar_estrutura(user: str | None = None) -> bool:
	return bool({ROLE_GESTOR_UEL, ROLE_ADMIN} & _roles(user))


def garantir_gestor_estrutura(user: str | None = None) -> None:
	if not pode_gerenciar_estrutura(user):
		frappe.throw(
			_("Apenas a gestão da UEL pode alterar as áreas e funções do grupo."),
			frappe.PermissionError,
		)


def garantir_leitura() -> None:
	"""A estrutura é aberta, mas não para quem não entrou."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Entre no portal para ver a estrutura da UEL."), frappe.PermissionError)
