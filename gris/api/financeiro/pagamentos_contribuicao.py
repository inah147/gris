"""Apuração da contribuição mensal a partir do DocType Pagamento Contribuicao Mensal.

A fonte de verdade voltou a ser o registro de cobrança: cada linha é um mês de
um contribuinte, com status (Em Aberto/Atrasado/Pago), valor e — quando pago —
a transação do extrato que quitou (`transacao_extrato`). Sem linha gerada para
o mês, ele aparece como "Não gerado": nem conta como esperado, nem como
recebido, até que o scheduler de geração mensal (ou alguém pela tela/MCP) crie
o registro.

Diferente da apuração antiga baseada em transações
(`gris.api.financeiro.contribuicoes`), esta versão é deliberadamente simples:
não há carência de registro, valor de atraso escalonado nem crédito
retroativo — o status e o valor de cada mês são só o que está gravado no
Pagamento Contribuicao Mensal, editável pela tela (`/financeiro/contribuicoes`
e `/financeiro/contribuicao`) e pelo MCP (`listar_pagamentos_contribuicao_mensal`
/ `atualizar_pagamento_contribuicao_mensal` / `definir_pagamento_mensal`).
"""

from __future__ import annotations

import datetime

import frappe
from frappe import _
from frappe.utils import add_months, getdate

from gris.api.financeiro.contribuicoes import (
	CATEGORIAS_CONTRIBUINTES,
	MESES_MAXIMO,
	MESES_PADRAO,
	chave_mes,
	construir_meses,
	get_contribuintes,
	get_transacoes_do_associado,
	get_transacoes_nao_vinculadas,
	normalizar_meses,
	rotulo_mes,
)
from gris.api.portal_access import user_has_access

STATUS_PAGO = "Pago"
STATUS_EM_ABERTO = "Em Aberto"
STATUS_ATRASADO = "Atrasado"
STATUS_NAO_GERADO = "Não gerado"

SLUG_SITUACAO = {
	STATUS_PAGO: "pago",
	STATUS_EM_ABERTO: "aberto",
	STATUS_ATRASADO: "atrasado",
	STATUS_NAO_GERADO: "na",
}

# Ordem de severidade: o pior status presente é a situação resumida do associado.
ORDEM_SITUACAO = [STATUS_ATRASADO, STATUS_EM_ABERTO, STATUS_NAO_GERADO, STATUS_PAGO]

STATUS_VALIDOS = (STATUS_PAGO, STATUS_EM_ABERTO, STATUS_ATRASADO)

ROLE_GESTOR = "Gestor Contribuição Mensal"
ROTA_CONTRIBUICOES = "/financeiro/contribuicoes"


def get_dia_vencimento() -> int:
	try:
		config = frappe.get_single("Configuracoes Contribuicao Mensal")
		dia = int(getattr(config, "dia_vencimento", 10) or 10)
	except Exception:
		dia = 10
	return dia if 1 <= dia <= 28 else 10


def get_pagamentos_por_associado(
	primeiro_dia: datetime.date, ultimo_dia: datetime.date, associados: list[str] | None = None
) -> dict[str, dict[str, dict]]:
	"""Registros de Pagamento Contribuicao Mensal no período, agrupados por associado e mês."""
	filtros: dict = {"mes_de_referencia": ["between", [primeiro_dia, ultimo_dia]]}
	if associados is not None:
		if not associados:
			return {}
		filtros["associado"] = ["in", list(associados)]

	linhas = frappe.get_all(
		"Pagamento Contribuicao Mensal",
		filters=filtros,
		fields=["name", "associado", "status", "valor", "atrasou", "mes_de_referencia", "transacao_extrato"],
	)

	agrupado: dict[str, dict[str, dict]] = {}
	for linha in linhas:
		por_mes = agrupado.setdefault(linha.associado, {})
		por_mes[chave_mes(getdate(linha.mes_de_referencia))] = linha
	return agrupado


def _situacao_da_linha(registro) -> str:
	if not registro:
		return STATUS_NAO_GERADO
	if registro.status in STATUS_VALIDOS:
		return registro.status
	return STATUS_EM_ABERTO


def montar_grade_pagamentos(meses: list[datetime.date], pagamentos_do_associado: dict[str, dict]) -> dict:
	"""Situação mês a mês de um contribuinte, lida direto do que está gravado."""
	linhas = []
	total_esperado = 0.0
	total_recebido = 0.0
	meses_gerados = 0
	meses_quitados = 0

	for mes in meses:
		ym = chave_mes(mes)
		registro = pagamentos_do_associado.get(ym)
		status = _situacao_da_linha(registro)
		valor = float(registro.valor or 0) if registro else 0.0
		recebido = valor if status == STATUS_PAGO else 0.0

		if registro:
			meses_gerados += 1
			total_esperado += valor
		if status == STATUS_PAGO:
			meses_quitados += 1
			total_recebido += valor

		linhas.append(
			{
				"name": registro.name if registro else None,
				"ym": ym,
				"rotulo": rotulo_mes(mes),
				"status": status,
				"status_slug": SLUG_SITUACAO[status],
				"valor": round(valor, 2),
				"recebido": round(recebido, 2),
				"falta": round(valor, 2) if status != STATUS_PAGO and registro else 0.0,
				"atrasou": bool(registro.atrasou) if registro else False,
				"transacao_extrato": registro.transacao_extrato if registro else None,
			}
		)

	situacao = STATUS_NAO_GERADO
	presentes = {linha["status"] for linha in linhas}
	for candidato in ORDEM_SITUACAO:
		if candidato in presentes:
			situacao = candidato
			break

	return {
		"linhas": linhas,
		"situacao": situacao,
		"situacao_slug": SLUG_SITUACAO[situacao],
		"total_esperado": round(total_esperado, 2),
		"total_recebido": round(total_recebido, 2),
		"saldo": round(total_recebido - total_esperado, 2),
		"meses_gerados": meses_gerados,
		"meses_quitados": meses_quitados,
		"meses_pendentes": meses_gerados - meses_quitados,
	}


def _acao_de_cadastro(contribuinte: dict) -> str | None:
	"""Pendência de cadastro da cobrança: sem carência, é imediata."""
	status_grupo = contribuinte.get("status_no_grupo")
	status_cobranca = contribuinte.get("status_cobranca")
	if status_grupo == "Inativo" and status_cobranca == "Ativo":
		return "Cancelar"
	if status_grupo == "Ativo" and status_cobranca != "Ativo":
		return "Cadastrar"
	return None


def apurar(
	meses=MESES_PADRAO, hoje: datetime.date | None = None, incluir_dados_cobranca: bool = False
) -> dict:
	"""Apuração completa do período, lida do Pagamento Contribuicao Mensal."""
	quantidade_meses = normalizar_meses(meses)
	hoje = hoje or getdate()
	sequencia = construir_meses(quantidade_meses, hoje)
	primeiro_dia = sequencia[0]
	ultimo_dia = getdate(add_months(sequencia[-1], 1)) - datetime.timedelta(days=1)
	proximo_mes = getdate(add_months(sequencia[-1], 1))

	contribuintes = get_contribuintes()
	pagamentos = get_pagamentos_por_associado(primeiro_dia, ultimo_dia)
	nao_vinculadas = get_transacoes_nao_vinculadas(primeiro_dia, proximo_mes)

	chaves = [chave_mes(mes) for mes in sequencia]
	esperado_mes = dict.fromkeys(chaves, 0.0)
	recebido_mes = dict.fromkeys(chaves, 0.0)
	gerados_mes = dict.fromkeys(chaves, 0)
	quitados_mes = dict.fromkeys(chaves, 0)

	associados = []
	for contribuinte in contribuintes:
		grade = montar_grade_pagamentos(sequencia, pagamentos.get(contribuinte["name"], {}))
		for linha in grade["linhas"]:
			ym = linha["ym"]
			if linha["status"] != STATUS_NAO_GERADO:
				gerados_mes[ym] += 1
				esperado_mes[ym] += linha["valor"]
			if linha["status"] == STATUS_PAGO:
				quitados_mes[ym] += 1
				recebido_mes[ym] += linha["valor"]

		dados_cobranca = (
			{
				"email_cobranca": contribuinte.get("email_cobranca"),
				"telefone_cobranca": contribuinte.get("telefone_cobranca"),
			}
			if incluir_dados_cobranca
			else {}
		)
		associados.append(
			{
				"id": contribuinte["name"],
				"nome": contribuinte.get("nome_completo") or contribuinte["name"],
				"categoria": contribuinte.get("categoria"),
				"secao": contribuinte.get("secao"),
				"status_no_grupo": contribuinte.get("status_no_grupo"),
				"status_cobranca": contribuinte.get("status_cobranca"),
				"esperado_mensal": float(contribuinte.get("valor_contribuicao") or 0),
				"acao_cadastro": _acao_de_cadastro(contribuinte),
				**dados_cobranca,
				**grade,
			}
		)

	nao_vinculado_mes = dict.fromkeys(chaves, 0.0)
	for transacao in nao_vinculadas:
		ym = (transacao.get("data") or "")[:7]
		if ym in nao_vinculado_mes:
			nao_vinculado_mes[ym] += transacao["valor"]

	total_esperado = sum(esperado_mes.values())
	total_recebido = sum(recebido_mes.values())
	total_nao_vinculado = sum(nao_vinculado_mes.values())
	total_gerados = sum(gerados_mes.values())
	total_quitados = sum(quitados_mes.values())

	com_pendencia = [a for a in associados if a["situacao"] in (STATUS_ATRASADO, STATUS_EM_ABERTO)]

	return {
		"meses": [{"ym": chave_mes(mes), "rotulo": rotulo_mes(mes)} for mes in sequencia],
		"quantidade_meses": quantidade_meses,
		"periodo": {"inicio": primeiro_dia.isoformat(), "fim": sequencia[-1].isoformat()},
		"dia_vencimento": get_dia_vencimento(),
		"associados": associados,
		"nao_vinculadas": nao_vinculadas,
		"series": {
			"labels": [rotulo_mes(mes) for mes in sequencia],
			"recebido": [round(recebido_mes[ym], 2) for ym in chaves],
			"nao_vinculado": [round(nao_vinculado_mes[ym], 2) for ym in chaves],
			"esperado": [round(esperado_mes[ym], 2) for ym in chaves],
			"adimplencia": [
				round((quitados_mes[ym] / gerados_mes[ym]) * 100, 2) if gerados_mes[ym] else 0.0
				for ym in chaves
			],
		},
		"totais": {
			"contribuintes": len(associados),
			"recebido_vinculado": round(total_recebido, 2),
			"recebido_nao_vinculado": round(total_nao_vinculado, 2),
			"recebido_total": round(total_recebido + total_nao_vinculado, 2),
			"esperado": round(total_esperado, 2),
			"saldo": round(total_recebido - total_esperado, 2),
			"meses_devidos": total_gerados,
			"meses_quitados": total_quitados,
			"adimplencia": round((total_quitados / total_gerados) * 100, 2) if total_gerados else 0.0,
			"com_pendencia": len(com_pendencia),
			"inadimplentes": len([a for a in associados if a["situacao"] == STATUS_ATRASADO]),
			"inadimplencia_associados": (
				round(
					len([a for a in associados if a["situacao"] == STATUS_ATRASADO]) / len(associados) * 100,
					2,
				)
				if associados
				else 0.0
			),
			"a_cadastrar": len([a for a in associados if a["acao_cadastro"] == "Cadastrar"]),
			"a_cancelar": len([a for a in associados if a["acao_cadastro"] == "Cancelar"]),
			"transacoes_nao_vinculadas": len(nao_vinculadas),
		},
	}


def apurar_associados(
	nomes: list[str], meses=MESES_PADRAO, hoje: datetime.date | None = None, incluir_gestao: bool = False
) -> list[dict]:
	"""Apura um conjunto fechado de associados (detalhe do contribuinte, cobrança)."""
	if not nomes:
		return []

	quantidade_meses = normalizar_meses(meses)
	hoje = hoje or getdate()
	sequencia = construir_meses(quantidade_meses, hoje)
	primeiro_dia = sequencia[0]
	ultimo_dia = getdate(add_months(sequencia[-1], 1)) - datetime.timedelta(days=1)

	contribuintes = frappe.get_all(
		"Associado",
		filters={"name": ["in", list(nomes)], "categoria": ["in", list(CATEGORIAS_CONTRIBUINTES)]},
		fields=[
			"name",
			"nome_completo",
			"categoria",
			"secao",
			"valor_contribuicao",
			"status_no_grupo",
			"status_cobranca",
			"email_cobranca",
			"telefone_cobranca",
		],
		order_by="nome_completo asc",
		limit_page_length=0,
	)
	if not contribuintes:
		return []

	pagamentos = get_pagamentos_por_associado(primeiro_dia, ultimo_dia, [c["name"] for c in contribuintes])

	apurados = []
	for contribuinte in contribuintes:
		grade = montar_grade_pagamentos(sequencia, pagamentos.get(contribuinte["name"], {}))
		dados_gestao = {}
		if incluir_gestao:
			dados_gestao = {
				"acao_cadastro": _acao_de_cadastro(contribuinte),
				"email_cobranca": contribuinte.get("email_cobranca"),
				"telefone_cobranca": contribuinte.get("telefone_cobranca"),
			}
		apurados.append(
			{
				"id": contribuinte["name"],
				"nome": contribuinte.get("nome_completo") or contribuinte["name"],
				"categoria": contribuinte.get("categoria"),
				"secao": contribuinte.get("secao"),
				"status_no_grupo": contribuinte.get("status_no_grupo"),
				"status_cobranca": contribuinte.get("status_cobranca"),
				"esperado_mensal": float(contribuinte.get("valor_contribuicao") or 0),
				"dia_vencimento": get_dia_vencimento(),
				**dados_gestao,
				**grade,
			}
		)
	return apurados


def _assert_acesso_leitura() -> None:
	if frappe.session.user == "Guest" or not user_has_access(ROTA_CONTRIBUICOES):
		frappe.throw(
			_("Sem permissão para consultar a apuração de contribuições mensais."),
			frappe.PermissionError,
		)


@frappe.whitelist()
def get_apuracao(meses: str | int = MESES_PADRAO):
	"""Apuração completa do período, para consumo do portal."""
	_assert_acesso_leitura()
	pode_ver_cobranca = ROLE_GESTOR in frappe.get_roles()
	return {"success": True, "dados": apurar(meses, incluir_dados_cobranca=pode_ver_cobranca)}


@frappe.whitelist()
def get_extrato_do_associado(associado: str, meses: str | int = MESES_PADRAO):
	"""Transações de contribuição de um associado no período — leitura do extrato.

	Não é regra de negócio da apuração (que agora vem do Pagamento Contribuicao
	Mensal): é só a lista de créditos brutos, útil como evidência ao lado do
	mês a mês.
	"""
	_assert_acesso_leitura()
	if not associado:
		frappe.throw(_("Parâmetro 'associado' é obrigatório."), frappe.ValidationError)

	quantidade_meses = normalizar_meses(meses)
	sequencia = construir_meses(quantidade_meses)
	transacoes = get_transacoes_do_associado(associado, sequencia[0], getdate(add_months(sequencia[-1], 1)))
	return {"success": True, "transacoes": transacoes}


__all__ = [
	"MESES_MAXIMO",
	"MESES_PADRAO",
	"ORDEM_SITUACAO",
	"ROLE_GESTOR",
	"ROTA_CONTRIBUICOES",
	"SLUG_SITUACAO",
	"STATUS_ATRASADO",
	"STATUS_EM_ABERTO",
	"STATUS_NAO_GERADO",
	"STATUS_PAGO",
	"apurar",
	"apurar_associados",
	"get_apuracao",
	"get_extrato_do_associado",
	"get_pagamentos_por_associado",
	"montar_grade_pagamentos",
	"normalizar_meses",
]
