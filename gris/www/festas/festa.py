from __future__ import annotations

import frappe
from frappe.utils import flt, format_date

from gris.api.festas import totais_payload
from gris.api.festas.convites import build_dashboard as build_convites_dashboard
from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached
from gris.festas.utils.unidades import UNIDADES

no_cache = 1

ALLOWED_ROLES = {"Gestor de festas", "System Manager"}


def _format_time(value) -> str:
	text = str(value) if value else ""
	return text[:5] if len(text) >= 5 else text


def _serializar_orcamento_linhas(rows, chave: str, labels: dict[str, str]) -> list[dict]:
	resultado = []
	for row in rows or []:
		ref = row.get(chave) or ""
		resultado.append(
			{
				"name": ref,
				"label": labels.get(ref, ref) or "—",
				"esperado_min": flt(row.esperado_min),
				"esperado_intermediario": flt(row.esperado_intermediario),
				"esperado_max": flt(row.esperado_max),
				"realizado_min": flt(row.realizado_min),
				"realizado_intermediario": flt(row.realizado_intermediario),
				"realizado_max": flt(row.realizado_max),
			}
		)
	return resultado


def _hydrate_membro(row) -> dict:
	return {
		"name": row.name,
		"tipo_pessoa": row.tipo_pessoa or "Outro",
		"associado": row.associado or "",
		"responsavel": row.responsavel or "",
		"nome": row.nome or "",
		"email": row.email or "",
		"telefone": row.telefone or "",
		"funcao": row.funcao or "",
	}


def _hydrate_area(doc) -> dict:
	return {
		"name": doc.name,
		"nome_area": doc.nome_area or "",
		"descricao": doc.descricao or "",
		"tipo_coord": doc.tipo_coord or "Outro",
		"responsavel_coord": doc.responsavel_coord or "",
		"associado_coord": doc.associado_coord or "",
		"nome_coord": doc.nome_coord or "",
		"email_coord": doc.email_coord or "",
		"telefone_coord": doc.telefone_coord or "",
		"equipe": [_hydrate_membro(m) for m in (doc.equipe or [])],
	}


def _hydrate_barraca(doc) -> dict:
	nome_area = ""
	if doc.area:
		nome_area = frappe.db.get_value("Area da Festa", doc.area, "nome_area") or ""
	return {
		"name": doc.name,
		"nome_barraca": doc.nome_barraca or "",
		"descricao": doc.descricao or "",
		"area": doc.area or "",
		"nome_area": nome_area,
		"tipo_coord": doc.tipo_coord or "Outro",
		"responsavel_coord": doc.responsavel_coord or "",
		"associado_coord": doc.associado_coord or "",
		"nome_coord": doc.nome_coord or "",
		"email_coord": doc.email_coord or "",
		"telefone_coord": doc.telefone_coord or "",
		"valor_arrecadado_realizado_real": flt(doc.valor_arrecadado_realizado_real),
		"equipe": [_hydrate_membro(m) for m in (doc.equipe or [])],
	}


def _hydrate_produto(doc) -> dict:
	nome_barraca = ""
	if doc.barraca:
		nome_barraca = frappe.db.get_value("Barraca da Festa", doc.barraca, "nome_barraca") or ""
	return {
		"name": doc.name,
		"nome_produto": doc.nome_produto or "",
		"barraca": doc.barraca or "",
		"nome_barraca": nome_barraca,
		"faz_parte_convite": bool(doc.faz_parte_convite),
		"preco_custo": flt(doc.preco_custo),
		"preco_venda": flt(doc.preco_venda),
		"margem_lucro": flt(doc.margem_lucro),
		"expectativa_venda_por_pessoa": flt(doc.expectativa_venda_por_pessoa),
		"qtd_min": flt(doc.qtd_min),
		"custo_total_min": flt(doc.custo_total_min),
		"receita_total_min": flt(doc.receita_total_min),
		"superavit_min": flt(doc.superavit_min),
		"qtd_intermediario": flt(doc.qtd_intermediario),
		"custo_total_intermediario": flt(doc.custo_total_intermediario),
		"receita_total_intermediario": flt(doc.receita_total_intermediario),
		"superavit_intermediario": flt(doc.superavit_intermediario),
		"qtd_max": flt(doc.qtd_max),
		"custo_total_max": flt(doc.custo_total_max),
		"receita_total_max": flt(doc.receita_total_max),
		"superavit_max": flt(doc.superavit_max),
		"qtd_realizada_vendas": flt(doc.qtd_realizada_vendas),
		"valor_total_arrecadado": flt(doc.valor_total_arrecadado),
	}


def _hydrate_cotacao_compra(row) -> dict:
	return {
		"fornecedor": row.fornecedor or "",
		"valor": flt(row.valor),
		"quantidade": flt(row.quantidade),
		"unidade_medida": row.unidade_medida or "unidade",
		"escolhida": bool(row.escolhida),
		"doacao": bool(row.doacao),
	}


def _hydrate_uso_compra(row, produto_labels: dict[str, str]) -> dict:
	return {
		"produto": row.produto or "",
		"produto_label": produto_labels.get(row.produto) or row.produto or "",
		"quantidade_usada": flt(row.quantidade_usada),
		"unidade_medida_uso": row.unidade_medida_uso or "unidade",
		"fracao_item": flt(row.fracao_item),
		"valor_uso": flt(row.valor_uso),
	}


def _hydrate_compra(doc, produto_labels: dict[str, str]) -> dict:
	nome_area = ""
	if doc.area:
		nome_area = frappe.db.get_value("Area da Festa", doc.area, "nome_area") or ""
	return {
		"name": doc.name,
		"festa": doc.festa or "",
		"area": doc.area or "",
		"nome_area": nome_area,
		"nome_item": doc.nome_item or "",
		"previsto": bool(doc.previsto),
		"varia_com_publico": bool(doc.varia_com_publico),
		"usado_em_produtos": bool(doc.usado_em_produtos),
		"unidade_compra": doc.unidade_compra or "unidade",
		"quantidade_compra": flt(doc.quantidade_compra),
		"quantidade_compra_final": flt(doc.quantidade_compra_final),
		"cotacao_escolhida_valor": flt(doc.cotacao_escolhida_valor),
		"valor_total_compra": flt(doc.valor_total_compra),
		# Realizado
		"valor_individual_realizado": flt(doc.valor_individual_realizado),
		"unidade_medida_realizado": doc.unidade_medida_realizado or "unidade",
		"quantidade_realizada": flt(doc.quantidade_realizada),
		"valor_total_realizado": flt(doc.valor_total_realizado),
		"fornecedor_realizado": doc.fornecedor_realizado or "",
		"observacoes_realizado": doc.observacoes_realizado or "",
		# Cenários de compra
		"qtd_sugerida_min": flt(doc.qtd_sugerida_min),
		"valor_total_min": flt(doc.valor_total_min),
		"qtd_sobra_individual_min": flt(doc.qtd_sobra_individual_min),
		"valor_sobra_min": flt(doc.valor_sobra_min),
		"qtd_sugerida_intermediario": flt(doc.qtd_sugerida_intermediario),
		"valor_total_intermediario": flt(doc.valor_total_intermediario),
		"qtd_sobra_individual_intermediario": flt(doc.qtd_sobra_individual_intermediario),
		"valor_sobra_intermediario": flt(doc.valor_sobra_intermediario),
		"qtd_sugerida_max": flt(doc.qtd_sugerida_max),
		"valor_total_max": flt(doc.valor_total_max),
		"qtd_sobra_individual_max": flt(doc.qtd_sobra_individual_max),
		"valor_sobra_max": flt(doc.valor_sobra_max),
		"cotacoes": [_hydrate_cotacao_compra(c) for c in (doc.cotacoes or [])],
		"usos_em_produto": [
			_hydrate_uso_compra(uso, produto_labels) for uso in (doc.usos_em_produto or [])
		],
	}


def _hydrate_cotacao_contratacao(row) -> dict:
	return {
		"fornecedor": row.fornecedor or "",
		"valor": flt(row.valor),
		"escolhida": bool(row.escolhida),
	}


def _hydrate_contratacao(doc) -> dict:
	nome_area = ""
	if doc.area:
		nome_area = frappe.db.get_value("Area da Festa", doc.area, "nome_area") or ""
	return {
		"name": doc.name,
		"festa": doc.festa or "",
		"area": doc.area or "",
		"nome_area": nome_area,
		"nome_item": doc.nome_item or "",
		"previsto": bool(doc.previsto),
		"valor_total_contratacao": flt(doc.valor_total_contratacao),
		"valor_total_realizado": flt(doc.valor_total_realizado),
		"fornecedor_realizado": doc.fornecedor_realizado or "",
		"observacoes_realizado": doc.observacoes_realizado or "",
		"cotacoes": [_hydrate_cotacao_contratacao(c) for c in (doc.cotacoes or [])],
	}


def _select_items_associados() -> list[dict]:
	registros = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo"},
		fields=["name", "nome_completo", "email", "telefone"],
		order_by="nome_completo asc",
	)
	return [
		{
			"label": r.nome_completo or r.name,
			"value": r.name,
			"type": "item",
			"attrs": {"data-email": r.email or "", "data-telefone": r.telefone or ""},
		}
		for r in registros
	]


def _select_items_responsaveis() -> list[dict]:
	registros = frappe.get_all(
		"Responsavel",
		fields=["name", "nome_completo", "email", "celular"],
		order_by="nome_completo asc",
	)
	return [
		{
			"label": r.nome_completo or r.name,
			"value": r.name,
			"type": "item",
			"attrs": {"data-email": r.email or "", "data-telefone": r.celular or ""},
		}
		for r in registros
	]


def _resolver_nome_coord_geral(doc) -> str:
	"""Nome do coordenador geral, com fallback ao link para festas salvas antes
	do campo `nome_coord_geral` passar a ser materializado no controller."""
	if doc.nome_coord_geral:
		return doc.nome_coord_geral
	if doc.tipo_coord_geral == "Responsavel" and doc.responsavel_coord_geral:
		return frappe.db.get_value("Responsavel", doc.responsavel_coord_geral, "nome_completo") or ""
	if doc.tipo_coord_geral == "Associado" and doc.associado_coord_geral:
		return frappe.db.get_value("Associado", doc.associado_coord_geral, "nome_completo") or ""
	return ""


def build_festa_payload(festa_name: str) -> dict:
	"""Monta o payload completo de uma Festa para hidratar a página ou refresh via API."""
	doc = frappe.get_doc("Festa", festa_name)

	payload: dict = {
		"festa_name": doc.name,
		"festa_board_name": doc.board_tarefas or "",
		"nome_festa": doc.nome_festa or doc.name,
		"status": doc.status or "",
		"data_formatada": format_date(doc.data, "dd/MM/yyyy") if doc.data else "",
		"horario_inicio": _format_time(doc.horario_inicio),
		"horario_termino": _format_time(doc.horario_termino),
		"link_drive": (doc.link_drive or "").strip(),
		"tipo_coord_geral": doc.tipo_coord_geral or "",
		"responsavel_coord_geral": doc.responsavel_coord_geral or "",
		"associado_coord_geral": doc.associado_coord_geral or "",
		"nome_coord_geral": _resolver_nome_coord_geral(doc),
		"expectativa_min": doc.expectativa_publico_min or 0,
		"expectativa_intermediario": doc.expectativa_publico_intermediario or 0,
		"expectativa_max": doc.expectativa_publico_max or 0,
		"cenario_simulacao": doc.cenario_simulacao or "Intermediário",
		"preco_min_convite": flt(doc.preco_min_convite),
		"preco_sugerido_convite": flt(doc.preco_sugerido_convite),
		"preco_convite": flt(doc.preco_convite),
		"margem_seguranca": flt(doc.margem_seguranca),
		"totais": totais_payload(doc),
	}

	areas_refs = frappe.get_all(
		"Area da Festa",
		filters={"festa": doc.name},
		fields=["name"],
		order_by="creation asc",
	)
	areas = [_hydrate_area(frappe.get_doc("Area da Festa", r.name)) for r in areas_refs]
	payload["areas"] = areas

	barracas_refs = frappe.get_all(
		"Barraca da Festa",
		filters={"festa": doc.name},
		fields=["name"],
		order_by="creation asc",
	)
	barracas = [_hydrate_barraca(frappe.get_doc("Barraca da Festa", r.name)) for r in barracas_refs]
	payload["barracas"] = barracas

	payload["barracas_items"] = [
		{"label": b["nome_barraca"], "value": b["name"], "type": "item"} for b in barracas
	]
	areas_obrigatorias = [
		{"label": a["nome_area"], "value": a["name"], "type": "item"} for a in areas
	]
	payload["areas_items"] = [{"label": "Sem área", "value": "", "type": "item"}] + areas_obrigatorias
	payload["areas_items_obrigatorio"] = areas_obrigatorias

	areas_labels = {a["name"]: a["nome_area"] for a in areas}
	barracas_labels = {b["name"]: b["nome_barraca"] for b in barracas}
	payload["receitas_por_area"] = _serializar_orcamento_linhas(
		doc.receitas_por_area, "area", areas_labels
	)
	payload["despesas_por_area"] = _serializar_orcamento_linhas(
		doc.despesas_por_area, "area", areas_labels
	)
	payload["receitas_por_barraca"] = _serializar_orcamento_linhas(
		doc.receitas_por_barraca, "barraca", barracas_labels
	)
	payload["despesas_por_barraca"] = _serializar_orcamento_linhas(
		doc.despesas_por_barraca, "barraca", barracas_labels
	)

	produtos_refs = frappe.get_all(
		"Produto de Venda Festa",
		filters={"festa": doc.name},
		fields=["name"],
		order_by="nome_produto asc",
	)
	produtos = [
		_hydrate_produto(frappe.get_doc("Produto de Venda Festa", r.name)) for r in produtos_refs
	]
	payload["produtos"] = produtos
	payload["produtos_items"] = [{"label": "Selecionar produto", "value": "", "type": "item"}] + [
		{"label": p["nome_produto"], "value": p["name"], "type": "item"} for p in produtos
	]
	produto_labels = {p["name"]: p["nome_produto"] for p in produtos}

	compras_refs = frappe.get_all(
		"Compra Festa",
		filters={"festa": doc.name},
		fields=["name"],
		order_by="nome_item asc",
	)
	payload["compras"] = [
		_hydrate_compra(frappe.get_doc("Compra Festa", r.name), produto_labels)
		for r in compras_refs
	]

	contratacoes_refs = frappe.get_all(
		"Contratacao Festa",
		filters={"festa": doc.name},
		fields=["name"],
		order_by="nome_item asc",
	)
	payload["contratacoes"] = [
		_hydrate_contratacao(frappe.get_doc("Contratacao Festa", r.name))
		for r in contratacoes_refs
	]

	payload["unidades_items"] = [
		{"label": unidade, "value": unidade, "type": "item"} for unidade in UNIDADES
	]
	payload["associados_items"] = _select_items_associados()
	payload["responsaveis_items"] = _select_items_responsaveis()
	payload["convites_dashboard"] = build_convites_dashboard(doc.name)

	return payload


@frappe.whitelist()
def get_festa_payload(festa_name: str) -> dict:
	"""Retorna o payload completo para o front-end refazer o estado após mutações."""
	if not festa_name:
		frappe.throw("Parâmetro 'festa_name' obrigatório.", frappe.ValidationError)
	if not frappe.has_permission("Festa", "read", festa_name):
		frappe.throw("Sem permissão para acessar esta festa.", frappe.PermissionError)
	return build_festa_payload(festa_name)


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/festas/festa"
		raise frappe.Redirect

	if not user_has_access("/festas/festa"):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		nome_uel = uel_data.get("nome_da_uel")
		context.sidebar_title = f"{uel_data.get('tipo_uel')} {nome_uel}" if nome_uel else "Portal"
	else:
		context.sidebar_title = "Portal"

	festa_name = frappe.form_dict.get("name")
	context.active_link = "/festas"

	if not festa_name:
		context.not_found = True
		context.missing_reason = "Parâmetro 'name' não informado."
		enrich_context(context, "/festas/festa")
		return context

	try:
		payload = build_festa_payload(festa_name)
	except frappe.DoesNotExistError:
		context.not_found = True
		context.missing_reason = "Festa não encontrada."
		enrich_context(context, "/festas/festa")
		return context

	roles = set(frappe.get_roles(frappe.session.user))
	context.can_edit = bool(roles & ALLOWED_ROLES)

	context.current_user = frappe.session.user
	context.current_user_full_name = (
		frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
	)

	for key, value in payload.items():
		setattr(context, key, value)

	context.portal_breadcrumbs = [
		{"label": "Festas", "url": "/festas/todas_festas"},
		{"label": context.nome_festa},
	]

	enrich_context(context, "/festas/festa")
	return context
