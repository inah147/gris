# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from typing import Any

import frappe
from frappe import _


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
