"""Ferramentas MCP transversais (contexto, papéis e dados de apoio)."""

from __future__ import annotations

import frappe

from gris.api.mcp.registry import carregar_ferramentas, ferramenta, usuario_autorizado


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
