# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from typing import Any

import frappe
from frappe import _


def format_phone(phone):
	"""Normaliza número de telefone para armazenamento no formato +55DDNÚMERO.

	Corrige DDD duplicado (e.g. +1111971872252 → +5511971872252).
	Aceita formatos como: +5511999999999, 5511999999999, 11999999999, (11) 99999-9999.
	"""
	if not phone:
		return phone

	digits = "".join(filter(str.isdigit, str(phone)))

	if not digits:
		return ""

	# Fix duplicate DDD with country code: e.g. 551111971872252 (15 digits) → 5511971872252
	if digits.startswith("55") and len(digits) >= 14 and digits[2:4] == digits[4:6]:
		digits = digits[:2] + digits[4:]

	# Fix duplicate DDD without country code: e.g. 1111971872252 (13 digits) → 11971872252
	if not digits.startswith("55") and len(digits) > 11 and digits[:2] == digits[2:4]:
		digits = digits[2:]

	# Brazil numbers are usually 10 or 11 digits (DDD + 8 or 9 digit number)
	if len(digits) in [10, 11]:
		return f"+55{digits}"

	# Already has country code (12 or 13 digits)
	if len(digits) in [12, 13] and digits.startswith("55"):
		return f"+{digits}"

	return phone


@frappe.whitelist()
def get_contato_pessoa(doctype_name: str, docname: str) -> dict[str, Any]:
	if doctype_name not in {"Associado", "Responsavel"}:
		frappe.throw(_("Tipo de pessoa invalido."))

	if doctype_name == "Associado":
		return _get_associado_payload(docname)

	return _get_responsavel_payload(docname)


def _get_associado_payload(name: str) -> dict[str, Any]:
	data = frappe.db.get_value(
		"Associado",
		name,
		["nome_completo", "data_de_nascimento", "id_escoteiros", "email", "telefone"],
		as_dict=True,
	)
	if not data:
		frappe.throw(_("Associado nao encontrado."))

	email = data.get("id_escoteiros") or data.get("email")
	if not email or not data.get("telefone"):
		frappe.throw(_("Associado selecionado nao possui email ou telefone preenchido."))

	return {
		"nome": data.get("nome_completo") or name,
		"email": email,
		"telefone": data.get("telefone"),
		"data_de_nascimento": data.get("data_de_nascimento"),
	}


def _get_responsavel_payload(name: str) -> dict[str, Any]:
	data = frappe.db.get_value(
		"Responsavel",
		name,
		["nome_completo", "data_de_nascimento", "email", "celular", "telefone_secundario"],
		as_dict=True,
	)
	if not data:
		frappe.throw(_("Responsavel nao encontrado."))

	telefone = data.get("celular") or data.get("telefone_secundario")
	if not data.get("email") or not telefone:
		frappe.throw(_("Responsavel selecionado nao possui email ou telefone preenchido."))

	return {
		"nome": data.get("nome_completo") or name,
		"email": data.get("email"),
		"telefone": telefone,
		"data_de_nascimento": data.get("data_de_nascimento"),
	}
