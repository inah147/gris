"""Ferramentas MCP de contribuições mensais e cobrança dos associados.

A regra de negócio continua em ``gris.api.financeiro.monthly_payments`` — aqui há
consulta, agregação e a chamada dos serviços já existentes, com suporte a
simulação (dry-run) nas operações de escrita.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt, getdate

from gris.api.mcp.registry import ErroDeFerramenta, ferramenta, normalizar_limite

DOCTYPE = "Pagamento Contribuicao Mensal"

ROLES_LEITURA = ("Gestor Contribuição Mensal", "Visualizador Contribuição Mensal")
ROLES_ESCRITA = ("Gestor Contribuição Mensal",)

STATUS_VALIDOS = ("Pago", "Em Aberto", "Atrasado")
MAX_PAGAMENTOS_LOTE = 200

CAMPOS_COBRANCA = ("valor_contribuicao", "status_cobranca", "email_cobranca", "telefone_cobranca")


def _mes_para_data(mes: str, nome_campo: str) -> str:
	"""Aceita 'AAAA-MM' ou 'AAAA-MM-DD' e devolve o primeiro dia do mês."""
	texto = str(mes).strip()
	if len(texto) == 7:
		texto = f"{texto}-01"
	try:
		data = getdate(texto)
	except Exception:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			f"'{nome_campo}' deve estar no formato AAAA-MM (ex.: 2026-03).",
		)
	return data.replace(day=1).strftime("%Y-%m-%d")


def _nomes_de_associados(registros: list[dict]) -> dict[str, str]:
	"""Busca os nomes em uma consulta só (evita N+1 ao montar a lista)."""
	cpfs = sorted({linha["associado"] for linha in registros if linha.get("associado")})
	if not cpfs:
		return {}
	linhas = frappe.get_all(
		"Associado",
		filters={"name": ["in", cpfs]},
		fields=["name", "nome_completo"],
	)
	return {linha["name"]: linha["nome_completo"] for linha in linhas}


@ferramenta(
	nome="listar_contribuicoes",
	titulo="Listar contribuições mensais",
	descricao=(
		"Lista os registros de contribuição mensal com filtros de associado, status e mês. "
		"Use status='Atrasado' para ver a inadimplência e mes_referencia no formato AAAA-MM."
	),
	parametros={
		"associado": {"type": "string", "description": "CPF do associado (identificador do registro)."},
		"status": {
			"type": "string",
			"enum": list(STATUS_VALIDOS),
			"description": "Situação do pagamento.",
		},
		"mes_referencia": {"type": "string", "description": "Mês exato no formato AAAA-MM."},
		"mes_inicio": {"type": "string", "description": "Início do intervalo (AAAA-MM)."},
		"mes_fim": {"type": "string", "description": "Fim do intervalo (AAAA-MM)."},
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
def listar_contribuicoes(
	associado: str | None = None,
	status: str | None = None,
	mes_referencia: str | None = None,
	mes_inicio: str | None = None,
	mes_fim: str | None = None,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict[str, Any] = {}
	if associado:
		filtros["associado"] = associado
	if status:
		filtros["status"] = status

	if mes_referencia:
		filtros["mes_de_referencia"] = _mes_para_data(mes_referencia, "mes_referencia")
	elif mes_inicio and mes_fim:
		filtros["mes_de_referencia"] = [
			"between",
			[_mes_para_data(mes_inicio, "mes_inicio"), _mes_para_data(mes_fim, "mes_fim")],
		]
	elif mes_inicio:
		filtros["mes_de_referencia"] = [">=", _mes_para_data(mes_inicio, "mes_inicio")]
	elif mes_fim:
		filtros["mes_de_referencia"] = ["<=", _mes_para_data(mes_fim, "mes_fim")]

	registros = frappe.get_all(
		DOCTYPE,
		filters=filtros,
		fields=["name", "associado", "status", "mes_de_referencia", "valor", "atrasou"],
		order_by="mes_de_referencia desc, associado asc",
		limit_page_length=normalizar_limite(limite),
		limit_start=max(0, int(inicio or 0)),
	)

	nomes = _nomes_de_associados(registros)
	for linha in registros:
		linha["nome_associado"] = nomes.get(linha.get("associado"))

	return {
		"contribuicoes": registros,
		"paginacao": {
			"inicio": max(0, int(inicio or 0)),
			"limite": normalizar_limite(limite),
			"retornados": len(registros),
			"total_com_filtros": frappe.db.count(DOCTYPE, filtros),
		},
	}


@ferramenta(
	nome="resumo_inadimplencia",
	titulo="Resumo de inadimplência",
	descricao=(
		"Consolida as contribuições de um mês (ou intervalo): quantidade e valor por status, "
		"percentual de inadimplência e a lista de associados em atraso. Sem parâmetros, usa o "
		"mês corrente."
	),
	parametros={
		"mes_referencia": {"type": "string", "description": "Mês a consolidar (AAAA-MM)."},
		"mes_inicio": {"type": "string", "description": "Início do intervalo (AAAA-MM)."},
		"mes_fim": {"type": "string", "description": "Fim do intervalo (AAAA-MM)."},
		"limite_devedores": {
			"type": "integer",
			"default": 20,
			"minimum": 1,
			"maximum": 100,
			"description": "Quantos associados em atraso listar.",
		},
	},
	roles=ROLES_LEITURA,
)
def resumo_inadimplencia(
	mes_referencia: str | None = None,
	mes_inicio: str | None = None,
	mes_fim: str | None = None,
	limite_devedores: int = 20,
) -> dict:
	if mes_inicio or mes_fim:
		inicio = _mes_para_data(mes_inicio or mes_fim, "mes_inicio")
		fim = _mes_para_data(mes_fim or mes_inicio, "mes_fim")
		filtros: dict[str, Any] = {"mes_de_referencia": ["between", [inicio, fim]]}
		periodo = {"inicio": inicio, "fim": fim}
	else:
		mes = _mes_para_data(mes_referencia or getdate().strftime("%Y-%m"), "mes_referencia")
		filtros = {"mes_de_referencia": mes}
		periodo = {"inicio": mes, "fim": mes}

	agregados = frappe.get_all(
		DOCTYPE,
		filters=filtros,
		fields=["status", "count(name) as quantidade", "sum(valor) as total"],
		group_by="status",
	)

	por_status = {
		linha.get("status") or "(sem status)": {
			"quantidade": int(linha.get("quantidade") or 0),
			"valor": flt(linha.get("total"), 2),
		}
		for linha in agregados
	}

	total_registros = sum(item["quantidade"] for item in por_status.values())
	atrasados = por_status.get("Atrasado", {"quantidade": 0, "valor": 0.0})
	em_aberto = por_status.get("Em Aberto", {"quantidade": 0, "valor": 0.0})

	filtros_atraso = dict(filtros)
	filtros_atraso["status"] = "Atrasado"
	devedores = frappe.get_all(
		DOCTYPE,
		filters=filtros_atraso,
		fields=["name", "associado", "mes_de_referencia", "valor"],
		order_by="mes_de_referencia asc, associado asc",
		limit_page_length=normalizar_limite(limite_devedores),
	)
	nomes = _nomes_de_associados(devedores)
	for linha in devedores:
		linha["nome_associado"] = nomes.get(linha.get("associado"))

	percentual = round((atrasados["quantidade"] / total_registros) * 100, 2) if total_registros else 0.0

	return {
		"periodo": periodo,
		"total_registros": total_registros,
		"por_status": por_status,
		"inadimplencia": {
			"quantidade": atrasados["quantidade"],
			"valor": atrasados["valor"],
			"percentual": percentual,
		},
		"a_receber": {
			"quantidade": atrasados["quantidade"] + em_aberto["quantidade"],
			"valor": flt(atrasados["valor"] + em_aberto["valor"], 2),
		},
		"devedores": devedores,
	}


@ferramenta(
	nome="marcar_contribuicoes_pagas",
	titulo="Marcar contribuições como pagas",
	descricao=(
		"Marca registros de contribuição mensal como 'Pago' (até 200 por chamada). "
		"Use simular=true para conferir a lista antes de gravar."
	),
	parametros={
		"ids": {
			"type": "array",
			"maxItems": MAX_PAGAMENTOS_LOTE,
			"description": "IDs dos pagamentos ('name' devolvido por 'listar_contribuicoes').",
		},
	},
	obrigatorios=("ids",),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def marcar_contribuicoes_pagas(ids: list[str], simular: bool = False) -> dict:
	ids = [str(item).strip() for item in ids if str(item).strip()]
	if not ids:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe ao menos um ID de pagamento.")

	from gris.api.financeiro import monthly_payments

	pagos: list[str] = []
	ja_pagos: list[str] = []
	falhas: list[dict] = []

	for pagamento_id in ids:
		situacao = frappe.db.get_value(
			DOCTYPE, pagamento_id, ["status", "associado", "mes_de_referencia"], as_dict=True
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
			monthly_payments.mark_payment_as_paid(pagamento_id)
			pagos.append(pagamento_id)
		except frappe.PermissionError as exc:
			falhas.append({"id": pagamento_id, "erro": str(exc) or "Sem permissão de escrita."})

	resultado = {
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


@ferramenta(
	nome="atualizar_cobranca_associado",
	titulo="Atualizar cobrança do associado",
	descricao=(
		"Ajusta os dados de cobrança de um associado: valor da contribuição mensal, situação da "
		"cobrança (Ativo/Inativo) e contatos de cobrança. Informe ao menos um campo."
	),
	parametros={
		"cpf": {"type": "string", "description": "CPF do associado."},
		"valor_contribuicao": {
			"type": "number",
			"description": "Novo valor mensal da contribuição (não pode ser negativo).",
		},
		"status_cobranca": {
			"type": "string",
			"enum": ["Ativo", "Inativo"],
			"description": "Ativa ou interrompe a cobrança do associado.",
		},
		"email_cobranca": {"type": "string", "description": "E-mail de cobrança."},
		"telefone_cobranca": {"type": "string", "description": "Telefone de cobrança."},
	},
	obrigatorios=("cpf",),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def atualizar_cobranca_associado(
	cpf: str,
	valor_contribuicao: float | None = None,
	status_cobranca: str | None = None,
	email_cobranca: str | None = None,
	telefone_cobranca: str | None = None,
	simular: bool = False,
) -> dict:
	solicitado = {
		"valor_contribuicao": valor_contribuicao,
		"status_cobranca": status_cobranca,
		"email_cobranca": email_cobranca,
		"telefone_cobranca": telefone_cobranca,
	}
	solicitado = {campo: valor for campo, valor in solicitado.items() if valor is not None}
	if not solicitado:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			"Informe ao menos um campo de cobrança para atualizar.",
			{"campos_aceitos": list(CAMPOS_COBRANCA)},
		)

	if valor_contribuicao is not None and flt(valor_contribuicao) < 0:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "O valor da contribuição não pode ser negativo.")

	atuais = frappe.db.get_value("Associado", cpf, list(CAMPOS_COBRANCA), as_dict=True)
	if atuais is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Nenhum associado encontrado com o CPF '{cpf}'.")

	alteracoes = {
		campo: {"de": atuais.get(campo), "para": valor}
		for campo, valor in solicitado.items()
		if atuais.get(campo) != valor
	}
	if not alteracoes:
		return {"atualizado": False, "motivo": "Nenhum valor diferente do atual.", "alteracoes": {}}

	if simular:
		return {"simulacao": True, "atualizado": False, "cpf": cpf, "alteracoes": alteracoes}

	from gris.api.financeiro import monthly_payments

	if "valor_contribuicao" in alteracoes:
		monthly_payments.update_contribution_value(cpf, flt(valor_contribuicao))
	if "status_cobranca" in alteracoes:
		if status_cobranca == "Ativo":
			monthly_payments.activate_billing_status(cpf)
		else:
			monthly_payments.deactivate_billing_status(cpf)
	if "email_cobranca" in alteracoes or "telefone_cobranca" in alteracoes:
		monthly_payments.update_billing_contacts(
			cpf,
			email=email_cobranca if "email_cobranca" in alteracoes else None,
			phone=telefone_cobranca if "telefone_cobranca" in alteracoes else None,
		)

	return {"atualizado": True, "cpf": cpf, "alteracoes": alteracoes}


@ferramenta(
	nome="gerar_contribuicoes_do_mes",
	titulo="Gerar contribuições do mês",
	descricao=(
		"Cria os registros 'Em Aberto' do mês corrente para todos os associados ativos da "
		"categoria Beneficiário. É idempotente: quem já tem registro no mês é ignorado. "
		"Use simular=true para saber quantos seriam criados."
	),
	parametros={},
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def gerar_contribuicoes_do_mes(simular: bool = False) -> dict:
	mes = getdate().replace(day=1).strftime("%Y-%m-%d")

	beneficiarios = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo", "categoria": "Beneficiário"},
		pluck="name",
	)
	existentes = set(frappe.get_all(DOCTYPE, filters={"mes_de_referencia": mes}, pluck="associado"))
	pendentes = [cpf for cpf in beneficiarios if cpf not in existentes]

	if simular:
		return {
			"simulacao": True,
			"mes_de_referencia": mes,
			"beneficiarios_ativos": len(beneficiarios),
			"ja_possuem_registro": len(beneficiarios) - len(pendentes),
			"seriam_criados": len(pendentes),
		}

	from gris.api.financeiro import monthly_payments

	criados = monthly_payments.generate_monthly_payments()
	return {
		"mes_de_referencia": mes,
		"beneficiarios_ativos": len(beneficiarios),
		"criados": criados,
	}
