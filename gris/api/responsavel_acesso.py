# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Resolução do responsável logado e dos beneficiários vinculados a ele.

Toda tela da área `/responsavel` precisa responder duas perguntas antes de
mostrar qualquer dado: quem é o responsável por trás desta sessão e quais
beneficiários são dele. Concentrar isso aqui evita que cada página invente sua
própria versão da cadeia de fallback — e é essa cadeia que delimita o que o
responsável pode ver.
"""

from __future__ import annotations

import frappe


def get_responsavel_do_usuario(user: str | None = None) -> str | None:
	"""Nome do `Responsavel` correspondente ao usuário da sessão.

	A conta pode chegar por três caminhos, do mais direto ao mais indireto:
	o e-mail do próprio `Responsavel`, um login `id@escoteiros` cujo CPF nomeia
	um `Responsavel`, ou um vínculo já existente apontando para o associado
	daquele login.
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None

	responsavel_name = frappe.db.get_value("Responsavel", {"email": user}, "name")
	if responsavel_name:
		return responsavel_name

	# Fallback para contas com login id@escoteiros associadas a um registro no doctype Associado
	associado_name = frappe.db.get_value("Associado", {"id_escoteiros": user}, "name")
	if not associado_name:
		return None

	associado_cpf_hash = frappe.db.get_value("Associado", associado_name, "cpf")
	if associado_cpf_hash and frappe.db.exists("Responsavel", associado_cpf_hash):
		return associado_cpf_hash

	# Último fallback: tentar via vínculo já existente do associado
	return frappe.db.get_value(
		"Responsavel Vinculo", {"beneficiario_associado": associado_name}, "responsavel"
	)


def get_beneficiarios_associados(responsavel: str | None) -> list[str]:
	"""Associados já registrados vinculados ao responsável.

	Só entram os beneficiários que viraram `Associado` — quem ainda está em
	integração vive em `Novo Associado` e não tem contribuição a apurar.
	"""
	if not responsavel:
		return []

	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": responsavel},
		fields=["beneficiario_associado"],
	)
	return [v.beneficiario_associado for v in vinculos if v.beneficiario_associado]
