"""Ferramentas MCP da contribuição mensal.

A apuração é a de ``gris.api.financeiro.pagamentos_contribuicao``: a fonte de
verdade voltou a ser o DocType ``Pagamento Contribuicao Mensal`` — um registro
por associado e mês, com status (Pago/Em Aberto/Atrasado), valor e a transação
do extrato que quitou (`transacao_extrato`). Sem carência de registro, valor de
atraso escalonado ou crédito retroativo: o que está gravado no registro é o que
a apuração mostra, editável por 'definir_pagamento_mensal' e
'atualizar_pagamento_contribuicao_mensal'.

Quando um único pagamento quita mais de um mês (ex.: R$ 70 do mês em atraso +
R$ 60 do mês em dia), use 'definir_competencias_transacao' na transação — ao
salvar, um Pagamento Contribuicao Mensal é criado/atualizado por mês declarado,
vinculado a ela. 'competencias_transacao' lê o que já está declarado.
"""

from __future__ import annotations

import re
from typing import Any

import frappe
from frappe.utils import flt

from gris.api.financeiro import contribuicoes as transacoes_servico
from gris.api.financeiro import pagamentos_contribuicao as servico
from gris.api.mcp.registry import ErroDeFerramenta, ferramenta, normalizar_limite

PADRAO_COMPETENCIA_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

ROLES_LEITURA = ("Gestor Contribuição Mensal", "Visualizador Contribuição Mensal")
ROLES_ESCRITA = ("Gestor Contribuição Mensal",)

SITUACOES = (
	servico.STATUS_ATRASADO,
	servico.STATUS_EM_ABERTO,
	servico.STATUS_PAGO,
	servico.STATUS_NAO_GERADO,
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
		"A apuração vem do registro de cobrança (Pagamento Contribuicao Mensal)."
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
		"Situação de cada contribuinte no período: esperado, recebido, saldo e situação "
		"(Atrasado, Em Aberto, Pago, Não gerado — quando o mês ainda não tem registro). "
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
			"description": "Atalho para situação Atrasado ou Em Aberto.",
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
			"description": "Categoria do associado (Dirigente e Escotista não contribuem).",
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
		pendentes = (servico.STATUS_ATRASADO, servico.STATUS_EM_ABERTO)
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


@ferramenta(
	nome="competencias_transacao",
	titulo="Meses cobertos por uma transação de contribuição",
	descricao=(
		"Mostra os meses declarados numa transação de contribuição mensal que cobre mais de "
		"um mês (ex.: R$ 70 do mês atrasado + R$ 60 do mês em dia). Lista vazia significa que "
		"a transação não tem detalhamento e segue o comportamento padrão (mês de competência "
		"com o valor cheio)."
	),
	parametros={"transacao": {"type": "string", "description": "ID da 'Transacao Extrato Geral' (name)."}},
	obrigatorios=("transacao",),
	roles=ROLES_LEITURA,
)
def competencias_transacao(transacao: str) -> dict:
	if not frappe.db.exists("Transacao Extrato Geral", transacao):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Nenhuma transação com o ID '{transacao}'.")
	return transacoes_servico.get_competencias_transacao(transacao)


@ferramenta(
	nome="definir_competencias_transacao",
	titulo="Definir meses cobertos por uma transação de contribuição",
	descricao=(
		"Declara quais meses uma transação de contribuição mensal quita e quanto de cada — "
		"use quando um único pagamento cobre mais de um mês, por exemplo R$ 70 do mês em "
		"atraso mais R$ 60 do mês em dia. A soma dos valores precisa bater com o valor da "
		"transação. A transação precisa ter categoria 'Contribuição Mensal' e beneficiário "
		"definido (use 'categorizar_transacoes' antes, se preciso). Uma lista vazia remove o "
		"detalhamento. Ao salvar, o(s) Pagamento Contribuicao Mensal correspondente(s) são "
		"criados ou atualizados como 'Pago' e vinculados a esta transação."
	),
	parametros={
		"transacao": {"type": "string", "description": "ID da 'Transacao Extrato Geral' (name)."},
		"competencias": {
			"type": "array",
			"maxItems": 24,
			"description": (
				'Lista de meses cobertos: [{"mes": "AAAA-MM", "valor": 70, '
				'"em_atraso": true}, {"mes": "AAAA-MM", "valor": 60, "em_atraso": false}]. '
				"Lista vazia remove o detalhamento."
			),
		},
	},
	obrigatorios=("transacao", "competencias"),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def definir_competencias_transacao(transacao: str, competencias: list, simular: bool = False) -> dict:
	if not frappe.db.exists("Transacao Extrato Geral", transacao):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Nenhuma transação com o ID '{transacao}'.")

	itens = competencias if isinstance(competencias, list) else []
	if any(not isinstance(item, dict) for item in itens):
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			"Cada item de 'competencias' precisa ser um objeto com 'mes', 'valor' e 'em_atraso'.",
		)

	antes = transacoes_servico.get_competencias_transacao(transacao)

	if simular:
		try:
			doc = frappe.get_doc("Transacao Extrato Geral", transacao)
			doc.check_permission("write")
		except frappe.PermissionError as erro:
			raise ErroDeFerramenta("PERMISSAO_NEGADA", str(erro)) from erro
		return {
			"simulacao": True,
			"transacao": transacao,
			"antes": antes["competencias"],
			"depois": itens,
		}

	try:
		resultado = transacoes_servico.definir_competencias_transacao(transacao, itens)
	except frappe.PermissionError as erro:
		raise ErroDeFerramenta("PERMISSAO_NEGADA", str(erro)) from erro
	except frappe.ValidationError as erro:
		raise ErroDeFerramenta("VALIDACAO", str(erro)) from erro

	return {"transacao": transacao, "antes": antes["competencias"], "depois": resultado["competencias"]}


CAMPOS_PAGAMENTO_MENSAL = ("status", "valor", "atrasou", "transacao_extrato")


@ferramenta(
	nome="definir_pagamento_mensal",
	titulo="Definir o pagamento de um mês (cria se não existir)",
	descricao=(
		"Cria ou atualiza o Pagamento Contribuicao Mensal de um associado num mês, por "
		"associado + mês — não é preciso saber o 'name' do registro. Use quando o mês ainda "
		"não tem registro gerado ('Não gerado' na apuração/tela) e precisa ser criado direto, "
		"por exemplo para marcar como Pago e vincular a transação que quitou."
	),
	parametros={
		"associado": {"type": "string", "description": "CPF do associado."},
		"mes": {"type": "string", "description": "Mês de referência, formato AAAA-MM."},
		"status": {"type": "string", "enum": ["Pago", "Em Aberto", "Atrasado"]},
		"valor": {
			"type": "number",
			"description": "Valor do mês (padrão: valor_contribuicao do associado, se novo).",
		},
		"atrasou": {"type": "boolean", "description": "Se este mês foi pago em atraso."},
		"transacao_extrato": {
			"type": "string",
			"description": "ID da 'Transacao Extrato Geral' que quitou este mês.",
		},
	},
	obrigatorios=("associado", "mes"),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def definir_pagamento_mensal(
	associado: str,
	mes: str,
	status: str | None = None,
	valor: float | None = None,
	atrasou: bool | None = None,
	transacao_extrato: str | None = None,
	simular: bool = False,
) -> dict:
	if not frappe.db.exists("Associado", associado):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Nenhum associado com o CPF '{associado}'.")
	if not PADRAO_COMPETENCIA_MES.match(mes or ""):
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Mês inválido. Use o formato AAAA-MM.")
	if transacao_extrato and not frappe.db.exists("Transacao Extrato Geral", transacao_extrato):
		raise ErroDeFerramenta(
			"NAO_ENCONTRADO",
			f"Nenhuma transação com o ID '{transacao_extrato}'.",
			{"campo": "transacao_extrato"},
		)

	existente = frappe.db.get_value(
		"Pagamento Contribuicao Mensal",
		{"associado": associado, "mes_de_referencia": f"{mes}-01"},
		list(CAMPOS_PAGAMENTO_MENSAL),
		as_dict=True,
	)

	if simular:
		return {
			"simulacao": True,
			"associado": associado,
			"mes": mes,
			"existia": existente is not None,
			"antes": existente or {},
			"depois": {
				"status": status,
				"valor": valor,
				"atrasou": atrasou,
				"transacao_extrato": transacao_extrato,
			},
		}

	from gris.api.financeiro import monthly_payments

	try:
		resultado = monthly_payments.definir_pagamento(
			associado,
			f"{mes}-01",
			status=status,
			valor=valor,
			atrasou=atrasou,
			transacao_extrato=transacao_extrato,
		)
	except frappe.PermissionError as erro:
		raise ErroDeFerramenta("PERMISSAO_NEGADA", str(erro)) from erro
	except frappe.ValidationError as erro:
		raise ErroDeFerramenta("VALIDACAO", str(erro)) from erro

	return {"associado": associado, "mes": mes, "existia": existente is not None, **resultado}


@ferramenta(
	nome="listar_pagamentos_contribuicao_mensal",
	titulo="Listar registros de cobrança da contribuição mensal",
	descricao=(
		"Lista os registros do DocType 'Pagamento Contribuicao Mensal' (fluxo de cobrança e "
		"vínculo com a transação que quitou cada mês). Para a apuração de quanto foi pago e "
		"quanto falta, use 'apuracao_contribuicoes' — este DocType é o registro de cobrança, "
		"não a fonte de verdade do que entrou."
	),
	parametros={
		"associado": {"type": "string", "description": "CPF do associado."},
		"status": {"type": "string", "enum": ["Pago", "Em Aberto", "Atrasado"]},
		"limite": {"type": "integer", "default": 25, "minimum": 1, "maximum": 100},
		"inicio": {"type": "integer", "default": 0, "minimum": 0},
	},
	roles=ROLES_LEITURA,
)
def listar_pagamentos_contribuicao_mensal(
	associado: str | None = None,
	status: str | None = None,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict[str, Any] = {}
	if associado:
		filtros["associado"] = associado
	if status:
		filtros["status"] = status

	limite = normalizar_limite(limite)
	inicio = max(0, int(inicio or 0))

	registros = frappe.get_all(
		"Pagamento Contribuicao Mensal",
		filters=filtros,
		fields=["name", "associado", "status", "mes_de_referencia", "valor", "atrasou", "transacao_extrato"],
		order_by="mes_de_referencia desc",
		limit_page_length=limite,
		limit_start=inicio,
	)
	total = frappe.db.count("Pagamento Contribuicao Mensal", filters=filtros)

	return {
		"pagamentos": registros,
		"paginacao": {"inicio": inicio, "limite": limite, "retornados": len(registros), "total": total},
	}


@ferramenta(
	nome="atualizar_pagamento_contribuicao_mensal",
	titulo="Atualizar registro de cobrança da contribuição mensal",
	descricao=(
		"Ajusta um registro do DocType 'Pagamento Contribuicao Mensal': status, valor, se foi em "
		"atraso e a transação do extrato que o quitou. Informe ao menos um campo."
	),
	parametros={
		"name": {
			"type": "string",
			"description": "Nome do registro (retornado por 'listar_pagamentos_contribuicao_mensal').",
		},
		"status": {"type": "string", "enum": ["Pago", "Em Aberto", "Atrasado"]},
		"valor": {"type": "number", "description": "Novo valor do mês."},
		"atrasou": {"type": "boolean", "description": "Se este mês foi pago em atraso."},
		"transacao_extrato": {
			"type": "string",
			"description": "ID da 'Transacao Extrato Geral' que quitou este mês (vazio para desvincular).",
		},
	},
	obrigatorios=("name",),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def atualizar_pagamento_contribuicao_mensal(
	name: str,
	status: str | None = None,
	valor: float | None = None,
	atrasou: bool | None = None,
	transacao_extrato: str | None = None,
	simular: bool = False,
) -> dict:
	if not frappe.db.exists("Pagamento Contribuicao Mensal", name):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Nenhum registro de pagamento com o nome '{name}'.")

	solicitado: dict[str, Any] = {}
	if status is not None:
		solicitado["status"] = status
	if valor is not None:
		if flt(valor) < 0:
			raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "O valor não pode ser negativo.")
		solicitado["valor"] = flt(valor)
	if atrasou is not None:
		solicitado["atrasou"] = 1 if atrasou else 0
	if transacao_extrato is not None:
		if transacao_extrato and not frappe.db.exists("Transacao Extrato Geral", transacao_extrato):
			raise ErroDeFerramenta(
				"NAO_ENCONTRADO",
				f"Nenhuma transação com o ID '{transacao_extrato}'.",
				{"campo": "transacao_extrato"},
			)
		solicitado["transacao_extrato"] = transacao_extrato or None

	if not solicitado:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			"Informe ao menos um campo para atualizar.",
			{"campos_aceitos": list(CAMPOS_PAGAMENTO_MENSAL)},
		)

	atuais = frappe.db.get_value(
		"Pagamento Contribuicao Mensal", name, list(CAMPOS_PAGAMENTO_MENSAL), as_dict=True
	)
	alteracoes = {
		campo: {"de": atuais.get(campo), "para": valor}
		for campo, valor in solicitado.items()
		if atuais.get(campo) != valor
	}
	if not alteracoes:
		return {"atualizado": False, "motivo": "Nenhum valor diferente do atual.", "alteracoes": {}}

	if simular:
		return {"simulacao": True, "atualizado": False, "name": name, "alteracoes": alteracoes}

	doc = frappe.get_doc("Pagamento Contribuicao Mensal", name)
	try:
		doc.check_permission("write")
	except frappe.PermissionError as erro:
		raise ErroDeFerramenta("PERMISSAO_NEGADA", str(erro)) from erro
	for campo, valor in solicitado.items():
		doc.set(campo, valor)
	doc.save()

	return {"atualizado": True, "name": name, "alteracoes": alteracoes}
