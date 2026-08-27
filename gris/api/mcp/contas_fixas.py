"""Ferramentas MCP de contas fixas (despesas recorrentes) e seus pagamentos."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, getdate

from gris.api.mcp.registry import ErroDeFerramenta, ferramenta, normalizar_limite

DOCTYPE_CONTA = "Conta Fixa"
DOCTYPE_PAGAMENTO = "Pagamento Conta Fixa"

ROLES_LEITURA = ("Gestor Financeiro", "Visualizador Financeiro")
ROLES_ESCRITA = ("Gestor Financeiro",)

STATUS_PAGAMENTO = ("Pago", "Em Aberto", "Atrasado")
MAX_PAGAMENTOS_LOTE = 100


def _mes_para_data(mes: str) -> str:
	texto = str(mes).strip()
	if len(texto) == 7:
		texto = f"{texto}-01"
	try:
		return getdate(texto).replace(day=1).strftime("%Y-%m-%d")
	except Exception:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "'mes' deve estar no formato AAAA-MM (ex.: 2026-03).")


@ferramenta(
	nome="listar_contas_fixas",
	titulo="Listar contas fixas",
	descricao=(
		"Lista as despesas recorrentes cadastradas (aluguel, energia, internet...) com valor, "
		"dia de vencimento e vigência das despesas temporárias, somando o custo mensal."
	),
	parametros={
		"apenas_ativas": {
			"type": "boolean",
			"default": True,
			"description": "Se falso, inclui também as contas desativadas.",
		},
		"tipo": {
			"type": "string",
			"enum": ["todas", "continuas", "temporarias"],
			"default": "todas",
			"description": "Filtra despesas contínuas ou temporárias.",
		},
	},
	roles=ROLES_LEITURA,
)
def listar_contas_fixas(apenas_ativas: bool = True, tipo: str = "todas") -> dict:
	filtros: dict[str, Any] = {}
	if apenas_ativas:
		filtros["ativa"] = 1
	if tipo == "continuas":
		filtros["despesa_temporaria"] = 0
	elif tipo == "temporarias":
		filtros["despesa_temporaria"] = 1

	contas = frappe.get_all(
		DOCTYPE_CONTA,
		filters=filtros,
		fields=[
			"name",
			"descricao",
			"valor",
			"dia_vencimento",
			"ativa",
			"despesa_temporaria",
			"data_inicio",
			"data_termino",
		],
		order_by="dia_vencimento asc, descricao asc",
	)

	total_ativas = sum(flt(conta.get("valor")) for conta in contas if conta.get("ativa"))

	return {
		"contas": contas,
		"total": len(contas),
		"custo_mensal_ativas": flt(total_ativas, 2),
	}


@ferramenta(
	nome="listar_pagamentos_contas_fixas",
	titulo="Listar pagamentos de contas fixas",
	descricao=(
		"Lista os pagamentos mensais das contas fixas. Sem filtro de status, traz todos; "
		"use status='Em Aberto' ou 'Atrasado' para ver o que falta pagar no mês."
	),
	parametros={
		"conta": {"type": "string", "description": "Nome da Conta Fixa (o próprio identificador)."},
		"status": {
			"type": "string",
			"enum": list(STATUS_PAGAMENTO),
			"description": "Situação do pagamento.",
		},
		"mes": {"type": "string", "description": "Mês de referência (AAAA-MM)."},
		"limite": {
			"type": "integer",
			"default": 25,
			"minimum": 1,
			"maximum": 100,
			"description": "Registros por página (máx. 100).",
		},
		"inicio": {"type": "integer", "default": 0, "minimum": 0, "description": "Deslocamento."},
	},
	roles=ROLES_LEITURA,
)
def listar_pagamentos_contas_fixas(
	conta: str | None = None,
	status: str | None = None,
	mes: str | None = None,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict[str, Any] = {}
	if conta:
		filtros["conta"] = conta
	if status:
		filtros["status"] = status
	if mes:
		filtros["mes_referencia"] = _mes_para_data(mes)

	pagamentos = frappe.get_all(
		DOCTYPE_PAGAMENTO,
		filters=filtros,
		fields=["name", "conta", "titulo", "status", "mes_referencia", "valor"],
		order_by="mes_referencia desc, conta asc",
		limit_page_length=normalizar_limite(limite),
		limit_start=max(0, int(inicio or 0)),
	)

	em_aberto = sum(flt(linha.get("valor")) for linha in pagamentos if linha.get("status") != "Pago")

	return {
		"pagamentos": pagamentos,
		"valor_em_aberto_na_pagina": flt(em_aberto, 2),
		"paginacao": {
			"inicio": max(0, int(inicio or 0)),
			"limite": normalizar_limite(limite),
			"retornados": len(pagamentos),
			"total_com_filtros": frappe.db.count(DOCTYPE_PAGAMENTO, filtros),
		},
	}


@ferramenta(
	nome="marcar_contas_fixas_pagas",
	titulo="Marcar contas fixas como pagas",
	descricao=(
		"Marca pagamentos de contas fixas como 'Pago' (até 100 por chamada). "
		"Use simular=true para conferir a lista antes de gravar."
	),
	parametros={
		"ids": {
			"type": "array",
			"maxItems": MAX_PAGAMENTOS_LOTE,
			"description": "IDs dos pagamentos ('name' de 'listar_pagamentos_contas_fixas').",
		},
	},
	obrigatorios=("ids",),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def marcar_contas_fixas_pagas(ids: list[str], simular: bool = False) -> dict:
	ids = [str(item).strip() for item in ids if str(item).strip()]
	if not ids:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe ao menos um ID de pagamento.")

	from gris.api.financeiro import conta_fixa as servico

	pagos: list[str] = []
	ja_pagos: list[str] = []
	falhas: list[dict] = []

	for pagamento_id in ids:
		situacao = frappe.db.get_value(
			DOCTYPE_PAGAMENTO, pagamento_id, ["status", "conta", "mes_referencia"], as_dict=True
		)
		if situacao is None:
			falhas.append({"id": pagamento_id, "erro": "Pagamento não encontrado."})
			continue
		if situacao.get("status") == "Pago":
			ja_pagos.append(pagamento_id)
			continue
		if simular:
			pagos.append(pagamento_id)
			continue
		try:
			servico.marcar_pagamento_pago(pagamento_id)
			pagos.append(pagamento_id)
		except frappe.PermissionError as exc:
			falhas.append({"id": pagamento_id, "erro": str(exc) or "Sem permissão de escrita."})

	resultado: dict[str, Any] = {
		"solicitadas": len(ids),
		"marcadas_como_pagas": len(pagos),
		"ids_afetados": pagos,
		"ja_estavam_pagas": ja_pagos,
		"falhas": falhas,
	}
	if simular:
		resultado["simulacao"] = True
		resultado["marcadas_como_pagas"] = 0
		resultado["seriam_marcadas"] = pagos
		resultado.pop("ids_afetados")
	return resultado
