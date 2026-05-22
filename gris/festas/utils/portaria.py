# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Helpers para a área Portaria (auto-criada por toda Festa)."""

from __future__ import annotations

import frappe
from frappe import _

AREA_PORTARIA_NOME = "Portaria"

# Roles com acesso global a operar a portaria (todas as festas).
ROLES_PORTARIA_GLOBAIS = {"System Manager", "Gestor de festas", "Portaria"}


def get_coordenador_portaria(festa: str) -> dict[str, str | None]:
	"""Retorna nome, email e telefone do coordenador da Portaria da festa.

	Resolve as três variações de `tipo_coord` (Responsavel / Associado / Outro)
	e retorna um dict simples mesmo quando algum campo está vazio — o chamador
	decide o que fazer com lacunas.
	"""
	nome_doc = f"{festa} - {AREA_PORTARIA_NOME}"
	portaria = frappe.db.get_value(
		"Area da Festa",
		nome_doc,
		[
			"tipo_coord",
			"responsavel_coord",
			"associado_coord",
			"nome_coord",
			"email_coord",
			"telefone_coord",
		],
		as_dict=True,
	)
	if not portaria:
		return {"nome": None, "email": None, "telefone": None}

	if portaria.tipo_coord == "Responsavel" and portaria.responsavel_coord:
		pessoa = frappe.db.get_value(
			"Responsavel",
			portaria.responsavel_coord,
			["nome_completo", "email", "telefone"],
			as_dict=True,
		)
		if pessoa:
			return {
				"nome": pessoa.get("nome_completo") or portaria.nome_coord,
				"email": pessoa.get("email") or portaria.email_coord,
				"telefone": pessoa.get("telefone") or portaria.telefone_coord,
			}

	if portaria.tipo_coord == "Associado" and portaria.associado_coord:
		pessoa = frappe.db.get_value(
			"Associado",
			portaria.associado_coord,
			["nome_completo", "email", "telefone"],
			as_dict=True,
		)
		if pessoa:
			return {
				"nome": pessoa.get("nome_completo") or portaria.nome_coord,
				"email": pessoa.get("email") or portaria.email_coord,
				"telefone": pessoa.get("telefone") or portaria.telefone_coord,
			}

	return {
		"nome": portaria.nome_coord,
		"email": portaria.email_coord,
		"telefone": portaria.telefone_coord,
	}


# ---------------------------------------------------------------------------
# ACL: quem pode operar a portaria
# ---------------------------------------------------------------------------


def _emails_da_area_portaria(festa: str) -> set[str]:
	"""Conjunto de e-mails autorizados pela Area Portaria desta festa.

	Inclui:
	- coordenador (via Responsavel.email / Associado.email / email_coord direto)
	- membros da equipe (mesmas três variações)
	Todos os e-mails são normalizados (lowercase, strip).
	"""
	nome_doc = f"{festa} - {AREA_PORTARIA_NOME}"
	area = frappe.db.get_value(
		"Area da Festa",
		nome_doc,
		[
			"tipo_coord",
			"responsavel_coord",
			"associado_coord",
			"email_coord",
		],
		as_dict=True,
	)
	if not area:
		return set()

	emails: set[str] = set()

	# Coordenador
	if area.tipo_coord == "Responsavel" and area.responsavel_coord:
		e = frappe.db.get_value("Responsavel", area.responsavel_coord, "email")
		if e:
			emails.add(e.strip().lower())
	elif area.tipo_coord == "Associado" and area.associado_coord:
		e = frappe.db.get_value("Associado", area.associado_coord, "email")
		if e:
			emails.add(e.strip().lower())
	if area.email_coord:
		emails.add(area.email_coord.strip().lower())

	# Equipe
	membros = frappe.get_all(
		"Membro Equipe Festa",
		filters={"parent": nome_doc, "parenttype": "Area da Festa"},
		fields=["tipo_pessoa", "associado", "responsavel", "email"],
	)
	for m in membros:
		if m.tipo_pessoa == "Responsavel" and m.responsavel:
			e = frappe.db.get_value("Responsavel", m.responsavel, "email")
			if e:
				emails.add(e.strip().lower())
		elif m.tipo_pessoa == "Associado" and m.associado:
			e = frappe.db.get_value("Associado", m.associado, "email")
			if e:
				emails.add(e.strip().lower())
		if m.email:
			emails.add(m.email.strip().lower())

	return {e for e in emails if e}


def user_pode_operar_portaria(user: str, festa_name: str | None = None) -> bool:
	"""True se o usuário tem permissão para operar a portaria.

	- True para roles globais (System Manager, Gestor de festas, Portaria).
	- Senão, exige `festa_name` e checa se o usuário (e-mail = User.name) é
	  coordenador ou membro da Área Portaria daquela festa.
	"""
	if not user or user == "Guest":
		return False
	roles = set(frappe.get_roles(user))
	if roles & ROLES_PORTARIA_GLOBAIS:
		return True
	if not festa_name:
		return False
	return user.strip().lower() in _emails_da_area_portaria(festa_name)


def ensure_user_pode_operar_portaria(festa_name: str | None = None) -> None:
	"""Lança PermissionError se o usuário atual não pode operar a portaria."""
	if not user_pode_operar_portaria(frappe.session.user, festa_name):
		frappe.throw(
			_("Você não tem permissão para operar a portaria desta festa."),
			frappe.PermissionError,
		)


def festas_que_user_pode_operar(user: str) -> list[str]:
	"""Lista de Festas ativas (Em andamento) que o usuário pode operar.

	- Roles globais → todas as festas em andamento.
	- Caso contrário, filtra por participação na Area Portaria.
	"""
	if not user or user == "Guest":
		return []

	from frappe.utils import today

	# Roles globais: todas as festas até data da festa.
	roles = set(frappe.get_roles(user))
	filtros_festa = [
		["status", "=", "Em andamento"],
		["status", "!=", "Realizada"],
		["data", ">=", today()],
	]
	todas = frappe.get_all(
		"Festa",
		filters=filtros_festa,
		fields=["name", "nome_festa", "data", "venda_na_portaria"],
		order_by="data asc",
	)
	if roles & ROLES_PORTARIA_GLOBAIS:
		return [_serializar_festa(f) for f in todas]

	user_norm = user.strip().lower()
	resultado = []
	for festa in todas:
		if user_norm in _emails_da_area_portaria(festa.name):
			resultado.append(_serializar_festa(festa))
	return resultado


def _serializar_festa(festa) -> dict:
	return {
		"name": festa.name,
		"nome_festa": festa.nome_festa or festa.name,
		"data": festa.data.isoformat() if festa.data else "",
		"venda_na_portaria": bool(festa.get("venda_na_portaria")),
	}
