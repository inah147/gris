"""Portal access helpers (role-based) under API namespace.

Exposed as gris.api.portal_access.* so pages and potential client code
can import a single stable module. Not whitelisted because these
helpers are server-side; whitelist only if you need to call from client.
"""

from __future__ import annotations

from collections.abc import Iterable

import frappe

# Sidebar logical structure (order preserved)
SIDEBAR_STRUCTURE: list[dict[str, object]] = [
	{"label": "Início", "path": "/inicio"},
	{
		"label": "Associados",
		"path": "/associados",
		"children": [
			{"label": "Visão Geral", "path": "/associados"},
			{"label": "Lista de Associados", "path": "/associados/lista"},
		],
	},
	{"label": "Transparência", "path": "/portal_transparencia"},
]

# Mapping: path -> allowed roles.
#   "All"    = qualquer usuário autenticado
#   "Public" = acessível inclusive para Guest (sem login)
PAGE_ROLES: dict[str, list[str]] = {
	"/inicio": ["All"],
	"/associados": ["Gestor de Associados", "Visualizador Associados"],
	"/associados/lista": ["Gestor de Associados", "Visualizador Associados"],
	"/associados/detalhe": ["Gestor de Associados", "Visualizador Associados"],
	"/portal_transparencia": ["Public"],  # totalmente público
}


def _get_user_roles(user: str | None = None) -> list[str]:
	user = user or frappe.session.user
	try:
		return frappe.get_roles(user)
	except Exception:  # pragma: no cover
		return []


def user_has_access(path: str, user: str | None = None, roles: Iterable[str] | None = None) -> bool:
	roles = list(roles) if roles else _get_user_roles(user)
	allowed = PAGE_ROLES.get(path)
	if "System Manager" in roles:
		return True
	if not allowed:
		# Página não mapeada => permitir (fail open) para não quebrar páginas novas
		return True
	if "Public" in allowed:
		return True  # disponível inclusive para Guest
	if "All" in allowed and frappe.session.user != "Guest":
		return True
	return any(r in allowed for r in roles)


@frappe.whitelist()
def _filter_items(items: list[dict[str, object]], roles: list[str]) -> list[dict[str, object]]:
	filtered: list[dict[str, object]] = []
	for item in items:
		path = item.get("path")  # type: ignore[arg-type]
		children = item.get("children") or []
		has_access = user_has_access(path, roles=roles) if path else False
		filtered_children = _filter_items(children, roles) if children else []
		if has_access or filtered_children:
			new_item = {k: v for k, v in item.items() if k != "children"}
			if filtered_children:
				new_item["children"] = filtered_children
			filtered.append(new_item)
	return filtered


@frappe.whitelist()
def build_sidebar(user: str | None = None) -> list[dict[str, object]]:
	roles = _get_user_roles(user)
	return _filter_items(SIDEBAR_STRUCTURE, roles)


@frappe.whitelist()
def enrich_context(context, current_path: str):
	# Sidebar items
	sidebar_items = build_sidebar()
	context.sidebar_items = sidebar_items
	context.access_denied = not user_has_access(current_path)

	# Descobrir filhos do grupo atual (para navegação móvel simplificada)
	current_children: list[dict[str, object]] = []
	for item in sidebar_items:
		path = item.get("path")  # type: ignore[arg-type]
		children = item.get("children") or []
		if children and isinstance(path, str) and current_path.startswith(path):
			current_children = children  # type: ignore[assignment]
			break
	context.current_group_children = current_children

	# Informações do usuário
	user = frappe.session.user
	if user and user != "Guest":
		try:
			full_name = frappe.utils.get_fullname(user)
		except Exception:  # pragma: no cover
			full_name = user
		context.user_display_name = full_name
		context.user_initial = (full_name[0] if full_name else user[0]).upper()
		roles = _get_user_roles(user)
		context.is_system_manager = "System Manager" in roles
	else:
		context.user_display_name = None
		context.user_initial = None
		context.is_system_manager = False

	return context
