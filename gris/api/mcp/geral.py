"""Ferramentas MCP transversais (contexto, papéis e dados de apoio)."""

from __future__ import annotations

from typing import Any

import frappe

from gris.api.mcp.registry import (
	ErroDeFerramenta,
	carregar_ferramentas,
	ferramenta,
	normalizar_limite,
	usuario_autorizado,
)


@ferramenta(
	nome="quem_sou_eu",
	titulo="Contexto do usuário conectado",
	descricao=(
		"Identifica o usuário autenticado no GRIS, seus papéis e quais ferramentas ele pode "
		"usar. Chame esta ferramenta quando uma operação for negada por permissão."
	),
	parametros={},
)
def quem_sou_eu() -> dict:
	papeis = sorted(set(frappe.get_roles(frappe.session.user)))
	disponiveis, bloqueadas = [], []
	for ferramenta_obj in sorted(carregar_ferramentas().values(), key=lambda f: f.nome):
		destino = disponiveis if usuario_autorizado(ferramenta_obj, set(papeis)) else bloqueadas
		destino.append(ferramenta_obj.nome)

	nome_completo = frappe.db.get_value("User", frappe.session.user, "full_name")

	return {
		"usuario": frappe.session.user,
		"nome_completo": nome_completo,
		"papeis": papeis,
		"ferramentas_disponiveis": disponiveis,
		"ferramentas_bloqueadas": bloqueadas,
		"site": frappe.local.site,
	}


@ferramenta(
	nome="listar_unidades_organizacionais",
	titulo="Listar unidades organizacionais",
	descricao=(
		"Lista as unidades organizacionais (campo 'area' do associado) com sua hierarquia. "
		"Use para descobrir valores válidos ao filtrar ou atualizar a área de um associado."
	),
	parametros={},
	roles=("Gestor de Associados", "Visualizador Associados", "Gestor da UEL"),
)
def listar_unidades_organizacionais() -> dict:
	unidades = frappe.get_all(
		"Unidade Organizacional",
		fields=["name", "area", "responde_para", "descrição as descricao"],
		order_by="area asc",
	)
	return {"unidades": unidades, "total": len(unidades)}


@ferramenta(
	nome="listar_usuarios",
	titulo="Listar usuários e papéis",
	descricao=(
		"Lista usuários do sistema com seus papéis (roles). Use 'busca' para procurar por "
		"nome ou e-mail e 'papel' para descobrir quem tem um papel específico — por exemplo, "
		"para responder 'quem pode fazer X' quando X é uma ação restrita por role."
	),
	parametros={
		"busca": {"type": "string", "description": "Texto livre: nome completo ou e-mail."},
		"papel": {
			"type": "string",
			"description": "Nome exato de um Role (veja 'listar_papeis'). Filtra só usuários com esse papel.",
		},
		"apenas_ativos": {
			"type": "boolean",
			"default": True,
			"description": "Considerar apenas usuários habilitados (enabled=1).",
		},
		"limite": {
			"type": "integer",
			"default": 25,
			"minimum": 1,
			"maximum": 100,
			"description": "Quantidade de registros por página (máx. 100).",
		},
		"inicio": {
			"type": "integer",
			"default": 0,
			"minimum": 0,
			"description": "Deslocamento para paginação.",
		},
	},
	roles=("System Manager",),
)
def listar_usuarios(
	busca: str | None = None,
	papel: str | None = None,
	apenas_ativos: bool = True,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict[str, Any] = {"user_type": "System User"}
	if apenas_ativos:
		filtros["enabled"] = 1

	if papel:
		if not frappe.db.exists("Role", papel):
			raise ErroDeFerramenta(
				"ARGUMENTO_INVALIDO",
				f"O papel '{papel}' não existe. Use 'listar_papeis' para ver os nomes válidos.",
			)
		usuarios_com_papel = frappe.get_all(
			"Has Role",
			filters={"role": papel, "parenttype": "User"},
			pluck="parent",
		)
		if not usuarios_com_papel:
			return {
				"usuarios": [],
				"paginacao": {
					"inicio": max(0, int(inicio or 0)),
					"limite": normalizar_limite(limite),
					"retornados": 0,
					"total_com_filtros": 0,
				},
			}
		filtros["name"] = ["in", usuarios_com_papel]

	or_filters = None
	if busca:
		termo = f"%{busca}%"
		or_filters = {
			"full_name": ["like", termo],
			"name": ["like", termo],
		}

	registros = frappe.get_all(
		"User",
		filters=filtros,
		or_filters=or_filters,
		fields=["name", "full_name", "enabled", "last_login"],
		order_by="full_name asc",
		limit_page_length=normalizar_limite(limite),
		limit_start=max(0, int(inicio or 0)),
	)
	total = frappe.db.count("User", filtros) if not or_filters else None

	nomes = [registro["name"] for registro in registros]
	papeis_por_usuario: dict[str, list[str]] = {nome: [] for nome in nomes}
	if nomes:
		linhas_papel = frappe.get_all(
			"Has Role",
			filters={"parenttype": "User", "parent": ["in", nomes]},
			fields=["parent", "role"],
		)
		for linha in linhas_papel:
			papeis_por_usuario.setdefault(linha["parent"], []).append(linha["role"])

	usuarios = [
		{
			"usuario": registro["name"],
			"nome_completo": registro["full_name"],
			"ativo": bool(registro["enabled"]),
			"ultimo_login": registro["last_login"],
			"papeis": sorted(papeis_por_usuario.get(registro["name"], [])),
		}
		for registro in registros
	]

	return {
		"usuarios": usuarios,
		"paginacao": {
			"inicio": max(0, int(inicio or 0)),
			"limite": normalizar_limite(limite),
			"retornados": len(usuarios),
			"total_com_filtros": total,
		},
	}


@ferramenta(
	nome="listar_papeis",
	titulo="Listar papéis (roles)",
	descricao=(
		"Lista os papéis (roles) cadastrados no sistema. Use antes de 'listar_usuarios' com "
		"o parâmetro 'papel' para descobrir o nome exato de um papel."
	),
	parametros={
		"busca": {"type": "string", "description": "Texto livre para filtrar pelo nome do papel."},
	},
	roles=("System Manager",),
)
def listar_papeis(busca: str | None = None) -> dict:
	filtros: dict[str, Any] = {"disabled": 0}
	if busca:
		filtros["name"] = ["like", f"%{busca}%"]

	papeis = frappe.get_all(
		"Role",
		filters=filtros,
		fields=["name", "desk_access"],
		order_by="name asc",
		limit_page_length=0,
	)
	return {"papeis": papeis, "total": len(papeis)}
