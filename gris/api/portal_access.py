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
			{"label": "Conciliação", "path": "/financeiro/conciliacao"},
			{"label": "Despesas Mensais", "path": "/financeiro/despesas"},
			{"label": "Previsão Orçamentária", "path": "/financeiro/previsao_orcamentaria"},
			{"label": "Relatórios", "path": "/financeiro/relatorios"},
			{"label": "Pareceres", "path": "/financeiro/pareceres"},
		],
	},
	{
		"label": "Calendário",
		"path": "/calendario",
		"children": [
			{"label": "Acessar Calendário", "path": "/calendario/visualizar"},
		],
	},
	{
		"label": "Gestão de Adultos",
		"path": "/gestao_adultos",
		"children": [
			{"label": "Minha Entrevista", "path": "/gestao_adultos/minha_entrevista"},
			{"label": "Entrevistas", "path": "/gestao_adultos/entrevista_competencias"},
		],
	},
	{
		"label": "Insígnias e Distintivos",
		"path": "/insignias",
		"children": [
			{"label": "Nova solicitação", "path": "/insignias/solicitar"},
			{"label": "Minhas solicitações", "path": "/insignias/minhas_solicitacoes"},
			{"label": "Compras", "path": "/insignias/compras"},
			{"label": "Catálogo", "path": "/insignias/catalogo"},
		],
	},
	{
		"label": "Projetos",
		"path": "/projetos",
		"children": [
			{"label": "Todos os projetos", "path": "/projetos/visao_geral"},
			{"label": "Meus projetos", "path": "/projetos/meus_projetos"},
			{"label": "Cadastrar novo projeto", "path": "/projetos/cadastrar_novo_projeto"},
		],
	},
	{
		"label": "Gestão de Tarefas",
		"path": "/gestao_tarefas",
		"children": [
			{"label": "Quadros", "path": "/gestao_tarefas"},
			{"label": "Minhas tarefas", "path": "/gestao_tarefas/tarefas"},
		],
	},
	{
		"label": "Festas",
		"path": "/festas",
		"children": [
			{"label": "Nova festa", "path": "/festas/nova_festa"},
			{"label": "Todas as festas", "path": "/festas/todas_festas"},
			{"label": "Portaria", "path": "/festas/portaria"},
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

PORTAL_MODULE_ICON_MAP: dict[str, str] = {
	"/associados": "users",
	"/calendario": "calendar-days",
	"/financeiro": "banknote",
	"/projetos": "folder-kanban",
	"/recepcao": "user-plus",
	"/gestao_adultos": "graduation-cap",
	"/insignias": "award",
	"/responsavel": "user",
	"/portal_transparencia": "file-text",
	"/festas": "party-popper",
	"/gestao_tarefas": "list-checks",
}

SIDEBAR_ICON_MAP: dict[str, str] = {
	"/inicio": "house",
	**PORTAL_MODULE_ICON_MAP,
	"/associados/dashboard": "layout-dashboard",
	"/associados/lista": "list",
	"/associados/importar": "upload",
	"/recepcao/visao_geral": "layout-dashboard",
	"/recepcao/agenda_visitas": "calendar-days",
	"/recepcao/fila_espera": "clock-3",
	"/recepcao/pesquisa_novos_respostas": "clipboard-list",
	"/financeiro/dashboard": "layout-dashboard",
	"/financeiro/contribuicoes": "wallet-cards",
	"/financeiro/contas": "landmark",
	"/financeiro/extrato": "receipt-text",
	"/financeiro/conciliacao": "arrow-left-right",
	"/financeiro/despesas": "receipt",
	"/financeiro/previsao_orcamentaria": "target",
	"/financeiro/relatorios": "clipboard-list",
	"/financeiro/pareceres": "file-search",
	"/calendario/visualizar": "calendar-days",
	"/gestao_adultos/minha_entrevista": "clipboard-list",
	"/gestao_adultos/entrevista_competencias": "list-check",
	"/insignias/solicitar": "file-plus",
	"/insignias/minhas_solicitacoes": "list",
	"/insignias/compras": "shopping-cart",
	"/insignias/catalogo": "award",
	"/projetos/visao_geral": "layout-dashboard",
	"/projetos/meus_projetos": "folder-search",
	"/projetos/cadastrar_novo_projeto": "upload",
	"/responsavel/meus_dados": "shield-user",
	"/responsavel/beneficiarios": "users",
	"/responsavel/pesquisa_novos": "search",
	"/festas/nova_festa": "calendar-plus",
	"/festas/todas_festas": "list",
	"/festas/festa": "party-popper",
	"/festas/portaria": "scan-qr-code",
	"/gestao_tarefas/tarefas": "square-check-big",
}

# Mapping: path -> allowed roles.
#   "All"    = qualquer usuário autenticado
#   "Public" = acessível inclusive para Guest (sem login)
PAGE_ROLES: dict[str, list[str]] = {
	"/inicio": ["All"],
	"/403": ["All"],
	"/gestao_tarefas": ["All"],
	"/gestao_tarefas/tarefas": ["All"],
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
	"/financeiro/conciliacao": ["Gestor Financeiro"],
	"/financeiro/despesas": ["Visualizador Financeiro", "Gestor Financeiro"],
	"/financeiro/previsao_orcamentaria": ["Visualizador Financeiro", "Gestor Financeiro"],
	"/financeiro/relatorios": ["Visualizador Financeiro", "Gestor Financeiro"],
	"/financeiro/pareceres": ["Visualizador Financeiro", "Gestor Financeiro", "Editor de Parecer"],
	"/portal_transparencia": ["Public"],  # totalmente público
	"/calendario": ["Visualizador Calendario", "Gestor Calendario"],
	"/calendario/visualizar": ["Visualizador Calendario", "Gestor Calendario"],
	"/calendario/importar": ["Gestor Calendario"],
	"/calendario/simulacao_calendario": ["Gestor Calendario"],
	"/gestao_adultos": ["Gestor de Adultos"],
	"/gestao_adultos/entrevista_competencias": ["Gestor de Adultos"],
	"/gestao_adultos/respostas_entrevista": ["Gestor de Adultos"],
	"/gestao_adultos/minha_entrevista": ["All"],
	"/insignias": ["Equipe de Metodos", "Gestor de Metodos", "Gestor Financeiro"],
	"/insignias/solicitar": ["Equipe de Metodos", "Gestor de Metodos"],
	"/insignias/minhas_solicitacoes": ["Equipe de Metodos", "Gestor de Metodos"],
	"/insignias/solicitacao": ["Equipe de Metodos", "Gestor de Metodos", "Gestor Financeiro"],
	"/insignias/compras": ["Gestor Financeiro"],
	"/insignias/catalogo": ["Gestor de Metodos"],
	"/projetos": ["Visualizador de projetos", "Editor de projetos"],
	"/projetos/visao_geral": ["Visualizador de projetos", "Editor de projetos"],
	"/projetos/meus_projetos": ["Visualizador de projetos", "Editor de projetos"],
	"/projetos/cadastrar_novo_projeto": ["Editor de projetos"],
	"/projetos/projeto": ["Visualizador de projetos", "Editor de projetos"],
	"/projetos/aprovacao_projeto": ["Visualizador de projetos", "Editor de projetos"],
	"/festas": ["Visualizador de festas", "Gestor de festas", "Portaria"],
	"/festas/nova_festa": ["Gestor de festas"],
	"/festas/todas_festas": ["Visualizador de festas", "Gestor de festas"],
	"/festas/festa": ["Visualizador de festas", "Gestor de festas"],
	"/festas/relatorio": ["Visualizador de festas", "Gestor de festas"],
	"/festas/portaria": ["Gestor de festas", "Portaria"],
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


def _get_responsavel_name(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None

	responsavel_name = frappe.db.get_value("Responsavel", {"email": user}, "name")
	if responsavel_name:
		return str(responsavel_name)

	associado_name = frappe.db.get_value("Associado", {"id_escoteiros": user}, "name")
	if not associado_name:
		return None

	associado_cpf_hash = frappe.db.get_value("Associado", associado_name, "cpf")
	if associado_cpf_hash and frappe.db.exists("Responsavel", associado_cpf_hash):
		return str(associado_cpf_hash)

	vinculado = frappe.db.get_value(
		"Responsavel Vinculo", {"beneficiario_associado": associado_name}, "responsavel"
	)
	return str(vinculado) if vinculado else None


def _has_beneficiario_em_integracao(user: str | None = None) -> bool:
	responsavel_name = _get_responsavel_name(user)
	if not responsavel_name:
		return False

	return bool(
		frappe.db.exists(
			"Responsavel Vinculo",
			{"responsavel": responsavel_name, "beneficiario_novo_associado": ["is", "set"]},
		)
	)


def _responsavel_has_associado_access(associado_name: str | None, user: str | None = None) -> bool:
	if not associado_name:
		return False

	responsavel_name = _get_responsavel_name(user)
	if not responsavel_name:
		return False

	return bool(
		frappe.db.exists(
			"Responsavel Vinculo",
			{"responsavel": responsavel_name, "beneficiario_associado": associado_name},
		)
	)


def _has_minha_entrevista(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False

	associado_name = frappe.db.get_value("Associado", {"id_escoteiros": user}, "name")
	if not associado_name:
		return False

	return bool(frappe.db.exists("Entrevista por Competencias", {"associado": associado_name}))


def user_has_access(path: str, user: str | None = None, roles: Iterable[str] | None = None) -> bool:
	roles = list(roles) if roles else _get_user_roles(user)
	allowed = PAGE_ROLES.get(path)
	if path == "/responsavel/pesquisa_novos" and not _has_beneficiario_em_integracao(user):
		return False
	if path == "/associados/detalhe" and "Responsavel" in roles:
		form_dict = getattr(frappe.local, "form_dict", {}) or {}
		associado_name = form_dict.get("name")
		if _responsavel_has_associado_access(associado_name, user):
			return True
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
def _filter_items(
	items: list[dict[str, object]],
	roles: list[str],
	has_minha_entrevista: bool,
) -> list[dict[str, object]]:
	filtered: list[dict[str, object]] = []
	for item in items:
		path = item.get("path")  # type: ignore[arg-type]
		if path == "/gestao_adultos/minha_entrevista" and not has_minha_entrevista:
			continue
		children = item.get("children") or []
		has_access = user_has_access(path, roles=roles) if path else False
		filtered_children = _filter_items(children, roles, has_minha_entrevista) if children else []
		if has_access or filtered_children:
			new_item = {k: v for k, v in item.items() if k != "children"}
			if filtered_children:
				new_item["children"] = filtered_children
			filtered.append(new_item)
	return filtered


def _normalize_path(path: str | None) -> str:
	if not path:
		return "/"
	normalized = path if path.startswith("/") else f"/{path}"
	if len(normalized) > 1:
		normalized = normalized.rstrip("/")
	return normalized or "/"


def _is_current_path(target_path: str, current_path: str) -> bool:
	target = _normalize_path(target_path)
	current = _normalize_path(current_path)

	if target == "/inicio":
		return current == "/" or current == "/inicio" or current.startswith("/inicio/")

	if current == target:
		return True

	return current.startswith(f"{target}/")


def _lucide_icon_markup(icon_name: str | None) -> str | None:
	if not icon_name:
		return None

	return (
		f'<svg class="ds-lucide" aria-hidden="true" focusable="false" viewBox="0 0 24 24">'
		f'<use href="/assets/gris/design_system/icons/lucide/sprite.svg#{icon_name}" /></svg>'
	)


def _to_design_system_sidebar_items(
	items: list[dict[str, object]],
	current_path: str,
) -> list[dict[str, object]]:
	menu: list[dict[str, object]] = []

	for item in items:
		label_value = item.get("label")
		path_value = item.get("path")
		children_value = item.get("children")

		label = str(label_value).strip() if label_value else ""
		path = _normalize_path(str(path_value)) if path_value else ""
		children = children_value if isinstance(children_value, list) else []
		icon = _lucide_icon_markup(SIDEBAR_ICON_MAP.get(path)) if path else None

		if not label:
			continue

		if children:
			submenu_items = _to_design_system_sidebar_items(children, current_path)
			if not submenu_items:
				continue

			submenu: dict[str, object] = {
				"type": "submenu",
				"label": label,
				"open": bool(path and _is_current_path(path, current_path)),
				"items": submenu_items,
			}

			if icon:
				submenu["icon"] = icon

			if path and _is_current_path(path, current_path):
				submenu["attrs"] = {"aria-current": "page"}

			menu.append(submenu)
			continue

		if not path:
			continue

		menu.append(
			{
				"type": "item",
				"label": label,
				"icon": icon,
				"url": path,
				"current": _is_current_path(path, current_path),
			}
		)

	return menu


def _to_portal_breadcrumb_items(
	items: list[dict[str, object]],
	current_path: str | None,
) -> list[dict[str, str | None]]:
	target_path = _normalize_path(current_path)
	exact_match: list[dict[str, str | None]] | None = None
	prefix_match: list[dict[str, str | None]] = []

	def _walk(
		nodes: list[dict[str, object]],
		trail: list[dict[str, str | None]],
	) -> bool:
		nonlocal exact_match, prefix_match

		for item in nodes:
			children_value = item.get("children")
			children = children_value if isinstance(children_value, list) else []

			label_value = item.get("label")
			label = str(label_value).strip() if label_value else ""

			path_value = item.get("path")
			path = _normalize_path(str(path_value)) if path_value else None

			next_trail = trail
			if label and path:
				crumb = {"label": label, "url": path}
				next_trail = [*trail, crumb]

				if path == target_path:
					exact_match = next_trail
					return True

				if _is_current_path(path, target_path) and len(next_trail) > len(prefix_match):
					prefix_match = next_trail

			if children and _walk(children, next_trail):
				return True

		return False

	_walk(items, [])
	match = exact_match or prefix_match
	if not match:
		return []

	breadcrumbs = [dict(item) for item in match]
	breadcrumbs[-1]["url"] = None
	return breadcrumbs


@frappe.whitelist()
def build_sidebar(user: str | None = None) -> list[dict[str, object]]:
	roles = _get_user_roles(user)
	has_minha_entrevista = _has_minha_entrevista(user)
	return _filter_items(SIDEBAR_STRUCTURE, roles, has_minha_entrevista)


@frappe.whitelist()
def enrich_context(context, current_path: str):
	# Sidebar items
	sidebar_items = build_sidebar()
	breadcrumb_path = context.get("active_link") or current_path
	context.sidebar_items = sidebar_items
	context.sidebar_menu_ds = _to_design_system_sidebar_items(sidebar_items, current_path)
	context.sidebar_icons = SIDEBAR_ICON_MAP
	context.portal_breadcrumbs = _to_portal_breadcrumb_items(sidebar_items, breadcrumb_path)
	context.access_denied = not user_has_access(current_path)

	# Permissions for mobile bottom nav
	context.has_financeiro_access = user_has_access("/financeiro")
	context.has_associados_access = user_has_access("/associados")
	context.has_calendario_access = user_has_access("/calendario")

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
		user_data = frappe.db.get_value("User", user, ["email", "user_image"], as_dict=True) or {}
		try:
			full_name = frappe.utils.get_fullname(user)
		except Exception:  # pragma: no cover
			full_name = user
		context.user_display_name = full_name
		context.user_email = user_data.get("email") or user
		context.user_avatar_url = user_data.get("user_image")
		context.user_initial = (full_name[0] if full_name else user[0]).upper()
		roles = _get_user_roles(user)
		context.is_system_manager = "System Manager" in roles
		context.is_guest_user = False
	else:
		context.user_display_name = None
		context.user_email = None
		context.user_avatar_url = None
		context.user_initial = None
		context.is_system_manager = False
		context.is_guest_user = True

	return context


def pode_conciliar(*doctypes: str) -> bool:
	"""True quando o usuário pode criar E editar todos os DocTypes informados.

	Usado pelas páginas de importação de extrato do /financeiro apenas para
	mostrar ou esconder as ações de upload; quem faz valer a permissão é o
	método de servidor que processa o arquivo.
	"""
	for doctype in doctypes:
		pode_criar = frappe.has_permission(doctype, ptype="create")
		pode_editar = frappe.has_permission(doctype, ptype="write")
		if not (pode_criar and pode_editar):
			return False
	return True
