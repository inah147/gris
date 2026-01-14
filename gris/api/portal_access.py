"""Portal access helpers (role-based) under API namespace.

Exposed as gris.api.portal_access.* so pages and potential client code
can import a single stable module. Not whitelisted because these
helpers are server-side; whitelist only if you need to call from client.
"""

from __future__ import annotations

from collections.abc import Iterable

import frappe

from gris.api.portal_cache_utils import get_uel_cached

# Sidebar logical structure (order preserved)
SIDEBAR_STRUCTURE: list[dict[str, object]] = [
	{"label": "Início", "path": "/inicio"},
	{
		"label": "Associados",
		"path": "/associados",
		"children": [
			{"label": "Visão Geral", "path": "/associados/dashboard"},
			{"label": "Lista de Associados", "path": "/associados/lista"},
			{"label": "Importar Associados", "path": "/associados/importar"},
		],
	},
	{
		"label": "Novos Associados",
		"path": "/recepcao",
		"children": [
			{"label": "Visão Geral", "path": "/recepcao/visao_geral"},
			{"label": "Agenda de Visitas", "path": "/recepcao/agenda_visitas"},
			{"label": "Fila de espera", "path": "/recepcao/fila_espera"},
			{"label": "Respostas da Pesquisa", "path": "/recepcao/pesquisa_novos_respostas"},
		],
	},
	{
		"label": "Financeiro",
		"path": "/financeiro",
		"children": [
			{"label": "Visão Geral", "path": "/financeiro/dashboard"},
			{"label": "Contribuições Mensais", "path": "/financeiro/contribuicoes"},
			{"label": "Contas e Carteiras", "path": "/financeiro/contas"},
			{"label": "Extrato", "path": "/financeiro/extrato"},
			{"label": "Despesas Mensais", "path": "/financeiro/despesas"},
			{"label": "Relatórios", "path": "/financeiro/relatorios"},
			{"label": "Pareceres", "path": "/financeiro/pareceres"},
		],
	},
	{
		"label": "Calendário",
		"path": "/calendario",
		"children": [
			{"label": "Acessar Calendário", "path": "/calendario/visualizar"},
			{"label": "Importar Calendário", "path": "/calendario/importar"},
		],
	},
	{
		"label": "Painel do Responsável",
		"path": "/responsavel",
		"children": [
			{"label": "Meus dados", "path": "/responsavel/meus_dados"},
			{"label": "Beneficiários", "path": "/responsavel/beneficiarios"},
			{"label": "Pesquisa de Novos Associados", "path": "/responsavel/pesquisa_novos"},
		],
	},
	{"label": "Transparência", "path": "/portal_transparencia"},
]

# Mapping: path -> allowed roles.
#   "All"    = qualquer usuário autenticado
#   "Public" = acessível inclusive para Guest (sem login)
PAGE_ROLES: dict[str, list[str]] = {
	"/inicio": ["All"],
	"/403": ["All"],
	"/responsavel": ["Responsavel"],
	"/responsavel/meus_dados": ["Responsavel"],
	"/responsavel/beneficiarios": ["Responsavel"],
	"/responsavel/pesquisa_novos": ["Responsavel"],
	"/associados": [
		"Gestor de Associados",
		"Visualizador Associados",
		"Visualizador de Métricas de Associados",
	],
	"/associados/dashboard": [
		"Gestor de Associados",
		"Visualizador Associados",
		"Visualizador de Métricas de Associados",
	],
	"/associados/lista": ["Gestor de Associados", "Visualizador Associados"],
	"/associados/detalhe": ["Gestor de Associados", "Visualizador Associados"],
	"/associados/importar": ["Gestor de Associados"],
	"/recepcao": ["Recepcao"],
	"/recepcao/visao_geral": ["Recepcao"],
	"/recepcao/ficha_registro": ["Recepcao"],
	"/recepcao/agenda_visitas": ["Recepcao"],
	"/recepcao/fila_espera": ["Recepcao"],
	"/recepcao/pesquisa_novos_respostas": ["Recepcao"],
	"/financeiro": ["Visualizador Financeiro", "Gestor Financeiro"],
	"/financeiro/dashboard": ["Visualizador Financeiro", "Gestor Financeiro"],
	"/financeiro/contribuicoes": ["Gestor Contribuição Mensal", "Visualizador Contribuição Mensal"],
	"/financeiro/contas": ["Visualizador Financeiro", "Gestor Financeiro"],
	"/financeiro/extrato": ["Visualizador Financeiro", "Gestor Financeiro"],
	"/financeiro/despesas": ["Visualizador Financeiro", "Gestor Financeiro"],
	"/financeiro/relatorios": ["Visualizador Financeiro", "Gestor Financeiro"],
	"/financeiro/pareceres": ["Visualizador Financeiro", "Gestor Financeiro"],
	"/portal_transparencia": ["Public"],  # totalmente público
	"/calendario": ["Visualizador Calendario", "Gestor Calendario"],
	"/calendario/visualizar": ["Visualizador Calendario", "Gestor Calendario"],
	"/calendario/importar": ["Gestor Calendario"],
	"/calendario/simulacao_calendario": ["Gestor Calendario"],
}

# Páginas marcadas como "estritas": mesmo System Manager deve ter uma das roles listadas.
STRICT_PORTAL_PAGES = {
	"/financeiro/contribuicoes",
	"/responsavel",
	"/responsavel/meus_dados",
	"/responsavel/beneficiarios",
	"/responsavel/pesquisa_novos",
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
	if "System Manager" in roles and (path not in STRICT_PORTAL_PAGES):
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

	# Permissions for mobile bottom nav
	context.has_financeiro_access = user_has_access("/financeiro")
	context.has_associados_access = user_has_access("/associados")

	# Descobrir filhos do grupo atual (para navegação móvel simplificada)
	current_children: list[dict[str, object]] = []
	for item in sidebar_items:
		path = item.get("path")  # type: ignore[arg-type]
		children = item.get("children") or []
		if children and isinstance(path, str) and current_path.startswith(path):
			current_children = children  # type: ignore[assignment]
			break
	context.current_group_children = current_children

	# UEL Info (Logo and Title) - Centralized
	if not context.get("portal_logo"):
		uel_data = get_uel_cached()
		if uel_data:
			context.portal_logo = uel_data.get("logo")
			if not context.get("sidebar_title") and uel_data.get("nome_da_uel"):
				context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
	if not context.get("sidebar_title"):
		context.sidebar_title = "Portal"

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
