"""Endpoints da aba Convites em /festas/festa (perfil Gestor de festas).

Inclui o dashboard agregado (opções, vendas confirmadas, série temporal e
totais), a configuração da festa (aceitar doações e data limite de vendas)
e o CRUD das `Opcao Convite Festa` usadas na vitrine pública.
"""

from __future__ import annotations

import json
import math
from datetime import datetime

import frappe
from frappe.utils import flt, getdate, today

from gris.api.festas import _ensure_gestor, _validate_festa

PUBLIC_SALE_URL = "/festas/venda_convite"

RAMOS_ESCOTEIROS = ["Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"]
RAMOS_CONVITE = [*RAMOS_ESCOTEIROS, "Diretoria"]
CENARIO_PARA_CAMPO = {
	"Mínimo": "expectativa_publico_min",
	"Intermediário": "expectativa_publico_intermediario",
	"Máximo": "expectativa_publico_max",
}
LOGO_RAMO_BASE = "/assets/gris/images/logos_ramos"
LOGO_POR_RAMO = {
	"Filhotes": f"{LOGO_RAMO_BASE}/Logo_ramo_filhotes_principal.png",
	"Lobinho": f"{LOGO_RAMO_BASE}/Logo_ramo_lobinho_principal.png",
	"Escoteiro": f"{LOGO_RAMO_BASE}/Logo_ramo_escoteiro_principal.png",
	"Sênior": f"{LOGO_RAMO_BASE}/Logo_ramo_senior_principal.png",
	"Pioneiro": f"{LOGO_RAMO_BASE}/Logo_ramo_pioneiro_principal.png",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_payload(payload) -> dict:
	if isinstance(payload, str):
		try:
			data = json.loads(payload)
		except (ValueError, TypeError):
			frappe.throw("Dados inválidos.")
	else:
		data = payload
	if not isinstance(data, dict):
		frappe.throw("Dados inválidos.")
	return data


def _hydrate_opcao(doc) -> dict:
	return {
		"name": doc.name,
		"festa": doc.festa,
		"nome_convite": doc.nome_convite,
		"ramo": doc.ramo or "",
		"ativo": bool(doc.ativo),
		"valor": flt(doc.valor),
		"quantidade_esperada": int(doc.quantidade_esperada or 0),
		"quantidade_vendida": int(doc.quantidade_vendida or 0),
		"imagem_capa": doc.imagem_capa or "",
	}


def _contagem_beneficiarios_por_ramo() -> dict:
	"""Beneficiários ativos por ramo escoteiro + Diretoria (Dirigentes ativos)."""
	contagem = {
		r: frappe.db.count(
			"Associado",
			{"ramo": r, "categoria": "Beneficiário", "status_no_grupo": "Ativo"},
		)
		for r in RAMOS_ESCOTEIROS
	}
	contagem["Diretoria"] = frappe.db.count(
		"Associado",
		{"categoria": "Dirigente", "status_no_grupo": "Ativo"},
	)
	return contagem


# ---------------------------------------------------------------------------
# Dashboard agregado
# ---------------------------------------------------------------------------


def build_dashboard(festa_name: str) -> dict:
	"""Monta o dashboard de convites de uma festa.

	Reutilizado tanto por `get_dashboard` (chamada API) quanto pelo
	`build_festa_payload` para hidratar a página inicial sem chamada extra.
	"""
	festa = frappe.db.get_value(
		"Festa",
		festa_name,
		[
			"aceitar_doacoes",
			"data_limite_vendas",
			"convites_por_ramo",
			"cenario_simulacao",
			"expectativa_publico_min",
			"expectativa_publico_intermediario",
			"expectativa_publico_max",
		],
		as_dict=True,
	) or {}

	opcoes_rows = frappe.get_all(
		"Opcao Convite Festa",
		filters={"festa": festa_name},
		fields=[
			"name",
			"nome_convite",
			"ramo",
			"ativo",
			"valor",
			"quantidade_esperada",
			"quantidade_vendida",
			"imagem_capa",
		],
		order_by="nome_convite asc",
	)
	opcoes = [
		{
			"name": row.name,
			"festa": festa_name,
			"nome_convite": row.nome_convite or "",
			"ramo": row.ramo or "",
			"ativo": bool(row.ativo),
			"valor": flt(row.valor),
			"quantidade_esperada": int(row.quantidade_esperada or 0),
			"quantidade_vendida": int(row.quantidade_vendida or 0),
			"imagem_capa": row.imagem_capa or "",
		}
		for row in opcoes_rows
	]

	# Tabela: 1 linha por item de convite (eh_convite=1), todos os pedidos.
	convite_rows = frappe.db.sql(
		"""
		SELECT
			cf.name              AS pedido_name,
			cf.nome_pagador      AS nome_pagador,
			cf.email_pagador     AS email_pagador,
			cf.creation          AS creation,
			it.descricao         AS tipo_convite,
			it.opcao_convite     AS opcao_convite,
			it.quantidade        AS quantidade,
			it.valor             AS valor,
			COALESCE(cob.status, 'Pendente') AS status_pagamento
		FROM `tabConvite Festa` AS cf
		INNER JOIN `tabItem Convite Festa` AS it
			ON it.parent = cf.name AND it.parenttype = 'Convite Festa'
		LEFT JOIN `tabCobranca Infinitepay` AS cob
			ON cob.name = cf.cobranca_infinitepay
		WHERE cf.festa = %(festa)s AND it.eh_convite = 1
		ORDER BY cf.creation DESC, it.idx ASC
		""",
		{"festa": festa_name},
		as_dict=True,
	)
	convites_tabela = [
		{
			"pedido_name": row.pedido_name,
			"nome_pagador": row.nome_pagador or "",
			"email_pagador": row.email_pagador or "",
			"tipo_convite": row.tipo_convite or "",
			"opcao_convite": row.opcao_convite or "",
			"quantidade": int(row.quantidade or 0),
			"valor": flt(row.valor),
			"status_pagamento": row.status_pagamento or "Pendente",
			"creation": row.creation.isoformat() if row.creation else "",
		}
		for row in convite_rows
	]

	# Série temporal: apenas itens de pedidos pagos.
	# Convites por dia/opcao.
	serie_rows = frappe.db.sql(
		"""
		SELECT
			DATE(cf.creation) AS dia,
			it.opcao_convite  AS opcao_convite,
			it.descricao      AS tipo_convite,
			SUM(it.quantidade) AS quantidade,
			SUM(it.quantidade * it.valor) AS valor
		FROM `tabConvite Festa` AS cf
		INNER JOIN `tabItem Convite Festa` AS it
			ON it.parent = cf.name AND it.parenttype = 'Convite Festa'
		INNER JOIN `tabCobranca Infinitepay` AS cob
			ON cob.name = cf.cobranca_infinitepay AND cob.status = 'Pago'
		WHERE cf.festa = %(festa)s AND it.eh_convite = 1
		GROUP BY DATE(cf.creation), it.opcao_convite, it.descricao
		ORDER BY dia ASC
		""",
		{"festa": festa_name},
		as_dict=True,
	)
	series_por_dia = [
		{
			"dia": row.dia.isoformat() if hasattr(row.dia, "isoformat") else str(row.dia or ""),
			"opcao_convite": row.opcao_convite or "",
			"tipo_convite": row.tipo_convite or "",
			"quantidade": int(row.quantidade or 0),
			"valor": flt(row.valor),
		}
		for row in serie_rows
	]

	# Totais e barras: qtd e valor por opção, considerando apenas pagos.
	totais_rows = frappe.db.sql(
		"""
		SELECT
			it.opcao_convite  AS opcao_convite,
			it.descricao      AS tipo_convite,
			SUM(it.quantidade) AS quantidade,
			SUM(it.quantidade * it.valor) AS valor
		FROM `tabConvite Festa` AS cf
		INNER JOIN `tabItem Convite Festa` AS it
			ON it.parent = cf.name AND it.parenttype = 'Convite Festa'
		INNER JOIN `tabCobranca Infinitepay` AS cob
			ON cob.name = cf.cobranca_infinitepay AND cob.status = 'Pago'
		WHERE cf.festa = %(festa)s AND it.eh_convite = 1
		GROUP BY it.opcao_convite, it.descricao
		""",
		{"festa": festa_name},
		as_dict=True,
	)
	qtd_por_opcao = {}
	valor_por_opcao = {}
	for row in totais_rows:
		key = row.opcao_convite or row.tipo_convite or ""
		qtd_por_opcao[key] = int(row.quantidade or 0)
		valor_por_opcao[key] = flt(row.valor)

	# Total de doações (itens com eh_convite=0) em pedidos pagos.
	doacoes_row = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(it.quantidade * it.valor), 0) AS total
		FROM `tabConvite Festa` AS cf
		INNER JOIN `tabItem Convite Festa` AS it
			ON it.parent = cf.name AND it.parenttype = 'Convite Festa'
		INNER JOIN `tabCobranca Infinitepay` AS cob
			ON cob.name = cf.cobranca_infinitepay AND cob.status = 'Pago'
		WHERE cf.festa = %(festa)s AND it.eh_convite = 0
		""",
		{"festa": festa_name},
		as_dict=True,
	)
	total_doacoes_valor = flt(doacoes_row[0].total if doacoes_row else 0)

	data_limite = festa.get("data_limite_vendas")

	# Agregação por ramo (apenas quando flag estiver ligada na festa)
	convites_por_ramo = bool(festa.get("convites_por_ramo"))
	cenario_simulacao = festa.get("cenario_simulacao") or "Intermediário"
	por_ramo: dict = {}
	convites_por_associado = 0.0

	if convites_por_ramo:
		contagem_ramos = _contagem_beneficiarios_por_ramo()
		total_beneficiarios = sum(contagem_ramos.values())
		cenario_field = CENARIO_PARA_CAMPO.get(
			cenario_simulacao, "expectativa_publico_intermediario"
		)
		expectativa = int(festa.get(cenario_field) or 0)
		convites_por_associado = (
			(expectativa / total_beneficiarios) if total_beneficiarios > 0 else 0.0
		)

		# Soma qtd_vendida e qtd_esperada por ramo a partir das opções carregadas.
		for ramo in RAMOS_CONVITE:
			por_ramo[ramo] = {
				"beneficiarios_ativos": int(contagem_ramos.get(ramo, 0)),
				"qtd_vendida": 0,
				"qtd_esperada": 0,
			}
		for op in opcoes:
			ramo = op.get("ramo")
			if not ramo or ramo not in por_ramo:
				continue
			por_ramo[ramo]["qtd_vendida"] += int(
				qtd_por_opcao.get(op["name"], 0)
			)
			por_ramo[ramo]["qtd_esperada"] += int(op["quantidade_esperada"] or 0)

	return {
		"festa_name": festa_name,
		"opcoes": opcoes,
		"convites": convites_tabela,
		"series_por_dia": series_por_dia,
		"aceitar_doacoes": bool(festa.get("aceitar_doacoes")),
		"data_limite_vendas": data_limite.isoformat() if data_limite else "",
		"link_publico": PUBLIC_SALE_URL,
		"convites_por_ramo": convites_por_ramo,
		"cenario_simulacao": cenario_simulacao,
		"convites_por_associado": flt(convites_por_associado),
		"por_ramo": por_ramo,
		"totais": {
			"qtd_por_opcao": qtd_por_opcao,
			"valor_por_opcao": valor_por_opcao,
			"total_doacoes_valor": total_doacoes_valor,
		},
	}


@frappe.whitelist()
def get_dashboard(festa_name: str) -> dict:
	if not festa_name:
		frappe.throw("Parâmetro 'festa_name' obrigatório.")
	if not frappe.has_permission("Festa", "read", festa_name):
		frappe.throw("Sem permissão para acessar esta festa.", frappe.PermissionError)
	_validate_festa(festa_name)
	return build_dashboard(festa_name)


# ---------------------------------------------------------------------------
# Configurações da festa (switch + data limite)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def update_config(festa_name: str, aceitar_doacoes, data_limite_vendas) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)

	flag = 1 if aceitar_doacoes in ("1", "true", "True", True, 1) else 0
	data_value = (data_limite_vendas or "").strip() if isinstance(data_limite_vendas, str) else data_limite_vendas
	if data_value:
		try:
			datetime.strptime(str(data_value), "%Y-%m-%d")
		except ValueError:
			frappe.throw("Data limite de vendas inválida.")
		if getdate(data_value) < getdate(today()):
			# Permite manter datas no passado para não bloquear correções administrativas;
			# o bloqueio efetivo é feito no controller de Convite Festa.
			pass
	else:
		data_value = None

	frappe.db.set_value(
		"Festa",
		festa_name,
		{"aceitar_doacoes": flag, "data_limite_vendas": data_value},
	)
	return {
		"ok": True,
		"aceitar_doacoes": bool(flag),
		"data_limite_vendas": data_value or "",
	}


# ---------------------------------------------------------------------------
# CRUD de Opcao Convite Festa
# ---------------------------------------------------------------------------


@frappe.whitelist()
def upsert_opcao(festa_name: str, payload) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)

	data = _parse_payload(payload)
	nome_convite = (data.get("nome_convite") or "").strip()
	if not nome_convite:
		frappe.throw("Informe o nome do convite.")

	try:
		valor = flt(data.get("valor", 0))
	except (ValueError, TypeError):
		frappe.throw("Valor inválido.")
	if valor < 0:
		frappe.throw("Valor não pode ser negativo.")

	qtd_esperada = data.get("quantidade_esperada")
	if qtd_esperada in (None, ""):
		qtd_esperada = 0
	try:
		qtd_esperada = int(qtd_esperada)
	except (ValueError, TypeError):
		frappe.throw("Quantidade esperada inválida.")
	if qtd_esperada < 0:
		frappe.throw("Quantidade esperada não pode ser negativa.")

	ativo = 1 if data.get("ativo") in ("1", "true", "True", True, 1, None) else 0
	if data.get("ativo") in (0, "0", "false", "False", False):
		ativo = 0
	imagem_capa = (data.get("imagem_capa") or "").strip() or None

	ramo_presente = "ramo" in data
	ramo = (data.get("ramo") or "").strip() or None
	if ramo and ramo not in RAMOS_CONVITE:
		frappe.throw("Ramo inválido.")

	name = (data.get("name") or "").strip()
	if name:
		doc = frappe.get_doc("Opcao Convite Festa", name)
		if doc.festa != festa_name:
			frappe.throw("Opção pertence a outra festa.")
		doc.nome_convite = nome_convite
		if ramo_presente:
			doc.ramo = ramo
		doc.valor = valor
		doc.quantidade_esperada = qtd_esperada
		doc.ativo = ativo
		doc.imagem_capa = imagem_capa
		doc.save()
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Opcao Convite Festa",
				"festa": festa_name,
				"nome_convite": nome_convite,
				"ramo": ramo,
				"valor": valor,
				"quantidade_esperada": qtd_esperada,
				"ativo": ativo,
				"imagem_capa": imagem_capa,
			}
		)
		doc.insert()

	return {"ok": True, "opcao": _hydrate_opcao(doc)}


@frappe.whitelist()
def delete_opcao(opcao_name: str) -> dict:
	_ensure_gestor()

	doc = frappe.get_doc("Opcao Convite Festa", opcao_name)
	if int(doc.quantidade_vendida or 0) > 0:
		frappe.throw(
			"Esta opção já possui vendas confirmadas. Marque como inativa em vez de excluir.",
		)

	# Bloqueia exclusão se houver itens de convite vinculados (pedidos pendentes).
	em_uso = frappe.db.exists(
		"Item Convite Festa", {"opcao_convite": opcao_name}
	)
	if em_uso:
		frappe.throw(
			"Esta opção está vinculada a um ou mais pedidos. Marque como inativa em vez de excluir.",
		)

	frappe.delete_doc("Opcao Convite Festa", opcao_name)
	return {"ok": True}


# ---------------------------------------------------------------------------
# Wizard: criar opções por ramo
# ---------------------------------------------------------------------------


@frappe.whitelist()
def criar_opcoes_por_ramo(festa_name: str) -> dict:
	"""Cria automaticamente uma Opcao Convite Festa por ramo escoteiro com
	beneficiários ativos na UEL, mais Diretoria (sempre). Distribui a
	expectativa de público do cenário selecionado proporcionalmente ao número
	de beneficiários ativos de cada ramo (round-up).
	"""
	_ensure_gestor()
	_validate_festa(festa_name)

	if frappe.db.count("Opcao Convite Festa", {"festa": festa_name}):
		frappe.throw("Esta festa já possui tipos de convite cadastrados.")

	festa = frappe.get_doc("Festa", festa_name)

	contagem = _contagem_beneficiarios_por_ramo()
	total_beneficiarios = sum(contagem.values())

	cenario_field = CENARIO_PARA_CAMPO.get(
		festa.cenario_simulacao or "Intermediário",
		"expectativa_publico_intermediario",
	)
	expectativa = int(festa.get(cenario_field) or 0)

	convites_por_associado = (
		(expectativa / total_beneficiarios) if total_beneficiarios > 0 else 0.0
	)

	ramos_a_criar = [
		*(r for r in RAMOS_ESCOTEIROS if contagem.get(r, 0) > 0),
		"Diretoria",
	]

	preco = flt(festa.preco_convite or 0)
	for ramo in ramos_a_criar:
		qtd_esperada = math.ceil(convites_por_associado * contagem.get(ramo, 0))
		frappe.get_doc(
			{
				"doctype": "Opcao Convite Festa",
				"festa": festa_name,
				"nome_convite": ramo,
				"ramo": ramo,
				"valor": preco,
				"quantidade_esperada": qtd_esperada,
				"ativo": 1,
				"imagem_capa": LOGO_POR_RAMO.get(ramo) or None,
			}
		).insert()

	festa.db_set("convites_por_ramo", 1, update_modified=True)

	return {"ok": True, "dashboard": build_dashboard(festa_name)}
