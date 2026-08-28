# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""API da Previsão Orçamentária do módulo Financeiro.

Expõe a leitura do orçamento previsto, o CRUD de previsões/itens e o comparativo
entre previsto e realizado (a partir de ``Transacao Extrato Geral``).
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate

from gris.financeiro.doctype.previsao_orcamentaria.previsao_orcamentaria import (
	DISTRIBUICAO_MES_ESPECIFICO,
	DISTRIBUICAO_UNIFORME,
	meses_do_periodo,
	primeiro_dia_do_mes,
)

ROLES_LEITURA = ("Visualizador Financeiro", "Gestor Financeiro", "System Manager")
ROLES_GESTAO = ("Gestor Financeiro", "System Manager")

CAMPOS_ITEM = (
	"tipo",
	"descricao",
	"categoria",
	"centro_de_custo",
	"distribuicao",
	"mes_referencia",
	"valor_previsto",
	"observacoes",
)


def _autenticado():
	if frappe.session.user == "Guest":
		frappe.throw(_("Não autenticado"), frappe.PermissionError)


def pode_gerir() -> bool:
	"""Indica se o usuário atual pode criar/editar previsões."""
	if frappe.session.user == "Guest":
		return False
	return any(role in frappe.get_roles() for role in ROLES_GESTAO)


def _exigir_leitura():
	_autenticado()
	if not any(role in frappe.get_roles() for role in ROLES_LEITURA):
		frappe.throw(_("Sem permissão para consultar a previsão orçamentária"), frappe.PermissionError)


def _exigir_gestao():
	_autenticado()
	if not pode_gerir():
		frappe.throw(_("Sem permissão para editar a previsão orçamentária"), frappe.PermissionError)


def _mes_label(mes_iso: str) -> str:
	"""``2026-03`` -> ``03/26``."""
	ano, mes = mes_iso.split("-")
	return f"{mes}/{ano[2:]}"


def _parse_itens(itens) -> list[dict]:
	if isinstance(itens, str):
		try:
			itens = json.loads(itens)
		except ValueError:
			frappe.throw(_("Lista de itens inválida"))
	if itens is None:
		return []
	if not isinstance(itens, list):
		frappe.throw(_("Lista de itens inválida"))
	return [_normalizar_item(item) for item in itens]


def _normalizar_item(item) -> dict:
	if not isinstance(item, dict):
		frappe.throw(_("Item inválido"))

	tipo = (item.get("tipo") or "").strip()
	if tipo not in ("Receita", "Despesa"):
		frappe.throw(_("Tipo do item deve ser 'Receita' ou 'Despesa'"))

	descricao = (item.get("descricao") or "").strip()
	if not descricao:
		frappe.throw(_("Descrição do item é obrigatória"))

	distribuicao = (item.get("distribuicao") or DISTRIBUICAO_UNIFORME).strip()
	if distribuicao not in (DISTRIBUICAO_UNIFORME, DISTRIBUICAO_MES_ESPECIFICO):
		frappe.throw(_("Tipo de distribuição inválido"))

	valor = flt(item.get("valor_previsto"))
	if valor <= 0:
		frappe.throw(_("Valor previsto de '{0}' deve ser maior que zero").format(descricao))

	mes_referencia = item.get("mes_referencia") or None
	if distribuicao == DISTRIBUICAO_MES_ESPECIFICO:
		if not mes_referencia:
			frappe.throw(_("Informe o mês de referência de '{0}'").format(descricao))
		mes_referencia = primeiro_dia_do_mes(mes_referencia)
	else:
		mes_referencia = None

	return {
		"tipo": tipo,
		"descricao": descricao,
		"categoria": item.get("categoria") or None,
		"centro_de_custo": item.get("centro_de_custo") or None,
		"distribuicao": distribuicao,
		"mes_referencia": mes_referencia,
		"valor_previsto": valor,
		"observacoes": (item.get("observacoes") or "").strip() or None,
	}


def _serializar_previsao(doc) -> dict:
	return {
		"name": doc.name,
		"titulo": doc.titulo,
		"exercicio": doc.exercicio,
		"status": doc.status,
		"data_inicio": str(doc.data_inicio),
		"data_fim": str(doc.data_fim),
		"centro_de_custo": doc.centro_de_custo,
		"observacoes": doc.observacoes,
		"total_receitas_previstas": flt(doc.total_receitas_previstas, 2),
		"total_despesas_previstas": flt(doc.total_despesas_previstas, 2),
		"resultado_previsto": flt(doc.resultado_previsto, 2),
		"itens": [
			{
				"idx": item.idx,
				"name": item.name,
				**{
					campo: (
						str(item.get(campo))
						if campo == "mes_referencia" and item.get(campo)
						else item.get(campo)
					)
					for campo in CAMPOS_ITEM
				},
			}
			for item in doc.itens or []
		],
	}


@frappe.whitelist()
def listar_previsoes(exercicio: int | None = None, status: str | None = None) -> list[dict]:
	"""Lista as previsões orçamentárias cadastradas, mais recentes primeiro."""
	_exigir_leitura()

	filtros: dict[str, object] = {}
	if exercicio:
		filtros["exercicio"] = int(exercicio)
	if status:
		filtros["status"] = status

	return frappe.get_all(
		"Previsao Orcamentaria",
		filters=filtros,
		fields=[
			"name",
			"titulo",
			"exercicio",
			"status",
			"data_inicio",
			"data_fim",
			"centro_de_custo",
			"total_receitas_previstas",
			"total_despesas_previstas",
			"resultado_previsto",
		],
		order_by="exercicio desc, data_inicio desc",
		limit_page_length=0,
	)


@frappe.whitelist()
def obter_previsao(name: str) -> dict:
	"""Retorna uma previsão com seus itens."""
	_exigir_leitura()
	doc = frappe.get_doc("Previsao Orcamentaria", name)
	return _serializar_previsao(doc)


@frappe.whitelist(methods=["POST"])
def criar_previsao(
	titulo: str,
	exercicio: int,
	data_inicio: str,
	data_fim: str,
	status: str = "Rascunho",
	centro_de_custo: str | None = None,
	observacoes: str | None = None,
	itens: str | list | None = None,
) -> dict:
	"""Cria uma previsão orçamentária (opcionalmente já com itens)."""
	_exigir_gestao()

	titulo = (titulo or "").strip()
	if not titulo:
		frappe.throw(_("Título é obrigatório"))

	doc = frappe.get_doc(
		{
			"doctype": "Previsao Orcamentaria",
			"titulo": titulo,
			"exercicio": int(exercicio),
			"status": status or "Rascunho",
			"data_inicio": getdate(data_inicio),
			"data_fim": getdate(data_fim),
			"centro_de_custo": centro_de_custo or None,
			"observacoes": observacoes or None,
			"itens": _parse_itens(itens),
		}
	)
	doc.insert()
	return {"success": True, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def atualizar_previsao(
	name: str,
	titulo: str | None = None,
	exercicio: int | None = None,
	data_inicio: str | None = None,
	data_fim: str | None = None,
	status: str | None = None,
	centro_de_custo: str | None = None,
	observacoes: str | None = None,
) -> dict:
	"""Atualiza os dados gerais de uma previsão (não altera os itens)."""
	_exigir_gestao()

	doc = frappe.get_doc("Previsao Orcamentaria", name)
	if titulo is not None:
		doc.titulo = titulo.strip()
	if exercicio is not None:
		doc.exercicio = int(exercicio)
	if data_inicio is not None:
		doc.data_inicio = getdate(data_inicio)
	if data_fim is not None:
		doc.data_fim = getdate(data_fim)
	if status is not None:
		doc.status = status
	if centro_de_custo is not None:
		doc.centro_de_custo = centro_de_custo or None
	if observacoes is not None:
		doc.observacoes = observacoes or None

	doc.save()
	return {"success": True, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def excluir_previsao(name: str) -> dict:
	"""Remove uma previsão e seus itens."""
	_exigir_gestao()
	frappe.delete_doc("Previsao Orcamentaria", name)
	return {"success": True}


@frappe.whitelist(methods=["POST"])
def salvar_item(
	previsao: str,
	tipo: str,
	descricao: str,
	valor_previsto: float,
	item_name: str | None = None,
	categoria: str | None = None,
	centro_de_custo: str | None = None,
	distribuicao: str = DISTRIBUICAO_UNIFORME,
	mes_referencia: str | None = None,
	observacoes: str | None = None,
) -> dict:
	"""Cria ou atualiza um item da previsão."""
	_exigir_gestao()

	dados = _normalizar_item(
		{
			"tipo": tipo,
			"descricao": descricao,
			"categoria": categoria,
			"centro_de_custo": centro_de_custo,
			"distribuicao": distribuicao,
			"mes_referencia": mes_referencia,
			"valor_previsto": valor_previsto,
			"observacoes": observacoes,
		}
	)

	doc = frappe.get_doc("Previsao Orcamentaria", previsao)
	if doc.status == "Encerrada":
		frappe.throw(_("Não é possível alterar itens de uma previsão encerrada"))

	if item_name:
		alvo = next((i for i in doc.itens if i.name == item_name), None)
		if not alvo:
			frappe.throw(_("Item não encontrado nesta previsão"))
		alvo.update(dados)
	else:
		doc.append("itens", dados)

	doc.save()
	return {"success": True, "name": doc.name}


@frappe.whitelist(methods=["POST"])
def excluir_item(previsao: str, item_name: str) -> dict:
	"""Remove um item da previsão."""
	_exigir_gestao()

	doc = frappe.get_doc("Previsao Orcamentaria", previsao)
	if doc.status == "Encerrada":
		frappe.throw(_("Não é possível alterar itens de uma previsão encerrada"))

	restantes = [i for i in doc.itens if i.name != item_name]
	if len(restantes) == len(doc.itens):
		frappe.throw(_("Item não encontrado nesta previsão"))

	# Linhas já persistidas mantêm o idx original ao serem reatribuídas, o que deixaria
	# buracos na numeração da tabela; por isso renumeramos explicitamente.
	for posicao, item in enumerate(restantes, start=1):
		item.idx = posicao
	doc.set("itens", restantes)
	doc.save()
	return {"success": True}


@frappe.whitelist(methods=["POST"])
def duplicar_previsao(name: str, titulo: str, exercicio: int, data_inicio: str, data_fim: str) -> dict:
	"""Copia os itens de uma previsão existente para um novo período."""
	_exigir_gestao()

	origem = frappe.get_doc("Previsao Orcamentaria", name)
	meses_destino = set(meses_do_periodo(data_inicio, data_fim))

	itens = []
	for item in origem.itens or []:
		dados = {campo: item.get(campo) for campo in CAMPOS_ITEM}
		# Um mês de referência da previsão de origem pode não existir no novo período;
		# nesse caso o item passa a ser distribuído uniformemente.
		if dados["distribuicao"] == DISTRIBUICAO_MES_ESPECIFICO:
			mes = primeiro_dia_do_mes(dados["mes_referencia"]) if dados["mes_referencia"] else None
			if not mes or mes.strftime("%Y-%m") not in meses_destino:
				dados["distribuicao"] = DISTRIBUICAO_UNIFORME
				dados["mes_referencia"] = None
		itens.append(dados)

	doc = frappe.get_doc(
		{
			"doctype": "Previsao Orcamentaria",
			"titulo": (titulo or "").strip(),
			"exercicio": int(exercicio),
			"status": "Rascunho",
			"data_inicio": getdate(data_inicio),
			"data_fim": getdate(data_fim),
			"centro_de_custo": origem.centro_de_custo,
			"observacoes": origem.observacoes,
			"itens": itens,
		}
	)
	doc.insert()
	return {"success": True, "name": doc.name}


def _realizado_por_mes(data_inicio, data_fim, centro_de_custo: str | None):
	"""Agrega o realizado do extrato geral por mês, categoria e centro de custo.

	Segue as mesmas exclusões do dashboard financeiro: transações em dinheiro e
	repasses entre contas não entram no comparativo.
	"""
	condicoes = [
		"COALESCE(data_deposito, timestamp_transacao) >= %(inicio)s",
		"COALESCE(data_deposito, timestamp_transacao) < %(fim_exclusivo)s",
		"metodo != 'Dinheiro'",
		"COALESCE(repasse_entre_contas, 0) = 0",
	]
	params: dict[str, object] = {
		"inicio": primeiro_dia_do_mes(data_inicio),
		"fim_exclusivo": getdate(add_months(primeiro_dia_do_mes(data_fim), 1)),
	}
	if centro_de_custo:
		condicoes.append("centro_de_custo = %(centro_de_custo)s")
		params["centro_de_custo"] = centro_de_custo

	where_sql = " AND ".join(condicoes)
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	return frappe.db.sql(
		f"""
		SELECT DATE_FORMAT(COALESCE(data_deposito, timestamp_transacao), '%%Y-%%m') AS ym,
		       COALESCE(categoria, '') AS categoria,
		       COALESCE(centro_de_custo, '') AS centro_de_custo,
		       SUM(CASE WHEN valor > 0 THEN valor ELSE 0 END) AS receitas,
		       SUM(CASE WHEN valor < 0 THEN ABS(valor) ELSE 0 END) AS despesas
		FROM `tabTransacao Extrato Geral`
		WHERE {where_sql}
		GROUP BY ym, categoria, centro_de_custo
		""",
		params,
		as_dict=True,
	)


def _agrupar(previsto: dict[str, float], realizado: dict[str, float], rotulo_vazio: str) -> list[dict]:
	"""Junta previsto e realizado de uma dimensão (categoria/centro) em linhas comparáveis."""
	chaves = set(previsto) | set(realizado)
	linhas = []
	for chave in chaves:
		valor_previsto = flt(previsto.get(chave, 0.0), 2)
		valor_realizado = flt(realizado.get(chave, 0.0), 2)
		if not valor_previsto and not valor_realizado:
			continue
		linhas.append(
			{
				"rotulo": chave or rotulo_vazio,
				"previsto": valor_previsto,
				"realizado": valor_realizado,
				"desvio": flt(valor_realizado - valor_previsto, 2),
			}
		)
	linhas.sort(key=lambda linha: max(linha["previsto"], linha["realizado"]), reverse=True)
	return linhas


@frappe.whitelist()
def obter_comparativo(previsao: str) -> dict:
	"""Compara o orçamento previsto com o realizado do período.

	Retorna séries mensais (previsto, realizado e acumulado), quebras por categoria e
	por centro de custo, e os indicadores de execução orçamentária.
	"""
	_exigir_leitura()

	doc = frappe.get_doc("Previsao Orcamentaria", previsao)
	meses = doc.meses()
	if not meses:
		frappe.throw(_("Período da previsão inválido"))

	distribuicao = doc.distribuicao_mensal()

	# Previsto por dimensão
	previsto_categoria: dict[str, dict[str, float]] = {"Receita": {}, "Despesa": {}}
	previsto_centro: dict[str, dict[str, float]] = {"Receita": {}, "Despesa": {}}
	for item in doc.itens or []:
		alvo = "Receita" if item.tipo == "Receita" else "Despesa"
		categoria = item.categoria or ""
		centro = item.centro_de_custo or doc.centro_de_custo or ""
		previsto_categoria[alvo][categoria] = previsto_categoria[alvo].get(categoria, 0.0) + flt(
			item.valor_previsto
		)
		previsto_centro[alvo][centro] = previsto_centro[alvo].get(centro, 0.0) + flt(item.valor_previsto)

	# Realizado por dimensão
	realizado_mes = {mes: {"receitas": 0.0, "despesas": 0.0} for mes in meses}
	realizado_categoria: dict[str, dict[str, float]] = {"Receita": {}, "Despesa": {}}
	realizado_centro: dict[str, dict[str, float]] = {"Receita": {}, "Despesa": {}}
	for linha in _realizado_por_mes(doc.data_inicio, doc.data_fim, doc.centro_de_custo):
		mes = linha.get("ym")
		receitas = flt(linha.get("receitas"))
		despesas = flt(linha.get("despesas"))
		if mes in realizado_mes:
			realizado_mes[mes]["receitas"] += receitas
			realizado_mes[mes]["despesas"] += despesas

		categoria = linha.get("categoria") or ""
		centro = linha.get("centro_de_custo") or ""
		realizado_categoria["Receita"][categoria] = (
			realizado_categoria["Receita"].get(categoria, 0.0) + receitas
		)
		realizado_categoria["Despesa"][categoria] = (
			realizado_categoria["Despesa"].get(categoria, 0.0) + despesas
		)
		realizado_centro["Receita"][centro] = realizado_centro["Receita"].get(centro, 0.0) + receitas
		realizado_centro["Despesa"][centro] = realizado_centro["Despesa"].get(centro, 0.0) + despesas

	mes_atual = getdate().strftime("%Y-%m")
	meses_decorridos = sum(1 for mes in meses if mes <= mes_atual)

	receitas_previstas = [flt(distribuicao[mes]["receitas"], 2) for mes in meses]
	despesas_previstas = [flt(distribuicao[mes]["despesas"], 2) for mes in meses]
	receitas_realizadas = [flt(realizado_mes[mes]["receitas"], 2) for mes in meses]
	despesas_realizadas = [flt(realizado_mes[mes]["despesas"], 2) for mes in meses]

	total_receitas_previstas = flt(sum(receitas_previstas), 2)
	total_despesas_previstas = flt(sum(despesas_previstas), 2)
	total_receitas_realizadas = flt(sum(receitas_realizadas), 2)
	total_despesas_realizadas = flt(sum(despesas_realizadas), 2)

	# Previsto até o mês corrente — base justa para o percentual de execução.
	previsto_ate_hoje_receitas = flt(sum(receitas_previstas[:meses_decorridos]), 2)
	previsto_ate_hoje_despesas = flt(sum(despesas_previstas[:meses_decorridos]), 2)

	def _percentual(realizado: float, previsto: float) -> float | None:
		if not previsto:
			return None
		return flt(realizado / previsto * 100, 2)

	return {
		"success": True,
		"previsao": {
			"name": doc.name,
			"titulo": doc.titulo,
			"exercicio": doc.exercicio,
			"status": doc.status,
			"data_inicio": str(doc.data_inicio),
			"data_fim": str(doc.data_fim),
			"centro_de_custo": doc.centro_de_custo,
		},
		"meses": meses,
		"labels": [_mes_label(mes) for mes in meses],
		"meses_decorridos": meses_decorridos,
		"series": {
			"receitas_previstas": receitas_previstas,
			"receitas_realizadas": receitas_realizadas,
			"despesas_previstas": despesas_previstas,
			"despesas_realizadas": despesas_realizadas,
			"resultado_previsto": [
				flt(r - d, 2) for r, d in zip(receitas_previstas, despesas_previstas, strict=True)
			],
			"resultado_realizado": [
				flt(r - d, 2) for r, d in zip(receitas_realizadas, despesas_realizadas, strict=True)
			],
		},
		"totais": {
			"receitas_previstas": total_receitas_previstas,
			"receitas_realizadas": total_receitas_realizadas,
			"despesas_previstas": total_despesas_previstas,
			"despesas_realizadas": total_despesas_realizadas,
			"resultado_previsto": flt(total_receitas_previstas - total_despesas_previstas, 2),
			"resultado_realizado": flt(total_receitas_realizadas - total_despesas_realizadas, 2),
			"desvio_receitas": flt(total_receitas_realizadas - total_receitas_previstas, 2),
			"desvio_despesas": flt(total_despesas_realizadas - total_despesas_previstas, 2),
			"execucao_receitas": _percentual(total_receitas_realizadas, previsto_ate_hoje_receitas),
			"execucao_despesas": _percentual(total_despesas_realizadas, previsto_ate_hoje_despesas),
			"previsto_ate_hoje_receitas": previsto_ate_hoje_receitas,
			"previsto_ate_hoje_despesas": previsto_ate_hoje_despesas,
		},
		"por_categoria": {
			"receitas": _agrupar(
				previsto_categoria["Receita"], realizado_categoria["Receita"], "Sem categoria"
			),
			"despesas": _agrupar(
				previsto_categoria["Despesa"], realizado_categoria["Despesa"], "Sem categoria"
			),
		},
		"por_centro_de_custo": {
			"receitas": _agrupar(previsto_centro["Receita"], realizado_centro["Receita"], "Sem centro"),
			"despesas": _agrupar(previsto_centro["Despesa"], realizado_centro["Despesa"], "Sem centro"),
		},
	}
