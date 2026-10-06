"""Quem usa o portal de acessos, quem o administra e quem decide cada etapa.

Todo usuário logado vê os próprios acessos e pode pedir novos — inclusive os
responsáveis, que não têm cadastro de Associado. O que depende do cadastro é o
id@escoteiros: ferramentas e drives são sempre concedidos nessa conta, então quem não a
tem só consegue pedir papéis do Gris (ver `catalogo._motivo_para_nao_solicitar`).
"""

from __future__ import annotations

import frappe
from frappe import _

from gris.api.acessos.constantes import (
	ROLE_GESTOR,
	ROLE_SYSTEM_MANAGER,
	SETTINGS_DOCTYPE,
	STATUS_EM_APROVACAO,
)

CAMPOS_DO_ASSOCIADO = ["name", "nome_completo", "id_escoteiros", "status_no_grupo", "categoria"]


def _usuario(user: str | None) -> str:
	return (user or frappe.session.user or "").strip()


def _papeis(user: str) -> set[str]:
	return set(frappe.get_roles(user))


def associado_do_usuario(user: str | None = None) -> frappe._dict | None:
	"""Cadastro de Associado do usuário. O login do associado é o id@escoteiros."""
	user = _usuario(user)
	if not user or user == "Guest":
		return None
	return frappe.db.get_value("Associado", {"id_escoteiros": user}, CAMPOS_DO_ASSOCIADO, as_dict=True)


def eh_gestor(user: str | None = None) -> bool:
	user = _usuario(user)
	if not user or user == "Guest":
		return False
	return bool(_papeis(user) & {ROLE_GESTOR, ROLE_SYSTEM_MANAGER})


def eh_system_manager(user: str | None = None) -> bool:
	user = _usuario(user)
	return bool(user) and ROLE_SYSTEM_MANAGER in _papeis(user)


def pode_usar_portal(user: str | None = None) -> bool:
	user = _usuario(user)
	return bool(user) and user != "Guest"


def papel_aprovador_padrao() -> str:
	"""Quem aprova um acesso que não teve o fluxo alterado: por padrão, a gestão de acessos."""
	return frappe.db.get_single_value(SETTINGS_DOCTYPE, "papel_aprovador_padrao") or ROLE_GESTOR


def pode_decidir(solicitacao, user: str | None = None) -> bool:
	"""Se ``user`` pode aprovar ou recusar a etapa corrente da solicitação.

	Decide quem tem o papel da etapa — por padrão, o Gestor de Acessos (ver
	`papel_aprovador_padrao`). Quando a gestão troca o papel de uma etapa, a troca vale de
	verdade: o gestor deixa de decidir aquela etapa. O System Manager decide qualquer
	etapa, para um pedido não ficar preso quando ninguém mais tem o papel. E quem pediu
	nunca decide o próprio pedido.
	"""
	user = _usuario(user)
	if not user or user == "Guest":
		return False
	if solicitacao.status != STATUS_EM_APROVACAO or solicitacao.solicitante == user:
		return False

	etapa = solicitacao.etapa_corrente()
	if not etapa:
		return False

	papeis = _papeis(user)
	return ROLE_SYSTEM_MANAGER in papeis or etapa.papel_aprovador in papeis


def garantir_portal(user: str | None = None) -> None:
	if not pode_usar_portal(user):
		frappe.throw(_("Entre no Gris para ver e pedir acessos."), frappe.PermissionError)


def garantir_gestor(user: str | None = None) -> None:
	if not eh_gestor(user):
		frappe.throw(_("Apenas a gestão de acessos pode fazer isso."), frappe.PermissionError)


def garantir_decisao(solicitacao, user: str | None = None) -> None:
	if not pode_decidir(solicitacao, user):
		frappe.throw(_("Você não pode decidir esta etapa da solicitação."), frappe.PermissionError)
