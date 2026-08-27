"""Ferramentas MCP de conciliação entre transações de Sistema e de Planilha.

A regra de negócio (vínculo recíproco, quem conta no total, categorização do
registro mantido) vive em ``gris.api.financeiro.conciliacao``. Aqui expomos a
fila de pendentes, os candidatos ranqueados e as ações, com simulação.

O ganho de usar o Claude aqui é o casamento por descrição: o ranking do serviço
ordena por valor e data e mede similaridade por sobreposição de palavras — o
modelo lê "PIX RECEBIDO M S SILVA" e reconhece "Contribuição Ago/Mariana Silva".
"""

from __future__ import annotations

from typing import Any

import frappe

from gris.api.financeiro import conciliacao as servico
from gris.api.mcp.registry import ErroDeFerramenta, ferramenta, normalizar_limite

DOCTYPE = "Transacao Extrato Geral"

# Conciliar altera totais: o serviço exige permissão de escrita no doctype,
# então mesmo a leitura da fila fica restrita ao Gestor Financeiro.
ROLES = ("Gestor Financeiro",)

CAMPOS_CATEGORIZACAO = {
	"categoria": "Categoria de Transacao",
	"centro_de_custo": "Centro de Custo",
	"descricao_reduzida": None,
	"ordinaria_extraordinaria": None,
}

PARAMETROS_CATEGORIZACAO = {
	"categoria": {"type": "string", "description": "Categoria a aplicar no registro mantido."},
	"centro_de_custo": {"type": "string", "description": "Centro de custo do registro mantido."},
	"descricao_reduzida": {"type": "string", "description": "Descrição amigável do registro mantido."},
	"ordinaria_extraordinaria": {
		"type": "string",
		"enum": ["Ordinária", "Extraordinária"],
		"description": "Classificação do registro mantido.",
	},
}


def _categorizacao(**valores) -> dict:
	"""Mantém só os campos de categorização informados e valida os links."""
	informados = {campo: valor for campo, valor in valores.items() if valor}
	for campo, doctype_link in CAMPOS_CATEGORIZACAO.items():
		valor = informados.get(campo)
		if doctype_link and valor and not frappe.db.exists(doctype_link, valor):
			raise ErroDeFerramenta(
				"NAO_ENCONTRADO",
				f"'{valor}' não existe em {doctype_link}. Consulte 'listar_opcoes_financeiras'.",
				{"campo": campo, "doctype": doctype_link},
			)
	return informados


def _carregar(transacao_id: str) -> dict:
	dados = frappe.db.get_value(
		DOCTYPE,
		transacao_id,
		[
			"name",
			"fonte",
			"descricao",
			"descricao_reduzida",
			"valor",
			"debito_credito",
			"data_deposito",
			"timestamp_transacao",
			"carteira",
			"categoria",
			"centro_de_custo",
			"status_conciliacao",
			"transacao_conciliada",
			"excluir_do_total",
		],
		as_dict=True,
	)
	if dados is None:
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Transação '{transacao_id}' não encontrada.")
	return dados


@ferramenta(
	nome="listar_pendentes_conciliacao",
	titulo="Listar pendências de conciliação",
	descricao=(
		"Lista as transações de fonte 'Sistema' que ainda não foram conciliadas com a planilha. "
		"É o ponto de partida: para cada pendência, use 'sugerir_candidatos_conciliacao'."
	),
	parametros={
		"carteira": {"type": "string", "description": "Filtra por carteira."},
		"instituicao": {"type": "string", "description": "Filtra por instituição financeira."},
		"limite": {
			"type": "integer",
			"default": 25,
			"minimum": 1,
			"maximum": 100,
			"description": "Quantidade de pendências (máx. 100).",
		},
	},
	roles=ROLES,
)
def listar_pendentes_conciliacao(
	carteira: str | None = None,
	instituicao: str | None = None,
	limite: int = 25,
) -> dict:
	pendentes = servico.get_sistema_pendentes(
		carteira=carteira, instituicao=instituicao, limit=normalizar_limite(limite)
	)
	return {"pendentes": pendentes, "retornados": len(pendentes)}


@ferramenta(
	nome="sugerir_candidatos_conciliacao",
	titulo="Sugerir candidatos para conciliação",
	descricao=(
		"Para uma transação de sistema, retorna as transações de planilha compatíveis "
		"(valor próximo em ±R$1 e data dentro de 5 dias), ordenadas por proximidade. "
		"Compare as descrições e escolha o par antes de chamar 'conciliar_transacoes'; "
		"quando nenhum candidato for a mesma transação, use 'marcar_sem_duplicata'."
	),
	parametros={
		"transacao_id": {
			"type": "string",
			"description": "ID da transação de sistema ('name' da pendência).",
		},
		"limite": {
			"type": "integer",
			"default": 10,
			"minimum": 1,
			"maximum": 50,
			"description": "Quantos candidatos retornar.",
		},
	},
	obrigatorios=("transacao_id",),
	roles=ROLES,
)
def sugerir_candidatos_conciliacao(transacao_id: str, limite: int = 10) -> dict:
	resultado = servico.get_candidatos_planilha(transacao_id)

	candidatos = []
	for item in (resultado.get("candidatos") or [])[: max(1, int(limite))]:
		item = dict(item)
		item["similaridade_descricao"] = round(item.pop("_score", 0.0), 3)
		item["diferenca_valor"] = round(item.pop("_diff_valor", 0.0), 2)
		candidatos.append(item)

	return {
		"sistema": resultado.get("sistema"),
		"candidatos": candidatos,
		"total_candidatos": len(resultado.get("candidatos") or []),
		"tolerancias": {"valor": servico.TOLERANCIA_VALOR, "dias": servico.JANELA_DIAS},
	}


@ferramenta(
	nome="conciliar_transacoes",
	titulo="Conciliar par de transações",
	descricao=(
		"Vincula uma transação de sistema a uma de planilha (mesma transação real registrada "
		"duas vezes), define qual das duas continua contando nos totais e, opcionalmente, "
		"categoriza o registro mantido. Use simular=true para conferir antes."
	),
	parametros={
		"sistema_id": {"type": "string", "description": "ID da transação de fonte Sistema."},
		"planilha_id": {"type": "string", "description": "ID da transação de fonte Planilha."},
		"manter": {
			"type": "string",
			"enum": ["sistema", "planilha"],
			"default": "sistema",
			"description": "Qual registro permanece nos totais.",
		},
		**PARAMETROS_CATEGORIZACAO,
	},
	obrigatorios=("sistema_id", "planilha_id"),
	roles=ROLES,
	somente_leitura=False,
)
def conciliar_transacoes(
	sistema_id: str,
	planilha_id: str,
	manter: str = "sistema",
	categoria: str | None = None,
	centro_de_custo: str | None = None,
	descricao_reduzida: str | None = None,
	ordinaria_extraordinaria: str | None = None,
	simular: bool = False,
) -> dict:
	if sistema_id == planilha_id:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Não é possível conciliar uma transação com ela mesma.")

	valores = _categorizacao(
		categoria=categoria,
		centro_de_custo=centro_de_custo,
		descricao_reduzida=descricao_reduzida,
		ordinaria_extraordinaria=ordinaria_extraordinaria,
	)

	sistema = _carregar(sistema_id)
	planilha = _carregar(planilha_id)

	for transacao in (sistema, planilha):
		par = transacao.get("transacao_conciliada")
		if transacao.get("status_conciliacao") == "Conciliada" and par not in (
			sistema_id,
			planilha_id,
			None,
			"",
		):
			raise ErroDeFerramenta(
				"VALIDACAO",
				f"A transação {transacao['name']} já está conciliada com {par}. "
				"Use 'desfazer_conciliacao' antes de refazer o vínculo.",
			)

	mantido, excluido = (sistema, planilha) if manter == "sistema" else (planilha, sistema)

	if simular:
		return {
			"simulacao": True,
			"conciliado": False,
			"mantido": mantido["name"],
			"excluido_do_total": excluido["name"],
			"categorizacao_aplicada": valores,
			"transacoes": {"sistema": sistema, "planilha": planilha},
		}

	resultado = servico.conciliar(
		sistema_id=sistema_id,
		planilha_id=planilha_id,
		manter=manter,
		**valores,
	)

	return {
		"conciliado": True,
		"mantido": resultado.get("mantido"),
		"excluido_do_total": resultado.get("excluido"),
		"categorizacao_aplicada": valores,
	}


@ferramenta(
	nome="marcar_sem_duplicata",
	titulo="Resolver pendência sem par",
	descricao=(
		"Marca uma transação de sistema como resolvida sem duplicata na planilha: ela sai da "
		"fila de pendentes, continua contando nos totais e fica marcada como revisada. "
		"Aceita categorização opcional."
	),
	parametros={
		"sistema_id": {"type": "string", "description": "ID da transação de fonte Sistema."},
		**PARAMETROS_CATEGORIZACAO,
	},
	obrigatorios=("sistema_id",),
	roles=ROLES,
	somente_leitura=False,
)
def marcar_sem_duplicata(
	sistema_id: str,
	categoria: str | None = None,
	centro_de_custo: str | None = None,
	descricao_reduzida: str | None = None,
	ordinaria_extraordinaria: str | None = None,
	simular: bool = False,
) -> dict:
	valores = _categorizacao(
		categoria=categoria,
		centro_de_custo=centro_de_custo,
		descricao_reduzida=descricao_reduzida,
		ordinaria_extraordinaria=ordinaria_extraordinaria,
	)
	transacao = _carregar(sistema_id)

	if simular:
		return {
			"simulacao": True,
			"resolvido": False,
			"transacao": transacao,
			"categorizacao_aplicada": valores,
		}

	resultado = servico.marcar_sem_duplicata(sistema_id=sistema_id, **valores)
	return {"resolvido": resultado.get("resolvido"), "categorizacao_aplicada": valores}


@ferramenta(
	nome="desfazer_conciliacao",
	titulo="Desfazer conciliação",
	descricao=(
		"Desfaz o vínculo de uma conciliação: os dois registros voltam a contar nos totais e "
		"retornam à fila de pendentes."
	),
	parametros={
		"transacao_id": {
			"type": "string",
			"description": "ID de qualquer uma das duas transações conciliadas.",
		},
	},
	obrigatorios=("transacao_id",),
	roles=ROLES,
	somente_leitura=False,
)
def desfazer_conciliacao(transacao_id: str, simular: bool = False) -> dict:
	transacao = _carregar(transacao_id)
	par = transacao.get("transacao_conciliada")

	if transacao.get("status_conciliacao") != "Conciliada":
		raise ErroDeFerramenta("VALIDACAO", f"A transação {transacao_id} não está conciliada.")

	if simular:
		afetadas: list[Any] = [transacao_id]
		if par:
			afetadas.append(par)
		return {"simulacao": True, "desfeito": False, "seriam_desconciliadas": afetadas}

	resultado = servico.desconciliar(transacao_id)
	return {"desfeito": True, "desconciliadas": resultado.get("desconciliados", [])}
