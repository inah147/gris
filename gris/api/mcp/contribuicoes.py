"""Ferramentas MCP da contribuição mensal.

A apuração é a de ``gris.api.financeiro.contribuicoes``: a fonte de verdade são
as transações de crédito do extrato com categoria "Contribuição Mensal" e
beneficiário preenchido — não o DocType ``Pagamento Contribuicao Mensal``, que
continua servindo apenas ao fluxo de cobrança (schedulers).

Por isso, a forma de fazer uma contribuição "contar" é vincular a transação ao
associado: use 'listar_contribuicoes_nao_vinculadas' e depois
'categorizar_transacoes' com o campo beneficiario.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import flt

from gris.api.financeiro import contribuicoes as servico
from gris.api.mcp.registry import ErroDeFerramenta, ferramenta, normalizar_limite

ROLES_LEITURA = ("Gestor Contribuição Mensal", "Visualizador Contribuição Mensal")
ROLES_ESCRITA = ("Gestor Contribuição Mensal",)

SITUACOES = (
	servico.STATUS_ATRASADO,
	servico.STATUS_PARCIAL,
	servico.STATUS_EM_ABERTO,
	servico.STATUS_PAGO,
	servico.STATUS_AGUARDANDO,
	servico.STATUS_NAO_APLICAVEL,
)

ACOES_CADASTRO = ("Cadastrar", "Cancelar")

CAMPOS_COBRANCA = ("valor_contribuicao", "status_cobranca", "email_cobranca", "telefone_cobranca")

PARAMETRO_MESES = {
	"type": "integer",
	"default": servico.MESES_PADRAO,
	"minimum": 1,
	"maximum": servico.MESES_MAXIMO,
	"description": (
		f"Janela de apuração em meses, terminando no mês corrente "
		f"(padrão {servico.MESES_PADRAO}, máximo {servico.MESES_MAXIMO})."
	),
}


def _apurar(meses: int) -> dict:
	"""Apuração completa, respeitando o controle de acesso da página do portal."""
	resposta = servico.get_apuracao(meses)
	return resposta.get("dados") or {}


@ferramenta(
	nome="resumo_contribuicoes",
	titulo="Resumo da contribuição mensal",
	descricao=(
		"Consolida a contribuição mensal do período: quanto foi recebido (vinculado e não "
		"vinculado a associado), quanto era esperado, adimplência, quantos associados estão "
		"com pendência e quantos cadastros de cobrança precisam ser criados ou cancelados. "
		"A apuração vem das transações do extrato, não dos registros de cobrança."
	),
	parametros={"meses": PARAMETRO_MESES},
	roles=ROLES_LEITURA,
)
def resumo_contribuicoes(meses: int = servico.MESES_PADRAO) -> dict:
	dados = _apurar(meses)
	series = dados.get("series") or {}

	por_mes = [
		{
			"mes": rotulo,
			"recebido": series.get("recebido", [])[indice],
			"nao_vinculado": series.get("nao_vinculado", [])[indice],
			"esperado": series.get("esperado", [])[indice],
			"adimplencia": series.get("adimplencia", [])[indice],
		}
		for indice, rotulo in enumerate(series.get("labels") or [])
	]

	return {
		"periodo": dados.get("periodo"),
		"quantidade_meses": dados.get("quantidade_meses"),
		"dia_vencimento": dados.get("dia_vencimento"),
		"totais": dados.get("totais"),
		"por_mes": por_mes,
	}


@ferramenta(
	nome="apuracao_contribuicoes",
	titulo="Apuração por associado",
	descricao=(
		"Situação de cada contribuinte no período: esperado, recebido, saldo, crédito "
		"acumulado e situação (Atrasado, Parcial, Em Aberto, Pago, Aguardando). "
		"Use situacao='Atrasado' ou com_pendencia=true para a lista de cobrança e "
		"acao_cadastro para quem precisa ter a cobrança criada ou cancelada."
	),
	parametros={
		"meses": PARAMETRO_MESES,
		"situacao": {
			"type": "string",
			"enum": list(SITUACOES),
			"description": "Situação consolidada do associado no período.",
		},
		"com_pendencia": {
			"type": "boolean",
			"description": "Atalho para situação Atrasado ou Parcial.",
		},
		"acao_cadastro": {
			"type": "string",
			"enum": list(ACOES_CADASTRO),
			"description": "Pendência de cadastro da cobrança.",
		},
		"secao": {"type": "string", "description": "Seção do associado."},
		"categoria": {
			"type": "string",
			"enum": list(servico.CATEGORIAS_CONTRIBUINTES),
			"description": "Categoria do associado (Dirigente não contribui).",
		},
		"busca": {"type": "string", "description": "Parte do nome do associado."},
		"incluir_meses": {
			"type": "boolean",
			"default": False,
			"description": "Inclui a grade mês a mês de cada associado (resposta bem maior).",
		},
		"limite": {
			"type": "integer",
			"default": 25,
			"minimum": 1,
			"maximum": 100,
			"description": "Associados por página (máx. 100).",
		},
		"inicio": {"type": "integer", "default": 0, "minimum": 0, "description": "Deslocamento."},
	},
	roles=ROLES_LEITURA,
)
def apuracao_contribuicoes(
	meses: int = servico.MESES_PADRAO,
	situacao: str | None = None,
	com_pendencia: bool | None = None,
	acao_cadastro: str | None = None,
	secao: str | None = None,
	categoria: str | None = None,
	busca: str | None = None,
	incluir_meses: bool = False,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	dados = _apurar(meses)
	associados = dados.get("associados") or []

	if situacao:
		associados = [a for a in associados if a.get("situacao") == situacao]
	if com_pendencia:
		pendentes = (servico.STATUS_ATRASADO, servico.STATUS_PARCIAL)
		associados = [a for a in associados if a.get("situacao") in pendentes]
	if acao_cadastro:
		associados = [a for a in associados if a.get("acao_cadastro") == acao_cadastro]
	if secao:
		associados = [a for a in associados if a.get("secao") == secao]
	if categoria:
		associados = [a for a in associados if a.get("categoria") == categoria]
	if busca:
		termo = busca.strip().lower()
		associados = [a for a in associados if termo in (a.get("nome") or "").lower()]

	limite = normalizar_limite(limite)
	inicio = max(0, int(inicio or 0))
	pagina = [dict(associado) for associado in associados[inicio : inicio + limite]]
	if not incluir_meses:
		for associado in pagina:
			associado.pop("linhas", None)

	return {
		"periodo": dados.get("periodo"),
		"meses": dados.get("meses") if incluir_meses else None,
		"associados": pagina,
		"paginacao": {
			"inicio": inicio,
			"limite": limite,
			"retornados": len(pagina),
			"total_com_filtros": len(associados),
			"total_contribuintes": len(dados.get("associados") or []),
		},
	}


@ferramenta(
	nome="extrato_contribuicoes_associado",
	titulo="Extrato de contribuições do associado",
	descricao=(
		"Transações de contribuição mensal atribuídas a um associado no período, da mais "
		"recente para a mais antiga, com data de competência, valor, método e carteira."
	),
	parametros={
		"associado": {"type": "string", "description": "CPF do associado (identificador)."},
		"meses": PARAMETRO_MESES,
	},
	obrigatorios=("associado",),
	roles=ROLES_LEITURA,
)
def extrato_contribuicoes_associado(associado: str, meses: int = servico.MESES_PADRAO) -> dict:
	if not frappe.db.exists("Associado", associado):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Nenhum associado com o CPF '{associado}'.")

	resposta = servico.get_extrato_do_associado(associado, meses)
	transacoes = resposta.get("transacoes") or []
	return {
		"associado": associado,
		"transacoes": transacoes,
		"total_recebido": flt(sum(t.get("valor") or 0 for t in transacoes), 2),
		"quantidade": len(transacoes),
	}


@ferramenta(
	nome="listar_contribuicoes_nao_vinculadas",
	titulo="Contribuições sem associado",
	descricao=(
		"Transações de contribuição mensal que entraram na conta mas ainda não foram "
		"atribuídas a ninguém — elas contam no total recebido, mas não na apuração de "
		"cada associado. Para resolver, use 'categorizar_transacoes' informando "
		"beneficiario (e categoria 'Contribuição Mensal', se ainda não estiver)."
	),
	parametros={
		"meses": PARAMETRO_MESES,
		"limite": {
			"type": "integer",
			"default": 25,
			"minimum": 1,
			"maximum": 100,
			"description": "Transações por página (máx. 100).",
		},
		"inicio": {"type": "integer", "default": 0, "minimum": 0, "description": "Deslocamento."},
	},
	roles=ROLES_LEITURA,
)
def listar_contribuicoes_nao_vinculadas(
	meses: int = servico.MESES_PADRAO, limite: int = 25, inicio: int = 0
) -> dict:
	dados = _apurar(meses)
	transacoes = dados.get("nao_vinculadas") or []

	limite = normalizar_limite(limite)
	inicio = max(0, int(inicio or 0))
	pagina = transacoes[inicio : inicio + limite]

	return {
		"periodo": dados.get("periodo"),
		"transacoes": pagina,
		"valor_total_nao_vinculado": (dados.get("totais") or {}).get("recebido_nao_vinculado"),
		"paginacao": {
			"inicio": inicio,
			"limite": limite,
			"retornados": len(pagina),
			"total": len(transacoes),
		},
	}


@ferramenta(
	nome="atualizar_cobranca_associado",
	titulo="Atualizar cobrança do associado",
	descricao=(
		"Ajusta os dados de cobrança de um associado: valor da contribuição mensal, situação "
		"da cobrança (Ativo/Inativo) e contatos de cobrança. Informe ao menos um campo. "
		"Use 'apuracao_contribuicoes' com acao_cadastro para saber quem precisa de ajuste."
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
	solicitado: dict[str, Any] = {
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
