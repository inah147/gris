"""API endpoints para gestão de Contas e Carteiras (ativar/desativar)."""

from __future__ import annotations

import frappe

_ALLOWED_DOCTYPES = {"Carteira", "Instituicao Financeira"}
_ALLOWED_ROLES = {"Gestor Financeiro", "System Manager"}


@frappe.whitelist()
def desativar(doctype: str, name: str) -> dict:
	"""Desativa uma Carteira ou Instituição Financeira.

	Requer role Gestor Financeiro ou System Manager.
	O registro continua acessível via Desk; apenas deixa de aparecer no portal.
	"""
	if doctype not in _ALLOWED_DOCTYPES:
		frappe.throw(
			f"Tipo de documento inválido: {doctype!r}",
			frappe.ValidationError,
		)

	roles = set(frappe.get_roles())
	if not (_ALLOWED_ROLES & roles):
		frappe.throw(
			"Sem permissão para desativar. Requer role Gestor Financeiro ou System Manager.",
			frappe.PermissionError,
		)

	if not frappe.has_permission(doctype, ptype="write", doc=name):
		frappe.throw(
			f"Sem permissão de escrita em {doctype} '{name}'.",
			frappe.PermissionError,
		)

	if not frappe.db.exists(doctype, name):
		frappe.throw(f"{doctype} '{name}' não encontrado.", frappe.DoesNotExistError)

	frappe.db.set_value(doctype, name, "ativa", 0)

	return {"success": True, "doctype": doctype, "name": name}


@frappe.whitelist()
def reativar(doctype: str, name: str) -> dict:
	"""Reativa uma Carteira ou Instituição Financeira desativada.

	Requer role Gestor Financeiro ou System Manager.
	"""
	if doctype not in _ALLOWED_DOCTYPES:
		frappe.throw(
			f"Tipo de documento inválido: {doctype!r}",
			frappe.ValidationError,
		)

	roles = set(frappe.get_roles())
	if not (_ALLOWED_ROLES & roles):
		frappe.throw(
			"Sem permissão para reativar. Requer role Gestor Financeiro ou System Manager.",
			frappe.PermissionError,
		)

	if not frappe.has_permission(doctype, ptype="write", doc=name):
		frappe.throw(
			f"Sem permissão de escrita em {doctype} '{name}'.",
			frappe.PermissionError,
		)

	if not frappe.db.exists(doctype, name):
		frappe.throw(f"{doctype} '{name}' não encontrado.", frappe.DoesNotExistError)

	frappe.db.set_value(doctype, name, "ativa", 1)

	return {"success": True, "doctype": doctype, "name": name}
