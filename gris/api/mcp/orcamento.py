"""Ferramentas MCP da previsão orçamentária.

Envolve ``gris.api.financeiro.previsao_orcamentaria``: leitura das previsões,
comparativo previsto vs. realizado e edição de itens, com simulação nas escritas.
"""

from __future__ import annotations

from typing import Any

import frappe

from gris.api.financeiro import previsao_orcamentaria as servico
from gris.api.mcp.registry import ErroDeFerramenta, ferramenta

DOCTYPE = "Previsao Orcamentaria"

ROLES_LEITURA = ("Gestor Financeiro", "Visualizador Financeiro")
ROLES_ESCRITA = ("Gestor Financeiro",)

STATUS_VALIDOS = ("Rascunho", "Aprovada", "Encerrada")
TIPOS_ITEM = ("Receita", "Despesa")
DISTRIBUICOES = (servico.DISTRIBUICAO_UNIFORME, servico.DISTRIBUICAO_MES_ESPECIFICO)


def _garantir_previsao(name: str) -> dict:
	dados = frappe.db.get_value(DOCTYPE, name, ["name", "titulo", "status"], as_dict=True)
	if dados is None:
		raise ErroDeFerramenta(
			"NAO_ENCONTRADO",
			f"Previsão '{name}' não encontrada. Use 'listar_previsoes_orcamentarias'.",
		)
	return dados


def _recusar_encerrada(previsao: dict) -> None:
	if previsao.get("status") == "Encerrada":
		raise ErroDeFerramenta("VALIDACAO", "Não é possível alterar itens de uma previsão encerrada.")


@ferramenta(
	nome="listar_previsoes_orcamentarias",
	titulo="Listar previsões orçamentárias",
	descricao=(
		"Lista as previsões orçamentárias cadastradas, mais recentes primeiro, com totais "
		"previstos de receita, despesa e resultado."
	),
	parametros={
		"exercicio": {"type": "integer", "description": "Ano do exercício (ex.: 2026)."},
		"status": {
			"type": "string",
			"enum": list(STATUS_VALIDOS),
			"description": "Situação da previsão.",
		},
	},
	roles=ROLES_LEITURA,
)
def listar_previsoes_orcamentarias(exercicio: int | None = None, status: str | None = None) -> dict:
	previsoes = servico.listar_previsoes(exercicio=exercicio, status=status)
	return {"previsoes": previsoes, "total": len(previsoes)}


@ferramenta(
	nome="obter_previsao_orcamentaria",
	titulo="Detalhar previsão orçamentária",
	descricao="Retorna uma previsão com todos os seus itens de receita e despesa.",
	parametros={"name": {"type": "string", "description": "Identificador da previsão."}},
	obrigatorios=("name",),
	roles=ROLES_LEITURA,
)
def obter_previsao_orcamentaria(name: str) -> dict:
	_garantir_previsao(name)
	return {"previsao": servico.obter_previsao(name)}


@ferramenta(
	nome="comparar_previsto_realizado",
	titulo="Comparar previsto e realizado",
	descricao=(
		"Compara o orçamento previsto com o realizado do extrato no período da previsão: "
		"totais, desvios, percentual de execução (medido contra o previsto até o mês corrente) "
		"e quebras por categoria e centro de custo."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da previsão."},
		"incluir_series_mensais": {
			"type": "boolean",
			"default": False,
			"description": "Inclui a evolução mês a mês (resposta bem maior).",
		},
	},
	obrigatorios=("name",),
	roles=ROLES_LEITURA,
)
def comparar_previsto_realizado(name: str, incluir_series_mensais: bool = False) -> dict:
	_garantir_previsao(name)
	comparativo = servico.obter_comparativo(name)

	resultado: dict[str, Any] = {
		"previsao": comparativo.get("previsao"),
		"meses_decorridos": comparativo.get("meses_decorridos"),
		# Mês em que a base do comparativo é cortada: os desvios de `totais` e das quebras
		# medem o realizado contra o previsto até aqui, não contra o do período inteiro.
		"mes_corte": comparativo.get("mes_corte"),
		"totais": comparativo.get("totais"),
		"por_categoria": comparativo.get("por_categoria"),
		"por_centro_de_custo": comparativo.get("por_centro_de_custo"),
	}

	if incluir_series_mensais:
		series = comparativo.get("series") or {}
		labels = comparativo.get("labels") or []
		resultado["por_mes"] = [
			{
				"mes": mes,
				**{nome: valores[indice] for nome, valores in series.items() if indice < len(valores)},
			}
			for indice, mes in enumerate(labels)
		]

	return resultado


@ferramenta(
	nome="criar_previsao_orcamentaria",
	titulo="Criar previsão orçamentária",
	descricao=(
		"Cria uma previsão orçamentária, opcionalmente já com os itens. Cada item aceita "
		"tipo (Receita/Despesa), descrição, valor_previsto, categoria, centro_de_custo, "
		"distribuicao e mes_referencia."
	),
	parametros={
		"titulo": {"type": "string", "description": "Nome da previsão (ex.: 'Orçamento 2027')."},
		"exercicio": {"type": "integer", "description": "Ano do exercício."},
		"data_inicio": {"type": "string", "description": "Início do período (AAAA-MM-DD)."},
		"data_fim": {"type": "string", "description": "Fim do período (AAAA-MM-DD)."},
		"status": {
			"type": "string",
			"enum": list(STATUS_VALIDOS),
			"default": "Rascunho",
			"description": "Situação inicial.",
		},
		"centro_de_custo": {"type": "string", "description": "Restringe a previsão a um centro de custo."},
		"observacoes": {"type": "string", "description": "Observações gerais."},
		"itens": {
			"type": "array",
			"maxItems": 200,
			"description": "Lista de itens da previsão (objetos).",
		},
	},
	obrigatorios=("titulo", "exercicio", "data_inicio", "data_fim"),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def criar_previsao_orcamentaria(
	titulo: str,
	exercicio: int,
	data_inicio: str,
	data_fim: str,
	status: str = "Rascunho",
	centro_de_custo: str | None = None,
	observacoes: str | None = None,
	itens: list | None = None,
	simular: bool = False,
) -> dict:
	if str(data_inicio) > str(data_fim):
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "'data_inicio' não pode ser maior que 'data_fim'.")
	if centro_de_custo and not frappe.db.exists("Centro de Custo", centro_de_custo):
		raise ErroDeFerramenta("NAO_ENCONTRADO", f"Centro de custo '{centro_de_custo}' não existe.")

	itens = itens or []
	resumo = {
		"titulo": titulo,
		"exercicio": exercicio,
		"periodo": {"inicio": data_inicio, "fim": data_fim},
		"status": status,
		"centro_de_custo": centro_de_custo,
		"quantidade_de_itens": len(itens),
	}

	if simular:
		return {"simulacao": True, "criada": False, "previsao": resumo, "itens": itens}

	resultado = servico.criar_previsao(
		titulo=titulo,
		exercicio=exercicio,
		data_inicio=data_inicio,
		data_fim=data_fim,
		status=status,
		centro_de_custo=centro_de_custo,
		observacoes=observacoes,
		itens=itens,
	)
	return {"criada": True, "name": resultado.get("name"), "previsao": resumo}


@ferramenta(
	nome="atualizar_previsao_orcamentaria",
	titulo="Atualizar previsão orçamentária",
	descricao=(
		"Atualiza os dados gerais de uma previsão (título, período, status, centro de custo, "
		"observações). Não mexe nos itens — para isso use 'salvar_item_previsao'."
	),
	parametros={
		"name": {"type": "string", "description": "Identificador da previsão."},
		"titulo": {"type": "string", "description": "Novo título."},
		"exercicio": {"type": "integer", "description": "Novo exercício."},
		"data_inicio": {"type": "string", "description": "Novo início (AAAA-MM-DD)."},
		"data_fim": {"type": "string", "description": "Novo fim (AAAA-MM-DD)."},
		"status": {
			"type": "string",
			"enum": list(STATUS_VALIDOS),
			"description": "Nova situação.",
		},
		"centro_de_custo": {"type": "string", "description": "Novo centro de custo."},
		"observacoes": {"type": "string", "description": "Novas observações."},
	},
	obrigatorios=("name",),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def atualizar_previsao_orcamentaria(
	name: str,
	titulo: str | None = None,
	exercicio: int | None = None,
	data_inicio: str | None = None,
	data_fim: str | None = None,
	status: str | None = None,
	centro_de_custo: str | None = None,
	observacoes: str | None = None,
	simular: bool = False,
) -> dict:
	_garantir_previsao(name)

	solicitado = {
		"titulo": titulo,
		"exercicio": exercicio,
		"data_inicio": data_inicio,
		"data_fim": data_fim,
		"status": status,
		"centro_de_custo": centro_de_custo,
		"observacoes": observacoes,
	}
	solicitado = {campo: valor for campo, valor in solicitado.items() if valor is not None}
	if not solicitado:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe ao menos um campo para atualizar.")

	atuais = frappe.db.get_value(DOCTYPE, name, list(solicitado), as_dict=True) or {}
	alteracoes = {
		campo: {"de": atuais.get(campo), "para": valor}
		for campo, valor in solicitado.items()
		if str(atuais.get(campo)) != str(valor)
	}
	if not alteracoes:
		return {"atualizada": False, "motivo": "Nenhum valor diferente do atual.", "alteracoes": {}}

	if simular:
		return {"simulacao": True, "atualizada": False, "name": name, "alteracoes": alteracoes}

	servico.atualizar_previsao(name=name, **solicitado)
	return {"atualizada": True, "name": name, "alteracoes": alteracoes}


@ferramenta(
	nome="salvar_item_previsao",
	titulo="Criar ou atualizar item da previsão",
	descricao=(
		"Cria um item na previsão ou atualiza um existente (informando item_name). "
		"Use distribuicao='Mês específico' com mes_referencia para lançar o valor em um único "
		"mês; 'Uniforme no período' divide o valor pelos meses da previsão."
	),
	parametros={
		"previsao": {"type": "string", "description": "Identificador da previsão."},
		"tipo": {
			"type": "string",
			"enum": list(TIPOS_ITEM),
			"description": "Receita ou Despesa.",
		},
		"descricao": {"type": "string", "description": "Descrição do item."},
		"valor_previsto": {"type": "number", "description": "Valor previsto no período."},
		"item_name": {
			"type": "string",
			"description": "Identificador do item a atualizar (omita para criar um novo).",
		},
		"categoria": {"type": "string", "description": "Categoria de Transacao vinculada."},
		"centro_de_custo": {"type": "string", "description": "Centro de Custo vinculado."},
		"distribuicao": {
			"type": "string",
			"enum": list(DISTRIBUICOES),
			"default": servico.DISTRIBUICAO_UNIFORME,
			"description": "Como o valor se distribui no período.",
		},
		"mes_referencia": {
			"type": "string",
			"description": "Mês do lançamento quando a distribuição for 'Mês específico' (AAAA-MM-DD).",
		},
		"observacoes": {"type": "string", "description": "Observações do item."},
	},
	obrigatorios=("previsao", "tipo", "descricao", "valor_previsto"),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def salvar_item_previsao(
	previsao: str,
	tipo: str,
	descricao: str,
	valor_previsto: float,
	item_name: str | None = None,
	categoria: str | None = None,
	centro_de_custo: str | None = None,
	distribuicao: str = servico.DISTRIBUICAO_UNIFORME,
	mes_referencia: str | None = None,
	observacoes: str | None = None,
	simular: bool = False,
) -> dict:
	doc_previsao = _garantir_previsao(previsao)
	_recusar_encerrada(doc_previsao)

	for campo, valor, doctype_link in (
		("categoria", categoria, "Categoria de Transacao"),
		("centro_de_custo", centro_de_custo, "Centro de Custo"),
	):
		if valor and not frappe.db.exists(doctype_link, valor):
			raise ErroDeFerramenta(
				"NAO_ENCONTRADO",
				f"'{valor}' não existe em {doctype_link}. Consulte 'listar_opcoes_financeiras'.",
				{"campo": campo, "doctype": doctype_link},
			)

	if distribuicao == servico.DISTRIBUICAO_MES_ESPECIFICO and not mes_referencia:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			f"Com distribuicao='{servico.DISTRIBUICAO_MES_ESPECIFICO}' informe 'mes_referencia'.",
		)

	item = {
		"tipo": tipo,
		"descricao": descricao,
		"valor_previsto": valor_previsto,
		"categoria": categoria,
		"centro_de_custo": centro_de_custo,
		"distribuicao": distribuicao,
		"mes_referencia": mes_referencia,
		"observacoes": observacoes,
	}
	operacao = "atualizacao" if item_name else "criacao"

	if simular:
		return {"simulacao": True, "salvo": False, "operacao": operacao, "item": item}

	servico.salvar_item(
		previsao=previsao,
		tipo=tipo,
		descricao=descricao,
		valor_previsto=valor_previsto,
		item_name=item_name,
		categoria=categoria,
		centro_de_custo=centro_de_custo,
		distribuicao=distribuicao,
		mes_referencia=mes_referencia,
		observacoes=observacoes,
	)
	return {"salvo": True, "operacao": operacao, "previsao": previsao, "item": item}


@ferramenta(
	nome="excluir_item_previsao",
	titulo="Excluir item da previsão",
	descricao="Remove um item de uma previsão orçamentária que não esteja encerrada.",
	parametros={
		"previsao": {"type": "string", "description": "Identificador da previsão."},
		"item_name": {"type": "string", "description": "Identificador do item a remover."},
	},
	obrigatorios=("previsao", "item_name"),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def excluir_item_previsao(previsao: str, item_name: str, simular: bool = False) -> dict:
	doc_previsao = _garantir_previsao(previsao)
	_recusar_encerrada(doc_previsao)

	detalhes = servico.obter_previsao(previsao)
	alvo = next((item for item in detalhes.get("itens", []) if item.get("name") == item_name), None)
	if alvo is None:
		raise ErroDeFerramenta(
			"NAO_ENCONTRADO", f"Item '{item_name}' não encontrado na previsão '{previsao}'."
		)

	if simular:
		return {"simulacao": True, "excluido": False, "item": alvo}

	servico.excluir_item(previsao=previsao, item_name=item_name)
	return {"excluido": True, "previsao": previsao, "item": alvo}
