"""Regras de acesso do módulo de Compras.

As compras são divididas em três áreas, cada uma com o seu gestor:
- Programa Educativo (insígnias e distintivos): Gestor de Metodos;
- Manutenção: Gestor de Manutencao;
- Administrativo: Gestor Administrativo.

Qualquer pessoa do grupo (usuário logado) solicita em qualquer área. O catálogo de
Manutenção e Administrativo aceita itens novos de qualquer pessoa, para quem não
achou o que precisa; o de Programa Educativo só o Gestor de Metodos mantém. Comprar,
registrar o recebimento e editar/inativar itens é do gestor da área. O Gestor
Financeiro acompanha a fila de todas as áreas, sem agir sobre ela.
"""

from __future__ import annotations

import frappe
from frappe import _

AREA_MANUTENCAO = "Manutenção"
AREA_PROGRAMA_EDUCATIVO = "Programa Educativo"
AREA_ADMINISTRATIVO = "Administrativo"

# Ordem de exibição no portal.
AREAS: dict[str, dict] = {
	AREA_PROGRAMA_EDUCATIVO: {
		"slug": "programa_educativo",
		"gestores": ("Gestor de Metodos",),
		"cadastro_aberto": False,
	},
	AREA_MANUTENCAO: {
		"slug": "manutencao",
		"gestores": ("Gestor de Manutencao",),
		"cadastro_aberto": True,
	},
	AREA_ADMINISTRATIVO: {
		"slug": "administrativo",
		"gestores": ("Gestor Administrativo",),
		"cadastro_aberto": True,
	},
}

AREAS_VALIDAS = tuple(AREAS)
AREA_POR_SLUG = {meta["slug"]: area for area, meta in AREAS.items()}

ROLES_GESTORES = tuple(sorted({role for meta in AREAS.values() for role in meta["gestores"]}))
ROLES_LEITURA_GERAL = ("Gestor Financeiro",)
ROLE_ADMIN = "System Manager"


def _roles(user: str | None = None) -> set[str]:
	return set(frappe.get_roles(user or frappe.session.user))


def _usuario(user: str | None = None) -> str:
	return user or frappe.session.user


def is_admin(user: str | None = None) -> bool:
	return ROLE_ADMIN in _roles(user)


def slug_da_area(area: str | None) -> str | None:
	meta = AREAS.get(area or "")
	return meta["slug"] if meta else None


def gestores_da_area(area: str | None) -> tuple[str, ...]:
	meta = AREAS.get(area or "")
	return meta["gestores"] if meta else ()


def autenticado(user: str | None = None) -> bool:
	return _usuario(user) != "Guest"


def e_gestor_da_area(area: str | None, user: str | None = None) -> bool:
	roles = _roles(user)
	return bool(roles & set(gestores_da_area(area))) or ROLE_ADMIN in roles


def e_gestor_de_alguma_area(user: str | None = None) -> bool:
	roles = _roles(user)
	return bool(roles & set(ROLES_GESTORES)) or ROLE_ADMIN in roles


def pode_solicitar(user: str | None = None) -> bool:
	"""Qualquer pessoa logada solicita, em qualquer área."""
	return autenticado(user)


def pode_comprar(area: str | None, user: str | None = None) -> bool:
	"""Comprar e registrar o recebimento é do gestor da área."""
	return area in AREAS and e_gestor_da_area(area, user)


def pode_ver_fila(area: str | None, user: str | None = None) -> bool:
	"""A fila da área: o gestor dela e, só para acompanhar, o financeiro."""
	if area not in AREAS:
		return False
	return e_gestor_da_area(area, user) or bool(_roles(user) & set(ROLES_LEITURA_GERAL))


def pode_ver_alguma_fila(user: str | None = None) -> bool:
	return any(pode_ver_fila(area, user) for area in AREAS)


def pode_cadastrar_item(area: str | None, user: str | None = None) -> bool:
	"""Item novo no catálogo: aberto a todos em Manutenção/Administrativo.

	Insígnias e distintivos seguem o Programa Educativo, e só a gestão de métodos sabe
	quais existem e como se chamam: lá o cadastro é dela.
	"""
	meta = AREAS.get(area or "")
	if not meta or not autenticado(user):
		return False
	return meta["cadastro_aberto"] or e_gestor_da_area(area, user)


def pode_editar_item(item, user: str | None = None) -> bool:
	"""Editar preço ou inativar: o gestor da área; fora do PE, também quem cadastrou."""
	area = item.get("area") if isinstance(item, dict) else item.area
	dono = item.get("owner") if isinstance(item, dict) else item.owner
	if e_gestor_da_area(area, user):
		return True
	meta = AREAS.get(area or "")
	return bool(meta and meta["cadastro_aberto"] and dono and dono == _usuario(user))


def areas_para(acao, user: str | None = None) -> list[str]:
	"""Áreas, na ordem de exibição, em que `acao(area, user)` é permitida."""
	return [area for area in AREAS if acao(area, user)]


def garantir_autenticado(user: str | None = None) -> None:
	if not autenticado(user):
		frappe.throw(_("Faça login para usar o módulo de compras."), frappe.PermissionError)


def garantir_area_valida(area: str | None) -> str:
	if area not in AREAS:
		frappe.throw(_("Selecione uma área válida: Manutenção, Programa Educativo ou Administrativo."))
	return area


def garantir_comprador(area: str | None, user: str | None = None) -> None:
	if not pode_comprar(area, user):
		frappe.throw(
			f"Apenas o responsável pelas compras de {area or 'desta área'} pode registrar a compra "
			"e o recebimento.",
			frappe.PermissionError,
		)


def garantir_cadastro_item(area: str | None, user: str | None = None) -> None:
	if not pode_cadastrar_item(area, user):
		frappe.throw(
			_("Apenas a gestão de métodos pode cadastrar insígnias e distintivos no catálogo."),
			frappe.PermissionError,
		)


def garantir_edicao_item(item, user: str | None = None) -> None:
	if not pode_editar_item(item, user):
		frappe.throw(
			_("Apenas o gestor da área pode alterar este item do catálogo."),
			frappe.PermissionError,
		)


def pode_ver_solicitacao(doc, user: str | None = None) -> bool:
	user = _usuario(user)
	return doc.solicitante == user or pode_ver_fila(doc.area, user)


def garantir_acesso_solicitacao(doc, user: str | None = None) -> None:
	if not pode_ver_solicitacao(doc, user):
		frappe.throw(_("Você não tem acesso a esta solicitação."), frappe.PermissionError)


def pode_cancelar(doc, user: str | None = None) -> bool:
	"""O próprio solicitante ou o gestor da área cancelam, enquanto não houver compra."""
	from gris.gris.doctype.solicitacao_de_compra.solicitacao_de_compra import (
		STATUS_COMPRADA,
		STATUS_SOLICITADA,
	)

	user = _usuario(user)
	if doc.status not in {STATUS_SOLICITADA, STATUS_COMPRADA}:
		return False

	if doc.status == STATUS_COMPRADA:
		# Depois da compra, só o gestor da área desfaz (ex.: pedido cancelado no fornecedor).
		return e_gestor_da_area(doc.area, user)

	return doc.solicitante == user or e_gestor_da_area(doc.area, user)


def pode_registrar_entrega(doc, user: str | None = None) -> bool:
	"""Entrega é confirmada por quem pediu ou pelo gestor da área."""
	from gris.gris.doctype.solicitacao_de_compra.solicitacao_de_compra import STATUS_RECEBIDA

	user = _usuario(user)
	if doc.status != STATUS_RECEBIDA:
		return False
	return doc.solicitante == user or e_gestor_da_area(doc.area, user)
