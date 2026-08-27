"""Ferramentas MCP do módulo Financeiro (extrato geral)."""

from __future__ import annotations

import inspect
from typing import Any

import frappe
from frappe.utils import flt

from gris.api.mcp.registry import (
	ErroDeFerramenta,
	ferramenta,
	normalizar_limite,
)

DOCTYPE = "Transacao Extrato Geral"

ROLES_LEITURA = ("Gestor Financeiro", "Visualizador Financeiro")
ROLES_ESCRITA = ("Gestor Financeiro",)

# Somente o Gestor Financeiro enxerga a descrição bruta do extrato — mesmo
# critério da página /financeiro/extrato.
ROLE_DESCRICAO_COMPLETA = "Gestor Financeiro"

CAMPOS_LISTA = [
	"name",
	"descricao_reduzida",
	"valor",
	"debito_credito",
	"data_transacao",
	"data_deposito",
	"timestamp_transacao",
	"metodo",
	"instituicao",
	"carteira",
	"categoria",
	"centro_de_custo",
	"beneficiario",
	"conta_fixa",
	"fixo_variavel",
	"ordinaria_extraordinaria",
	"repasse_entre_contas",
	"transacao_revisada",
	"status_conciliacao",
	"excluir_do_total",
	"fonte",
]

# Campos que a categorização em lote pode gravar (espelha
# gris.api.financeiro.transactions.batch_update_transactions).
CAMPOS_CATEGORIZACAO = {
	"categoria": "Categoria de Transacao",
	"centro_de_custo": "Centro de Custo",
	"beneficiario": "Associado",
	"ordinaria_extraordinaria": None,
	"descricao_reduzida": None,
	"transacao_revisada": None,
}

# O beneficiário só faz sentido na contribuição mensal: é ele que liga a
# transação ao associado na apuração de gris.api.financeiro.contribuicoes.
CATEGORIA_CONTRIBUICAO = "Contribuição Mensal"

MAX_TRANSACOES_LOTE = 200

CAMPOS_DATA = ("data_deposito", "data_transacao", "timestamp_transacao")


def _pode_ver_descricao_completa() -> bool:
	papeis = set(frappe.get_roles(frappe.session.user))
	return ROLE_DESCRICAO_COMPLETA in papeis or "System Manager" in papeis


def _filtros_de_periodo(campo_data: str, data_inicio: str | None, data_fim: str | None) -> dict:
	if campo_data not in CAMPOS_DATA:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			f"campo_data inválido. Opções: {', '.join(CAMPOS_DATA)}.",
		)
	if data_inicio and data_fim:
		return {campo_data: ["between", [data_inicio, data_fim]]}
	if data_inicio:
		return {campo_data: [">=", data_inicio]}
	if data_fim:
		return {campo_data: ["<=", data_fim]}
	return {}


@ferramenta(
	nome="listar_transacoes",
	titulo="Listar transações do extrato",
	descricao=(
		"Lista transações do extrato geral com filtros de período, categoria, centro de custo, "
		"carteira e situação de revisão. Use sem_categoria=true para achar o que ainda precisa "
		"ser categorizado — esse é o ponto de partida do fluxo de categorização."
	),
	parametros={
		"data_inicio": {"type": "string", "description": "Data inicial no formato AAAA-MM-DD."},
		"data_fim": {"type": "string", "description": "Data final no formato AAAA-MM-DD."},
		"campo_data": {
			"type": "string",
			"enum": list(CAMPOS_DATA),
			"default": "data_deposito",
			"description": "Campo de data usado no filtro de período.",
		},
		"busca": {"type": "string", "description": "Texto contido na descrição da transação."},
		"categoria": {"type": "string", "description": "Categoria de Transacao exata."},
		"centro_de_custo": {"type": "string", "description": "Centro de Custo exato."},
		"carteira": {"type": "string", "description": "Carteira exata."},
		"instituicao": {"type": "string", "description": "Instituição financeira exata."},
		"debito_credito": {
			"type": "string",
			"enum": ["Crédito", "Débito"],
			"description": "Tipo de movimento.",
		},
		"sem_categoria": {
			"type": "boolean",
			"description": "Se true, retorna apenas transações sem categoria definida.",
		},
		"revisada": {
			"type": "boolean",
			"description": "Filtra por transação revisada (true) ou não revisada (false).",
		},
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
def listar_transacoes(
	data_inicio: str | None = None,
	data_fim: str | None = None,
	campo_data: str = "data_deposito",
	busca: str | None = None,
	categoria: str | None = None,
	centro_de_custo: str | None = None,
	carteira: str | None = None,
	instituicao: str | None = None,
	debito_credito: str | None = None,
	sem_categoria: bool | None = None,
	revisada: bool | None = None,
	limite: int = 25,
	inicio: int = 0,
) -> dict:
	filtros: dict[str, Any] = _filtros_de_periodo(campo_data, data_inicio, data_fim)

	for campo, valor in (
		("categoria", categoria),
		("centro_de_custo", centro_de_custo),
		("carteira", carteira),
		("instituicao", instituicao),
		("debito_credito", debito_credito),
	):
		if valor:
			filtros[campo] = valor

	if sem_categoria:
		filtros["categoria"] = ["in", [None, ""]]
	if revisada is not None:
		filtros["transacao_revisada"] = 1 if revisada else 0
	if busca:
		filtros["descricao"] = ["like", f"%{busca}%"]

	campos = list(CAMPOS_LISTA)
	if _pode_ver_descricao_completa():
		campos.insert(1, "descricao")

	registros = frappe.get_all(
		DOCTYPE,
		filters=filtros,
		fields=campos,
		order_by="timestamp_transacao desc",
		limit_page_length=normalizar_limite(limite),
		limit_start=max(0, int(inicio or 0)),
	)

	return {
		"transacoes": registros,
		"paginacao": {
			"inicio": max(0, int(inicio or 0)),
			"limite": normalizar_limite(limite),
			"retornados": len(registros),
			"total_com_filtros": frappe.db.count(DOCTYPE, filtros),
		},
	}


@ferramenta(
	nome="listar_opcoes_financeiras",
	titulo="Listar opções de categorização",
	descricao=(
		"Retorna os valores válidos para categorizar transações: categorias, centros de custo, "
		"carteiras, instituições financeiras e contas fixas. Consulte antes de usar "
		"'categorizar_transacoes' para não enviar um valor inexistente."
	),
	parametros={},
	roles=ROLES_LEITURA,
)
def listar_opcoes_financeiras() -> dict:
	def nomes(doctype: str, order_by: str = "name asc", filters: dict | None = None) -> list[str]:
		return [linha["name"] for linha in frappe.get_all(doctype, filters=filters, order_by=order_by)]

	categorias = frappe.get_all(
		"Categoria de Transacao",
		fields=["name", "desscrição as descricao"],
		order_by="name asc",
	)

	return {
		"categorias": categorias,
		"centros_de_custo": nomes("Centro de Custo"),
		"carteiras": nomes("Carteira", filters={"ativa": 1}),
		"instituicoes": nomes("Instituicao Financeira"),
		"contas_fixas": nomes("Conta Fixa"),
		"ordinaria_extraordinaria": ["Ordinária", "Extraordinária"],
	}


def _validar_beneficiario(ids: list[str], beneficiario: str, categoria: str | None) -> None:
	"""O beneficiário só vale para contribuição mensal e para quem contribui.

	Atribuir a um Dirigente (ou a uma transação de outra categoria) faria o valor
	sumir da apuração sem erro nenhum — melhor recusar aqui.
	"""
	from gris.api.financeiro.contribuicoes import CATEGORIAS_CONTRIBUINTES

	categoria_associado = frappe.db.get_value("Associado", beneficiario, "categoria")
	if categoria_associado not in CATEGORIAS_CONTRIBUINTES:
		raise ErroDeFerramenta(
			"VALIDACAO",
			f"O associado '{beneficiario}' é da categoria '{categoria_associado}' e não entra "
			f"na apuração da contribuição mensal (categorias que contribuem: "
			f"{', '.join(CATEGORIAS_CONTRIBUINTES)}).",
		)

	if categoria and categoria != CATEGORIA_CONTRIBUICAO:
		raise ErroDeFerramenta(
			"VALIDACAO",
			f"Beneficiário só se aplica a transações de categoria '{CATEGORIA_CONTRIBUICAO}'.",
		)

	if categoria:
		return

	# Sem categoria na chamada, as transações precisam já estar na categoria certa.
	fora = [
		transacao["name"]
		for transacao in frappe.get_all(
			DOCTYPE,
			filters={"name": ["in", ids], "categoria": ["!=", CATEGORIA_CONTRIBUICAO]},
			fields=["name"],
		)
	]
	if fora:
		raise ErroDeFerramenta(
			"VALIDACAO",
			f"Só é possível definir beneficiário em transações de categoria "
			f"'{CATEGORIA_CONTRIBUICAO}'. Informe categoria='{CATEGORIA_CONTRIBUICAO}' na mesma "
			f"chamada ou ajuste as transações primeiro.",
			{"transacoes_fora_da_categoria": fora[:20]},
		)


def _simular_categorizacao(ids: list[str], atualizacoes: dict) -> dict:
	"""Monta o antes/depois da categorização sem tocar em nenhum documento."""
	if not frappe.has_permission(DOCTYPE, ptype="write"):
		raise ErroDeFerramenta("PERMISSAO_NEGADA", "Sem permissão de escrita no extrato geral.")

	previa, falhas = [], []
	for transacao_id in ids:
		atuais = frappe.db.get_value(DOCTYPE, transacao_id, list(atualizacoes), as_dict=True)
		if atuais is None:
			falhas.append({"id": transacao_id, "erro": "Transação não encontrada."})
			continue
		mudancas = {
			campo: {"de": atuais.get(campo), "para": valor}
			for campo, valor in atualizacoes.items()
			if atuais.get(campo) != valor
		}
		previa.append({"id": transacao_id, "alteracoes": mudancas, "sem_mudanca": not mudancas})

	return {
		"simulacao": True,
		"atualizadas": 0,
		"solicitadas": len(ids),
		"campos_aplicados": atualizacoes,
		"previa": previa,
		"falhas": falhas,
	}


@ferramenta(
	nome="categorizar_transacoes",
	titulo="Categorizar transações em lote",
	descricao=(
		"Aplica categoria, centro de custo, classificação ordinária/extraordinária, descrição "
		"reduzida, beneficiário e/ou marcação de revisada a uma lista de transações "
		"(máx. 200 por chamada). Informe ao menos um campo além dos IDs. O beneficiário é o "
		"que faz a contribuição mensal contar para o associado na apuração — use junto com "
		"categoria='Contribuição Mensal'. Use simular=true para conferir o antes/depois."
	),
	parametros={
		"ids": {
			"type": "array",
			"maxItems": MAX_TRANSACOES_LOTE,
			"description": "IDs das transações (campo 'name' retornado por 'listar_transacoes').",
		},
		"categoria": {"type": "string", "description": "Categoria de Transacao a aplicar."},
		"centro_de_custo": {"type": "string", "description": "Centro de Custo a aplicar."},
		"ordinaria_extraordinaria": {
			"type": "string",
			"enum": ["Ordinária", "Extraordinária"],
			"description": "Classificação da transação.",
		},
		"descricao_reduzida": {"type": "string", "description": "Descrição amigável da transação."},
		"beneficiario": {
			"type": "string",
			"description": (
				"CPF do associado que fez a contribuição mensal. Só se aplica a transações "
				"de categoria 'Contribuição Mensal'."
			),
		},
		"marcar_revisada": {
			"type": "boolean",
			"description": "Marca (true) ou desmarca (false) a transação como revisada.",
		},
	},
	obrigatorios=("ids",),
	roles=ROLES_ESCRITA,
	somente_leitura=False,
)
def categorizar_transacoes(
	ids: list[str],
	categoria: str | None = None,
	centro_de_custo: str | None = None,
	ordinaria_extraordinaria: str | None = None,
	descricao_reduzida: str | None = None,
	beneficiario: str | None = None,
	marcar_revisada: bool | None = None,
	simular: bool = False,
) -> dict:
	ids = [str(item).strip() for item in ids if str(item).strip()]
	if not ids:
		raise ErroDeFerramenta("ARGUMENTO_INVALIDO", "Informe ao menos um ID de transação.")

	atualizacoes: dict[str, Any] = {}
	if categoria:
		atualizacoes["categoria"] = categoria
	if centro_de_custo:
		atualizacoes["centro_de_custo"] = centro_de_custo
	if ordinaria_extraordinaria:
		atualizacoes["ordinaria_extraordinaria"] = ordinaria_extraordinaria
	if descricao_reduzida:
		atualizacoes["descricao_reduzida"] = descricao_reduzida
	if beneficiario:
		atualizacoes["beneficiario"] = beneficiario
	if marcar_revisada is not None:
		atualizacoes["transacao_revisada"] = 1 if marcar_revisada else 0

	if not atualizacoes:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			"Informe ao menos um campo para atualizar além dos IDs.",
			{"campos_aceitos": sorted(CAMPOS_CATEGORIZACAO)},
		)

	# Valida os links uma única vez, antes de tocar em qualquer documento.
	for campo, doctype_link in CAMPOS_CATEGORIZACAO.items():
		valor = atualizacoes.get(campo)
		if doctype_link and valor and not frappe.db.exists(doctype_link, valor):
			raise ErroDeFerramenta(
				"NAO_ENCONTRADO",
				f"'{valor}' não existe em {doctype_link}. Consulte 'listar_opcoes_financeiras'.",
				{"campo": campo, "doctype": doctype_link},
			)

	if beneficiario:
		_validar_beneficiario(ids, beneficiario, categoria)

	if simular:
		return _simular_categorizacao(ids, atualizacoes)

	atualizadas: list[str] = []
	falhas: list[dict] = []

	for transacao_id in ids:
		try:
			doc = frappe.get_doc(DOCTYPE, transacao_id)
			doc.check_permission("write")
			for campo, valor in atualizacoes.items():
				doc.set(campo, valor)
			doc.save()
			atualizadas.append(transacao_id)
		except frappe.DoesNotExistError:
			falhas.append({"id": transacao_id, "erro": "Transação não encontrada."})
		except frappe.PermissionError:
			falhas.append({"id": transacao_id, "erro": "Sem permissão de escrita."})

	return {
		"atualizadas": len(atualizadas),
		"solicitadas": len(ids),
		"campos_aplicados": atualizacoes,
		"ids_atualizados": atualizadas,
		"falhas": falhas,
	}


@ferramenta(
	nome="resumo_financeiro",
	titulo="Resumo financeiro por período",
	descricao=(
		"Totaliza créditos e débitos de um período e agrupa por categoria, centro de custo ou "
		"carteira. Ignora transações marcadas como 'excluir do total' (duplicatas conciliadas)."
	),
	parametros={
		"data_inicio": {"type": "string", "description": "Data inicial (AAAA-MM-DD)."},
		"data_fim": {"type": "string", "description": "Data final (AAAA-MM-DD)."},
		"campo_data": {
			"type": "string",
			"enum": list(CAMPOS_DATA),
			"default": "data_deposito",
			"description": "Campo de data usado no filtro de período.",
		},
		"agrupar_por": {
			"type": "string",
			"enum": ["categoria", "centro_de_custo", "carteira", "instituicao", "debito_credito"],
			"default": "categoria",
			"description": "Dimensão de agrupamento do resumo.",
		},
	},
	roles=ROLES_LEITURA,
)
def resumo_financeiro(
	data_inicio: str | None = None,
	data_fim: str | None = None,
	campo_data: str = "data_deposito",
	agrupar_por: str = "categoria",
) -> dict:
	filtros: dict[str, Any] = _filtros_de_periodo(campo_data, data_inicio, data_fim)
	filtros["excluir_do_total"] = 0

	linhas = frappe.get_all(
		DOCTYPE,
		filters=filtros,
		fields=[
			agrupar_por,
			"debito_credito",
			"sum(valor_absoluto) as total_absoluto",
			"sum(valor) as total_liquido",
			"count(name) as quantidade",
		],
		group_by=f"{agrupar_por}, debito_credito",
	)

	grupos: dict[str, dict] = {}
	total_credito = total_debito = 0.0

	for linha in linhas:
		chave = linha.get(agrupar_por) or "(sem valor)"
		grupo = grupos.setdefault(chave, {"grupo": chave, "credito": 0.0, "debito": 0.0, "quantidade": 0})
		# valor_absoluto é preenchido pelos importadores; se vier vazio,
		# usamos o módulo da soma de 'valor' como alternativa.
		valor = flt(linha.get("total_absoluto")) or abs(flt(linha.get("total_liquido")))
		grupo["quantidade"] += int(linha.get("quantidade") or 0)
		if linha.get("debito_credito") == "Crédito":
			grupo["credito"] += valor
			total_credito += valor
		else:
			grupo["debito"] += valor
			total_debito += valor

	for grupo in grupos.values():
		grupo["saldo"] = grupo["credito"] - grupo["debito"]

	return {
		"periodo": {"inicio": data_inicio, "fim": data_fim, "campo_data": campo_data},
		"agrupado_por": agrupar_por,
		"totais": {
			"credito": total_credito,
			"debito": total_debito,
			"saldo": total_credito - total_debito,
		},
		"grupos": sorted(grupos.values(), key=lambda g: abs(g["saldo"]), reverse=True),
	}


# ---------------------------------------------------------------------------
# Séries mensais (reaproveitam gris.api.financeiro.dashboard)
# ---------------------------------------------------------------------------

SERIES_DISPONIVEIS: dict[str, str] = {
	"entradas_saidas": "get_entradas_saidas_mensal",
	"entradas_por_categoria": "get_entradas_credito_mensal_por_categoria",
	"entradas_por_centro_de_custo": "get_entradas_credito_mensal_por_centro_custo",
	"entradas_por_tipo": "get_entradas_credito_mensal_por_tipo",
	"saidas_por_categoria": "get_saidas_debito_mensal_por_categoria",
	"saidas_por_centro_de_custo": "get_saidas_debito_mensal_por_centro_custo",
	"saidas_por_tipo": "get_saidas_debito_mensal_por_tipo",
	"contribuicoes_por_status": "get_contribuicoes_mensais_por_status",
	"inadimplencia_mensal": "get_contribuicoes_mensais_inadimplencia",
}


def _tabular(payload: dict) -> dict:
	"""Converte o formato de gráfico (labels + datasets) em linhas por mês."""
	labels = payload.get("labels") or []
	datasets = payload.get("datasets") or []

	por_mes = []
	for indice, mes in enumerate(labels):
		linha = {"mes": mes}
		for dataset in datasets:
			valores = dataset.get("values") or []
			linha[dataset.get("name", "serie")] = valores[indice] if indice < len(valores) else 0
		por_mes.append(linha)

	totais = {
		dataset.get("name", "serie"): round(sum(dataset.get("values") or []), 2) for dataset in datasets
	}
	return {"meses": labels, "por_mes": por_mes, "totais": totais}


@ferramenta(
	nome="serie_financeira",
	titulo="Série mensal do financeiro",
	descricao=(
		"Séries dos últimos 12 meses usadas no painel financeiro: entradas x saídas, entradas ou "
		"saídas por categoria/centro de custo/tipo, contribuições por status e inadimplência. "
		"Atenção: as duas séries de contribuição vêm do fluxo de cobrança (Pagamento "
		"Contribuicao Mensal); a apuração pelo dinheiro que entrou está em "
		"'resumo_contribuicoes'. "
		"Retorna uma linha por mês, pronta para comparação. O período é sempre os 12 meses "
		"encerrados no mês atual — para recortes livres use 'resumo_financeiro'."
	),
	parametros={
		"serie": {
			"type": "string",
			"enum": list(SERIES_DISPONIVEIS),
			"default": "entradas_saidas",
			"description": "Qual série calcular.",
		},
		"categoria": {"type": "string", "description": "Filtra por Categoria de Transacao."},
		"centro_de_custo": {"type": "string", "description": "Filtra por Centro de Custo."},
		"carteira": {"type": "string", "description": "Filtra por Carteira."},
		"instituicao": {"type": "string", "description": "Filtra por Instituição Financeira."},
		"ordinaria_extraordinaria": {
			"type": "string",
			"enum": ["Ordinária", "Extraordinária"],
			"description": "Filtra por classificação da transação.",
		},
	},
	roles=ROLES_LEITURA,
)
def serie_financeira(
	serie: str = "entradas_saidas",
	categoria: str | None = None,
	centro_de_custo: str | None = None,
	carteira: str | None = None,
	instituicao: str | None = None,
	ordinaria_extraordinaria: str | None = None,
) -> dict:
	from gris.api.financeiro import dashboard

	nome_funcao = SERIES_DISPONIVEIS.get(serie)
	if not nome_funcao:
		raise ErroDeFerramenta(
			"ARGUMENTO_INVALIDO",
			f"Série inválida. Opções: {', '.join(SERIES_DISPONIVEIS)}.",
			{"opcoes": list(SERIES_DISPONIVEIS)},
		)

	funcao = getattr(dashboard, nome_funcao)
	filtros = {
		"categoria": categoria,
		"centro_de_custo": centro_de_custo,
		"carteira": carteira,
		"instituicao": instituicao,
		"ordinaria_extraordinaria": ordinaria_extraordinaria,
	}
	# Cada série aceita um subconjunto diferente de filtros; passamos só o que existe
	# na assinatura para não quebrar quando o painel evoluir.
	aceitos = inspect.signature(funcao).parameters
	argumentos = {campo: valor for campo, valor in filtros.items() if valor and campo in aceitos}
	ignorados = sorted(campo for campo, valor in filtros.items() if valor and campo not in aceitos)

	resultado = _tabular(funcao(**argumentos))
	resultado["serie"] = serie
	resultado["filtros_aplicados"] = argumentos
	if ignorados:
		resultado["filtros_ignorados"] = ignorados
	return resultado
