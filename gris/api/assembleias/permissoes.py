# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Quem gerencia as assembleias (spec RF-01)."""

from __future__ import annotations

import frappe
from frappe import _

from gris.api.assembleias.constantes import ROLE_GESTOR_ASSEMBLEIAS

PAPEIS_GESTORES = frozenset({ROLE_GESTOR_ASSEMBLEIAS, "Gestor da UEL", "System Manager"})


def pode_gerenciar_assembleias(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	return bool(PAPEIS_GESTORES & set(frappe.get_roles(user)))


def garantir_gestor_assembleias(user: str | None = None) -> None:
	if not pode_gerenciar_assembleias(user):
		frappe.throw(_("Apenas quem gerencia as assembleias pode fazer isso."), frappe.PermissionError)
