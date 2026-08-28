"""Relatório completo da festa.

Agregação somente-leitura usada pela página de portal `/festas/relatorio`. As
consultas são *set-based* (`frappe.get_all` com `fields=` + mapas em memória),
evitando o N+1 do payload da página de edição da festa. Receita de convites e
avaliações reaproveitam o código já existente.
"""

from __future__ import annotations

import base64
import io
import math
import os

import frappe
from frappe import _
from frappe.utils import cint, flt, format_date, today

from gris.api.festas.avaliacao import _get_avaliacao_for_festa, _serialize_avaliacao
from gris.api.festas.convites import build_dashboard as build_convites_dashboard
from gris.api.festas.portaria import build_acompanhamento_data
from gris.festas.doctype.lista_entrada_festa.lista_entrada_festa import STATUS_ENTROU

# Cenário escolhido para cotações -> sufixo dos campos de cenário.
CENARIO_SUFIXO = {
	"Mínimo": "min",
	"Intermediário": "intermediario",
	"Máximo": "max",
}


def _format_time(value) -> str:
	text = str(value) if value else ""
	return text[:5] if len(text) >= 5 else text


def _nome_coord_geral(doc) -> str:
	"""Nome do coordenador geral, com fallback ao link (mesma regra de
	`www/festas/festa.py:_resolver_nome_coord_geral`)."""
	if doc.nome_coord_geral:
		return doc.nome_coord_geral
	if doc.tipo_coord_geral == "Responsavel" and doc.responsavel_coord_geral:
		return frappe.db.get_value("Responsavel", doc.responsavel_coord_geral, "nome_completo") or ""
	if doc.tipo_coord_geral == "Associado" and doc.associado_coord_geral:
		return frappe.db.get_value("Associado", doc.associado_coord_geral, "nome_completo") or ""
	return ""


def relatorio_disponivel(festa_name: str) -> bool:
	"""O relatório só existe após o início da avaliação da equipe.

	A avaliação da equipe é considerada iniciada quando há linhas em
	`avaliacoes_individuais` (gerada por `iniciar_avaliacao_festa`). A avaliação
	dos convidados é independente e não habilita o relatório.
	"""
	avaliacao_doc = _get_avaliacao_for_festa(festa_name)
	return bool(avaliacao_doc and avaliacao_doc.avaliacoes_individuais)


def _membros_por_pai(parenttype: str, nomes: list[str]) -> dict[str, list[dict]]:
	"""Mapa nome_do_pai -> equipe (nome + função), em uma única consulta."""
	if not nomes:
		return {}
	rows = frappe.get_all(
		"Membro Equipe Festa",
		filters={"parenttype": parenttype, "parent": ["in", nomes]},
		fields=["parent", "nome", "funcao"],
		order_by="idx asc",
	)
	mapa: dict[str, list[dict]] = {}
	for row in rows:
		mapa.setdefault(row.parent, []).append({"nome": row.nome or "", "funcao": row.funcao or ""})
	return mapa


def _fornecedor_escolhido(child_doctype: str, parenttype: str, parents: list[str]) -> dict[str, str]:
	"""Mapa parent -> fornecedor da cotação marcada como escolhida."""
	if not parents:
		return {}
	rows = frappe.get_all(
		child_doctype,
		filters={"parenttype": parenttype, "parent": ["in", parents], "escolhida": 1},
		fields=["parent", "fornecedor"],
	)
	mapa: dict[str, str] = {}
	for row in rows:
		mapa.setdefault(row.parent, row.fornecedor or "")
	return mapa


def _entradas_por_opcao(festa_name: str) -> dict[str, int]:
	"""Mapa opcao_convite -> nº de convidados que entraram (status=Entrou).

	A entrada (Lista Entrada Festa) é por convidado e não guarda o tipo de
	convite; quando o pedido tem um único tipo, a atribuição é exata. Nos pedidos
	com tipos misturados, distribui as entradas proporcionalmente à quantidade de
	cada tipo (maior resto), mantendo a soma por tipo igual ao total de entradas.
	"""
	# Raw SQL parametrizado (igual a `build_dashboard`): contagens set-based que
	# não devem sofrer filtro de permissão por doctype — a página já é autorizada
	# por leitura da Festa.
	entered_rows = frappe.db.sql(
		"""
		SELECT convite, COUNT(name) AS entradas
		  FROM `tabLista Entrada Festa`
		 WHERE festa = %(festa)s AND status = %(status)s AND convite IS NOT NULL
		 GROUP BY convite
		""",
		{"festa": festa_name, "status": STATUS_ENTROU},
		as_dict=True,
	)
	entered_by_pedido = {r.convite: cint(r.entradas) for r in entered_rows if r.convite}
	if not entered_by_pedido:
		return {}

	item_rows = frappe.db.sql(
		"""
		SELECT parent, opcao_convite, SUM(quantidade) AS qtd
		  FROM `tabItem Convite Festa`
		 WHERE parenttype = 'Convite Festa'
		   AND eh_convite = 1
		   AND opcao_convite IS NOT NULL
		   AND parent IN %(pedidos)s
		 GROUP BY parent, opcao_convite
		""",
		{"pedidos": tuple(entered_by_pedido)},
		as_dict=True,
	)
	itens_por_pedido: dict[str, list[tuple[str, int]]] = {}
	for r in item_rows:
		itens_por_pedido.setdefault(r.parent, []).append((r.opcao_convite, cint(r.qtd)))

	resultado: dict[str, int] = {}
	for pedido, entradas in entered_by_pedido.items():
		itens = itens_por_pedido.get(pedido) or []
		total_qtd = sum(q for _, q in itens)
		if not itens or total_qtd <= 0:
			continue
		if len(itens) == 1:
			opc = itens[0][0]
			resultado[opc] = resultado.get(opc, 0) + entradas
			continue
		# Rateio proporcional com maior resto (mantém contagens inteiras somando
		# exatamente ao nº de entradas do pedido).
		restante = min(entradas, total_qtd)
		brutos = [(opc, restante * q / total_qtd) for opc, q in itens]
		alocado = {opc: int(v) for opc, v in brutos}
		sobra = restante - sum(alocado.values())
		ordem = sorted(range(len(brutos)), key=lambda i: brutos[i][1] - int(brutos[i][1]), reverse=True)
		for k in range(sobra):
			opc = brutos[ordem[k % len(ordem)]][0]
			alocado[opc] += 1
		for opc, v in alocado.items():
			resultado[opc] = resultado.get(opc, 0) + v
	return resultado


def _montar_secao_convites(festa_name: str, convites_dashboard: dict) -> dict:
	"""Cards, tabela e dados de gráfico da seção Convites do relatório.

	Reaproveita o dashboard de convites (qtd/valor por opção, pagos) e o
	acompanhamento da portaria (pizza/origem/linha das entradas).
	"""
	acomp = build_acompanhamento_data(festa_name)
	pizza = acomp.get("pizza", {}) or {}
	entrou_previo = cint(pizza.get("entrou"))
	nao_entrou = cint(pizza.get("nao_entrou"))
	portaria = cint(pizza.get("comprou_portaria"))
	total_entrou = cint(pizza.get("total_entrou"))
	total_previa = entrou_previo + nao_entrou

	totais = convites_dashboard.get("totais", {}) or {}
	qtd_por_opcao = totais.get("qtd_por_opcao", {}) or {}
	valor_por_opcao = totais.get("valor_por_opcao", {}) or {}
	doacoes = flt(totais.get("total_doacoes_valor"))
	entradas_opcao = _entradas_por_opcao(festa_name)

	linhas = []
	total_qtd = total_val = total_entraram = 0
	for opc in convites_dashboard.get("opcoes", []) or []:
		nome = opc.get("name")
		qtd = cint(qtd_por_opcao.get(nome, 0))
		valor = flt(valor_por_opcao.get(nome, 0))
		entraram = cint(entradas_opcao.get(nome, 0))
		total_qtd += qtd
		total_val += valor
		total_entraram += entraram
		linhas.append(
			{
				"nome": opc.get("nome_convite") or nome,
				"qtd": qtd,
				"valor": valor,
				"entraram": entraram,
				"pct_entrou": (entraram / qtd * 100) if qtd else 0.0,
			}
		)

	return {
		"cards": {
			"previa_entrou": entrou_previo,
			"previa_total": total_previa,
			"previa_pct": (entrou_previo / total_previa * 100) if total_previa else 0.0,
			"total_entrou": total_entrou,
			"portaria_entrou": portaria,
		},
		"tabela": linhas,
		"tabela_total": {
			"qtd": total_qtd,
			"valor": total_val,
			"entraram": total_entraram,
			"pct_entrou": (total_entraram / total_qtd * 100) if total_qtd else 0.0,
		},
		"doacoes": doacoes,
		"tem_dados": cint(pizza.get("total")) > 0,
		"chart": {
			"pizza": pizza,
			"origem": acomp.get("origem_entradas", {}) or {},
			"linha": acomp.get("linha", []) or [],
		},
	}


def _distribuicao_0_10(notas: list[int]) -> list[int]:
	"""Contagem de cada nota inteira de 0 a 10 (11 baldes), para os histogramas."""
	return [sum(1 for n in notas if n == i) for i in range(11)]


def _montar_avaliacoes(avaliacao: dict | None) -> dict | None:
	"""Normaliza os dados de avaliação para o relatório, calculando o NPS dos
	convidados e a distribuição das notas a partir das respostas."""
	if not avaliacao:
		return None

	convidados = avaliacao.get("convidados") or []
	notas = [cint(c.get("recomendacao")) for c in convidados if c.get("recomendacao") is not None]
	total_conv = len(notas)
	promotores = sum(1 for n in notas if n >= 9)
	detratores = sum(1 for n in notas if n <= 6)
	nps_conv = (promotores - detratores) / total_conv if total_conv else 0.0
	distribuicao = _distribuicao_0_10(notas)

	# Distribuição das notas da equipe (avaliações individuais concluídas): a
	# satisfação em colaborar alimenta o NPS da equipe; o resultado da festa, a
	# avaliação geral. Servem para os histogramas do relatório.
	individuais = avaliacao.get("individuais") or []
	notas_satisfacao = [
		cint(i.get("satisfacao_colaboracao"))
		for i in individuais
		if i.get("satisfacao_colaboracao") not in (None, "")
	]
	notas_resultado = [
		cint(i.get("resultado_festa")) for i in individuais if i.get("resultado_festa") not in (None, "")
	]

	return {
		"geral": {
			"funcionou_bem": avaliacao.get("o_que_funcionou_bem_na_dinamica_da_equipe", ""),
			"nao_funcionou": avaliacao.get("o_que_nao_funcionou_na_dinamica_da_equipe", ""),
			"pontos_positivos": avaliacao.get("pontos_positivos_adicionais", ""),
			"pontos_melhoria": avaliacao.get("pontos_de_melhoria_adicionais", ""),
			"resumo_ia": avaliacao.get("resumo_avaliacao_completa", ""),
		},
		"convidados": {
			"nps": nps_conv,
			"total": total_conv,
			"distribuicao": distribuicao,
			"resumo_ia": avaliacao.get("resumo_avaliacoes_convidados", ""),
		},
		"equipe": {
			"nps": flt(avaliacao.get("satisfacao_dos_participantes")),
			"avaliacao_geral": flt(avaliacao.get("avaliacao_geral")),
			"total": cint(avaliacao.get("total_individuais")),
			"concluidas": cint(avaliacao.get("concluidas_individuais")),
			"dist_nps": _distribuicao_0_10(notas_satisfacao),
			"dist_geral": _distribuicao_0_10(notas_resultado),
			"resumo_ia": avaliacao.get("resumo_avaliacoes_individuais", ""),
		},
	}


def build_relatorio_payload(festa_name: str) -> dict:
	"""Monta o payload completo do relatório de uma festa."""
	doc = frappe.get_doc("Festa", festa_name)
	sufixo = CENARIO_SUFIXO.get(doc.cenario_simulacao or "Intermediário", "intermediario")

	# ── Áreas, barracas e equipes ───────────────────────────────────────────
	areas = frappe.get_all(
		"Area da Festa",
		filters={"festa": festa_name},
		fields=["name", "nome_area", "nome_coord"],
		order_by="creation asc",
	)
	barracas = frappe.get_all(
		"Barraca da Festa",
		filters={"festa": festa_name},
		fields=["name", "nome_barraca", "nome_coord", "area", "valor_arrecadado_realizado_real"],
		order_by="creation asc",
	)
	area_nome = {a.name: (a.nome_area or a.name) for a in areas}
	equipe_area = _membros_por_pai("Area da Festa", [a.name for a in areas])
	equipe_barraca = _membros_por_pai("Barraca da Festa", [b.name for b in barracas])

	areas_payload = [
		{
			"nome_area": a.nome_area or a.name,
			"nome_coord": a.nome_coord or "",
			"equipe": equipe_area.get(a.name, []),
		}
		for a in areas
	]
	barracas_lista = [b.nome_barraca or b.name for b in barracas]

	# ── Produtos (itens vendidos) por barraca ───────────────────────────────
	produtos = frappe.get_all(
		"Produto de Venda Festa",
		filters={"festa": festa_name},
		fields=[
			"barraca",
			"nome_produto",
			"valor_total_arrecadado",
			f"qtd_{sufixo} as qtd_esperada",
			"qtd_realizada_vendas",
		],
		order_by="nome_produto asc",
	)
	produtos_por_barraca: dict[str, list[dict]] = {}
	for p in produtos:
		produtos_por_barraca.setdefault(p.barraca, []).append(
			{
				"nome_produto": p.nome_produto or "",
				"valor_vendido": flt(p.valor_total_arrecadado),
				"qtd_esperada": flt(p.qtd_esperada),
				"qtd_vendida": flt(p.qtd_realizada_vendas),
			}
		)

	# Receita esperada por barraca (cenário escolhido), do próprio doc Festa.
	esperado_por_barraca = {
		row.barraca: flt(row.get(f"esperado_{sufixo}")) for row in (doc.receitas_por_barraca or [])
	}

	barracas_payload = []
	barracas_receita = []  # gráfico + tabela de receitas (arrecadação realizada)
	for b in barracas:
		realizado = flt(b.valor_arrecadado_realizado_real)
		label = b.nome_barraca or b.name
		barracas_payload.append(
			{
				"nome_barraca": label,
				"nome_coord": b.nome_coord or "",
				"equipe": equipe_barraca.get(b.name, []),
				"itens": produtos_por_barraca.get(b.name, []),
				"esperado": esperado_por_barraca.get(b.name, 0.0),
				"realizado": realizado,
			}
		)
		barracas_receita.append({"label": label, "valor": realizado})
	barracas_receita.sort(key=lambda x: x["valor"], reverse=True)

	# ── Receita de convites executada + doações (pagos) ─────────────────────
	convites = build_convites_dashboard(festa_name)
	totais_conv = convites.get("totais", {}) or {}
	receita_convites = sum(flt(v) for v in (totais_conv.get("valor_por_opcao") or {}).values())
	receita_doacoes = flt(totais_conv.get("total_doacoes_valor"))

	# Seção Convites: entradas (cards + gráficos) e tabela por tipo de convite.
	convites_secao = _montar_secao_convites(festa_name, convites)

	# ── Compras e contratações (realizado) ──────────────────────────────────
	compras = frappe.get_all(
		"Compra Festa",
		filters={"festa": festa_name},
		fields=[
			"name",
			"area",
			"nome_item",
			"cotacao_escolhida_valor",
			"quantidade_compra_final",
			"valor_total_compra",
			"valor_individual_realizado",
			"quantidade_realizada",
			"valor_total_realizado",
			"fornecedor_realizado",
			"observacoes_realizado",
			"cancelado",
		],
		order_by="nome_item asc",
	)
	contratacoes = frappe.get_all(
		"Contratacao Festa",
		filters={"festa": festa_name},
		fields=[
			"name",
			"area",
			"nome_item",
			"valor_total_contratacao",
			"valor_total_realizado",
			"fornecedor_realizado",
			"observacoes_realizado",
			"cancelado",
		],
		order_by="nome_item asc",
	)
	forn_compra = _fornecedor_escolhido("Cotacao Compra Festa", "Compra Festa", [c.name for c in compras])
	forn_contr = _fornecedor_escolhido(
		"Cotacao Contratacao Festa", "Contratacao Festa", [c.name for c in contratacoes]
	)

	compras_payload = [
		{
			"nome_item": c.nome_item or "",
			"valor_individual_orcado": flt(c.cotacao_escolhida_valor),
			"qtd_orcada": flt(c.quantidade_compra_final),
			"valor_total_orcado": flt(c.valor_total_compra),
			"fornecedor_orcado": forn_compra.get(c.name, ""),
			"valor_individual_realizado": flt(c.valor_individual_realizado),
			"qtd_realizada": flt(c.quantidade_realizada),
			"valor_total_realizado": flt(c.valor_total_realizado),
			"fornecedor_realizado": c.fornecedor_realizado or "",
			"observacoes": c.observacoes_realizado or "",
			"cancelado": bool(c.cancelado),
		}
		for c in compras
	]
	contratacoes_payload = [
		{
			"nome_item": c.nome_item or "",
			"valor_orcado": flt(c.valor_total_contratacao),
			"fornecedor_orcado": forn_contr.get(c.name, ""),
			"valor_realizado": flt(c.valor_total_realizado),
			"fornecedor_realizado": c.fornecedor_realizado or "",
			"observacoes": c.observacoes_realizado or "",
			"cancelado": bool(c.cancelado),
		}
		for c in contratacoes
	]

	# Despesa realizada por área (compras + contratações).
	# Itens cancelados (não comprados) não entram nas despesas.
	despesa_area: dict[str, float] = {}
	for c in compras:
		if c.cancelado:
			continue
		despesa_area[c.area or ""] = despesa_area.get(c.area or "", 0.0) + flt(c.valor_total_realizado)
	for c in contratacoes:
		if c.cancelado:
			continue
		despesa_area[c.area or ""] = despesa_area.get(c.area or "", 0.0) + flt(c.valor_total_realizado)
	despesas_por_area = [
		{"label": area_nome.get(a, "Sem área") if a else "Sem área", "valor": v}
		for a, v in despesa_area.items()
	]
	despesas_por_area.sort(key=lambda x: x["valor"], reverse=True)

	# ── Arrecadação e resultado por área ────────────────────────────────────
	# Receita realizada de cada barraca agrupada pela área a que pertence e o
	# resultado por área (receita das barracas menos despesas de compras/contratações).
	# Áreas seguem a ordem de cadastro; barracas/despesas sem área vão ao final.
	ordem_areas = [a.name for a in areas]

	def _ordem_area(chave: str) -> tuple[int, str]:
		return (ordem_areas.index(chave), "") if chave in ordem_areas else (len(ordem_areas), chave)

	def _label_area(chave: str) -> str:
		return area_nome.get(chave, "Sem área") if chave else "Sem área"

	barracas_por_area: dict[str, list[dict]] = {}
	receita_area: dict[str, float] = {}
	for b in barracas:
		chave = b.area or ""
		valor = flt(b.valor_arrecadado_realizado_real)
		barracas_por_area.setdefault(chave, []).append(
			{"nome_barraca": b.nome_barraca or b.name, "valor": valor}
		)
		receita_area[chave] = receita_area.get(chave, 0.0) + valor

	arrecadacao_por_area = [
		{
			"label": _label_area(chave),
			"barracas": barracas_por_area[chave],
			"subtotal": receita_area.get(chave, 0.0),
		}
		for chave in sorted(barracas_por_area, key=_ordem_area)
	]
	resultado_por_area = [
		{
			"label": _label_area(chave),
			"receitas": receita_area.get(chave, 0.0),
			"despesas": despesa_area.get(chave, 0.0),
			"resultado": receita_area.get(chave, 0.0) - despesa_area.get(chave, 0.0),
		}
		for chave in sorted(set(receita_area) | set(despesa_area), key=_ordem_area)
	]

	# ── Totais do fechamento (segmentação de receitas) ──────────────────────
	# Receitas de convite segmentadas: consumação (parcela de fichas embutida no
	# valor do convite) e entrada (restante do valor do convite).
	consumacao_convites = flt(totais_conv.get("total_consumacao"))
	entrada_convites = receita_convites - consumacao_convites
	# Os convites de portaria já entram no caixa da festa; subtraímos para não
	# contabilizar duas vezes no fechamento de caixa.
	portaria_valor = flt(totais_conv.get("total_portaria_valor"))
	valor_arrecadado_festa = flt(doc.get("valor_arrecadado_festa"))
	fechamento_caixa = valor_arrecadado_festa - portaria_valor

	arrecadacao_barracas = sum(flt(b.valor_arrecadado_realizado_real) for b in barracas)
	arrecadacao = consumacao_convites + entrada_convites + fechamento_caixa + receita_doacoes
	despesas = sum(x["valor"] for x in despesas_por_area)
	resultado = arrecadacao - despesas

	# Fichas não gastas: consumação vendida + caixa - arrecadação das barracas.
	fichas_nao_gastas = consumacao_convites + fechamento_caixa - arrecadacao_barracas

	# Previsão do cenário escolhido (totais esperados gravados no doc Festa).
	previsto_arrecadacao = flt(doc.get(f"receita_total_{sufixo}"))
	previsto_despesas = flt(doc.get(f"despesa_total_{sufixo}"))
	previsto = {
		"arrecadacao": previsto_arrecadacao,
		"despesas": previsto_despesas,
		"resultado": previsto_arrecadacao - previsto_despesas,
	}

	# Passos do waterfall: as 3 receitas segmentadas (+), doações (+) e despesas
	# por área (negativo); o JS acumula e fecha com a barra de Resultado.
	waterfall = [
		{"label": "Consumação", "valor": consumacao_convites},
		{"label": "Entrada", "valor": entrada_convites},
		{"label": "Fechamento de caixa", "valor": fechamento_caixa},
	]
	if receita_doacoes:
		waterfall.append({"label": "Doações", "valor": receita_doacoes})
	waterfall += [{"label": d["label"], "valor": -d["valor"]} for d in despesas_por_area]

	avaliacao_doc = _get_avaliacao_for_festa(festa_name)
	avaliacoes = _montar_avaliacoes(_serialize_avaliacao(avaliacao_doc) if avaliacao_doc else None)

	return {
		"festa_name": doc.name,
		"nome_festa": doc.nome_festa or doc.name,
		"status": doc.status or "",
		"data_formatada": format_date(doc.data, "dd/MM/yyyy") if doc.data else "",
		"horario_inicio": _format_time(doc.horario_inicio),
		"horario_termino": _format_time(doc.horario_termino),
		"nome_coord_geral": _nome_coord_geral(doc),
		"expectativa_min": cint(doc.expectativa_publico_min),
		"expectativa_intermediario": cint(doc.expectativa_publico_intermediario),
		"expectativa_max": cint(doc.expectativa_publico_max),
		"cenario_simulacao": doc.cenario_simulacao or "Intermediário",
		"areas": areas_payload,
		"barracas_lista": barracas_lista,
		"barracas": barracas_payload,
		"convites_secao": convites_secao,
		"receita_convites": receita_convites,
		"receita_doacoes": receita_doacoes,
		"consumacao_convites": consumacao_convites,
		"entrada_convites": entrada_convites,
		"fechamento_caixa": fechamento_caixa,
		"valor_arrecadado_festa": valor_arrecadado_festa,
		"fichas_nao_gastas": fichas_nao_gastas,
		"receitas_barracas": barracas_receita,
		"arrecadacao_barracas": arrecadacao_barracas,
		"arrecadacao_por_area": arrecadacao_por_area,
		"despesas_por_area": despesas_por_area,
		"resultado_por_area": resultado_por_area,
		"arrecadacao": arrecadacao,
		"despesas": despesas,
		"resultado": resultado,
		"previsto": previsto,
		"compras": compras_payload,
		"contratacoes": contratacoes_payload,
		"avaliacoes": avaliacoes,
		"chart_data": {
			"barracas": barracas_receita,
			"waterfall": waterfall,
			"resultado": resultado,
			"distribuicao": (avaliacoes or {}).get("convidados", {}).get("distribuicao", []),
			"entradas": convites_secao["chart"],
		},
	}


@frappe.whitelist()
def get_relatorio_payload(festa_name: str) -> dict:
	"""Versão exposta para refresh client-side, com checagem de permissão."""
	if not festa_name:
		frappe.throw(_("Parâmetro 'festa_name' obrigatório."), frappe.ValidationError)
	if not frappe.has_permission("Festa", "read", festa_name):
		frappe.throw(_("Sem permissão para acessar esta festa."), frappe.PermissionError)
	if not relatorio_disponivel(festa_name):
		frappe.throw(_("Relatório indisponível: a avaliação da equipe ainda não foi iniciada."))
	return build_relatorio_payload(festa_name)


# ---------------------------------------------------------------------------
# Relatório em PDF (capa + corpo) — gerado no servidor com WeasyPrint.
#
# Documento único: o template do corpo inclui a capa (página nomeada `cover`,
# full-bleed) e usa CSS moderno (linear-gradient, flexbox, web font Figtree,
# `@page`/`counter(page)`). Como o WeasyPrint também não roda JavaScript, os
# gráficos seguem em SVG estático com a geometria (roscas/waterfall/séries)
# calculada aqui em Python.
# ---------------------------------------------------------------------------

# Paleta acessível (Okabe-Ito) — mesma da página de relatório (`relatorio.js`).
_COR_ENTROU = "#009E73"
_COR_NAO_ENTROU = "#D55E00"
_COR_PORTARIA = "#0072B2"
_COR_COMPRA_PREVIA = "#56B4E9"
_COR_COMPRA_PORTARIA = "#E69F00"
# Marca (degradê e acentos).
_COR_NAVY = "#1D2755"

# A capa é renderizada à parte e injetada no corpo (documento mestre) como
# `capa_html`. Não usamos `{% include %}`: o loader do Jinja do Frappe não resolve
# o nome do template quando renderizamos a partir de string.
_CAPA_TEMPLATE = "templates/pages/relatorio_festa_pdf_capa.html"
_CORPO_TEMPLATE = "templates/pages/relatorio_festa_pdf_corpo.html"


# ── Paginação das tabelas "de lado" (compras/contratações) ─────────────────────
# No corpo do PDF a seção de compras/contratações fica em folhas RETRATO com o
# conteúdo rotacionado 90° (CSS `transform: rotate`), para a tabela larga caber. O
# WeasyPrint aplica o transform DEPOIS do layout, então conteúdo transformado não
# pagina sozinho — o que passa da folha é cortado. Por isso quebramos as linhas em
# blocos aqui, estimando a altura de cada linha, de modo que cada bloco (uma
# `.rot-canvas`) caiba em uma folha. Estimativas conservadoras (poucos caracteres
# por linha → mais linhas previstas) preferem sobrar espaço a cortar conteúdo.
_PAG_ALTURA_MM = 184.0  # espaço de empilhamento por folha (largura útil do retrato)
_PAG_MARGEM_MM = 12.0  # folga de segurança
_PAG_SEC_HEAD_MM = 22.0  # sec_head + h3 (só na 1ª folha das compras)
_PAG_H3_MM = 8.0  # h3 "Contratações" / "(continuação)"
_PAG_THEAD_MM = 16.0  # cabeçalho da tabela (repetido por folha; rótulos quebram em 2-3 linhas)
_PAG_LINHA_MM = 4.4  # altura de uma linha de texto a 8pt
_PAG_ROW_PAD_MM = 4.2  # padding vertical de uma <tr>


def _altura_linha(celulas: list[tuple[str, int]]) -> float:
	"""Altura estimada (mm) de uma `<tr>`: a célula que mais quebra define a altura.

	`celulas`: pares ``(texto, caracteres_por_linha_da_coluna)``.
	"""
	linhas = 1
	for texto, cpl in celulas:
		if texto:
			linhas = max(linhas, math.ceil(len(str(texto)) / cpl))
	return linhas * _PAG_LINHA_MM + _PAG_ROW_PAD_MM


def _paginar(linhas: list[dict], celulas_de, extra_primeira_mm: float) -> list[list[dict]]:
	"""Quebra `linhas` em blocos que cabem numa folha rotacionada.

	`celulas_de(linha)` devolve os pares ``(texto, cpl)`` que estimam a altura da
	linha. `extra_primeira_mm` é o cabeçalho extra que só aparece na 1ª folha.
	Devolve sempre ao menos um bloco (vazio quando não há linhas) para o template
	renderizar o estado "nenhum item cadastrado".
	"""
	if not linhas:
		return [[]]
	cap_primeira = _PAG_ALTURA_MM - _PAG_MARGEM_MM - extra_primeira_mm - _PAG_THEAD_MM
	cap_demais = _PAG_ALTURA_MM - _PAG_MARGEM_MM - _PAG_H3_MM - _PAG_THEAD_MM
	paginas: list[list[dict]] = []
	atual: list[dict] = []
	restante = cap_primeira
	for ln in linhas:
		altura = _altura_linha(celulas_de(ln))
		if atual and altura > restante:
			paginas.append(atual)
			atual = []
			restante = cap_demais
		atual.append(ln)
		restante -= altura
	paginas.append(atual)
	return paginas


# caracteres-por-linha de cada coluna que quebra (≈ largura útil / largura do
# caractere a 8pt). Valores conservadores — derivados das larguras fixas do
# `<colgroup>` no template — para superestimar a altura e nunca cortar linhas.
def _paginar_compras(compras: list[dict]) -> list[list[dict]]:
	def celulas(c: dict) -> list[tuple[str, int]]:
		return [
			(c.get("observacoes"), 38),  # obs: col. 68mm
			(c.get("nome_item"), 14),  # item: col. 26mm
			(c.get("fornecedor_orcado"), 15),  # fornecedor: col. 28mm
			(c.get("fornecedor_realizado"), 15),
		]

	return _paginar(compras, celulas, _PAG_SEC_HEAD_MM)


def _paginar_contratacoes(contratacoes: list[dict]) -> list[list[dict]]:
	def celulas(c: dict) -> list[tuple[str, int]]:
		return [
			(c.get("observacoes"), 38),  # obs: col. 68mm
			(c.get("nome_item"), 20),  # nome: col. 42mm
			(c.get("fornecedor_orcado"), 22),  # fornecedor: col. 46mm
			(c.get("fornecedor_realizado"), 22),
		]

	return _paginar(contratacoes, celulas, _PAG_H3_MM)


def _logo_uel_data_uri() -> str:
	"""Logo da UEL como data-URI PNG (mesmo carregamento do convite/QR), com
	contorno branco para contraste sobre o gradiente escuro da capa."""
	from gris.festas.utils.convite_qr import _carregar_logo

	logo = _carregar_logo()
	if logo is None:
		return ""
	logo = _com_contorno_branco(logo)
	buf = io.BytesIO()
	logo.save(buf, format="PNG")
	return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _com_contorno_branco(logo, proporcao: float = 0.06):
	"""Recorta um contorno branco que segue a silhueta (alpha) do logo — efeito
	"die-cut" de adesivo, para o logo ficar legível sobre o gradiente escuro da
	capa. O WeasyPrint não gera esse contorno via CSS, então pré-processamos o PNG.

	Dilata a máscara alpha carimbando-a num disco (contorno redondo e uniforme) e
	usa a silhueta resultante para recortar uma camada branca, com o logo original
	por cima. A espessura é `proporcao` da menor dimensão (independe da resolução).
	"""
	from PIL import Image, ImageChops

	logo = logo.convert("RGBA")
	bbox = logo.getbbox()
	if bbox:
		logo = logo.crop(bbox)
	# O logo aparece pequeno na capa (~22mm) e o custo do contorno cresce com a
	# espessura²; limitar a resolução de trabalho mantém o pré-processo barato.
	limite = 480
	if max(logo.size) > limite:
		resample = getattr(Image, "Resampling", Image).LANCZOS
		logo.thumbnail((limite, limite), resample)

	espessura = max(4, round(min(logo.size) * proporcao))
	alpha = logo.getchannel("A")
	pad = espessura + 4
	size = (logo.width + 2 * pad, logo.height + 2 * pad)

	mascara = Image.new("L", size, 0)
	for dy in range(-espessura, espessura + 1):
		for dx in range(-espessura, espessura + 1):
			if dx * dx + dy * dy <= espessura * espessura:
				deslocado = Image.new("L", size, 0)
				deslocado.paste(alpha, (pad + dx, pad + dy))
				mascara = ImageChops.lighter(mascara, deslocado)

	out = Image.new("RGBA", size, (255, 255, 255, 0))
	out.paste(Image.new("RGBA", size, (255, 255, 255, 255)), (0, 0), mascara)
	out.alpha_composite(logo, (pad, pad))
	return out


def _donut(pares: list[dict]) -> dict | None:
	"""Segmentos prontos para um donut SVG.

	O círculo usa r=15.915 (circunferência ≈ 100), então `stroke-dasharray` já é
	a própria porcentagem e o `stroke-dashoffset` posiciona cada fatia a partir do
	topo (12h). `pares`: lista de ``{label, value, color}``.
	"""
	total = sum(flt(p["value"]) for p in pares)
	if total <= 0:
		return None
	segmentos = []
	acumulado = 0.0
	for p in pares:
		valor = flt(p["value"])
		pct = valor / total * 100
		segmentos.append(
			{
				"label": p["label"],
				"value": valor,
				"pct": pct,
				"color": p["color"],
				"dasharray": f"{pct:.3f} {100 - pct:.3f}",
				"dashoffset": f"{125 - acumulado:.3f}",
			}
		)
		acumulado += pct
	return {"total": total, "segmentos": segmentos}


def _waterfall(steps: list[dict], resultado: float) -> dict | None:
	"""Geometria (px) das barras do waterfall financeiro para um SVG estático."""
	if not steps:
		return None
	largura, altura = 540.0, 230.0
	pad_top, pad_bottom, pad_lado = 16.0, 46.0, 10.0

	pontos = []  # (label, inicio, fim, valor)
	running = 0.0
	for s in steps:
		valor = flt(s["valor"])
		pontos.append((s["label"], running, running + valor, valor))
		running += valor
	pontos.append(("Resultado", 0.0, flt(resultado), flt(resultado)))

	valores_eixo = [0.0]
	for _rotulo, inicio, fim, _acumulado in pontos:
		valores_eixo += [inicio, fim]
	vmin, vmax = min(valores_eixo), max(valores_eixo)
	if vmax == vmin:
		vmax = vmin + 1
	plot_h = altura - pad_top - pad_bottom

	def y_de(v: float) -> float:
		return pad_top + (vmax - v) / (vmax - vmin) * plot_h

	n = len(pontos)
	slot = (largura - 2 * pad_lado) / n
	bar_w = min(slot * 0.55, 56.0)

	barras = []
	for i, (label, inicio, fim, valor) in enumerate(pontos):
		cx = pad_lado + slot * i + slot / 2
		y_top = y_de(max(inicio, fim))
		h = max(abs(y_de(inicio) - y_de(fim)), 1.0)
		cor = _COR_NAVY if label == "Resultado" else (_COR_ENTROU if valor >= 0 else _COR_NAO_ENTROU)
		barras.append(
			{
				"x": cx - bar_w / 2,
				"y": y_top,
				"w": bar_w,
				"h": h,
				"cx": cx,
				"cor": cor,
				"label": label,
				"valor": valor,
				"valor_y": y_top - 5,
			}
		)
	return {
		"width": largura,
		"height": altura,
		"zero_y": y_de(0.0),
		"label_y": altura - pad_bottom + 14,
		"barras": barras,
	}


def _serie(linha: list[dict], modo: str) -> dict | None:
	"""Pontos de uma série temporal (linha + área) para um SVG estático.

	`modo`: ``"qtd"`` (entradas por janela de 15 min) ou ``"acumulado"``.
	"""
	if not linha:
		return None
	chave = "acumulado" if modo == "acumulado" else "qtd"
	valores = [flt(p.get(chave)) for p in linha]
	largura, altura = 540.0, 170.0
	pad_top, pad_bottom, pad_lado = 12.0, 26.0, 10.0
	plot_h = altura - pad_top - pad_bottom
	plot_w = largura - 2 * pad_lado
	vmax = max(valores) or 1.0
	n = len(valores)

	def x_de(i: int) -> float:
		return pad_lado + (plot_w * (i / (n - 1) if n > 1 else 0.5))

	def y_de(v: float) -> float:
		return pad_top + (1 - v / vmax) * plot_h

	pts = [(x_de(i), y_de(v)) for i, v in enumerate(valores)]
	base_y = pad_top + plot_h
	linha_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
	area_pts = f"{pts[0][0]:.1f},{base_y:.1f} {linha_pts} {pts[-1][0]:.1f},{base_y:.1f}"

	rotulos = []
	for p in linha:
		b = str(p.get("bin") or "")
		rotulos.append(b[11:16] if len(b) >= 16 else b)
	marcas = [{"x": x_de(i), "label": rotulos[i]} for i in sorted({0, n // 2, n - 1}) if 0 <= i < n]
	return {
		"width": largura,
		"height": altura,
		"base_y": base_y,
		"vmax": vmax,
		"linha": linha_pts,
		"area": area_pts,
		"pontos": [{"x": round(x, 1), "y": round(y, 1)} for x, y in pts],
		"marcas": marcas,
		"label_y": altura - pad_bottom + 14,
	}


def _build_pdf_visuais(payload: dict) -> dict:
	"""Calcula a geometria dos visuais estáticos do PDF a partir do payload."""
	chart = (payload.get("convites_secao") or {}).get("chart") or {}
	pizza = chart.get("pizza") or {}
	origem = chart.get("origem") or {}
	linha = chart.get("linha") or []

	return {
		"donut_entradas": _donut(
			[
				{"label": "Entrou", "value": cint(pizza.get("entrou")), "color": _COR_ENTROU},
				{"label": "Não entrou", "value": cint(pizza.get("nao_entrou")), "color": _COR_NAO_ENTROU},
				{
					"label": "Comprou na portaria",
					"value": cint(pizza.get("comprou_portaria")),
					"color": _COR_PORTARIA,
				},
			]
		),
		"donut_origem": _donut(
			[
				{
					"label": "Compra prévia",
					"value": cint(origem.get("compra_previa")),
					"color": _COR_COMPRA_PREVIA,
				},
				{
					"label": "Compra na portaria",
					"value": cint(origem.get("compra_portaria")),
					"color": _COR_COMPRA_PORTARIA,
				},
			]
		),
		"donut_previa": _donut(
			[
				{"label": "Entrou", "value": cint(pizza.get("entrou")), "color": _COR_ENTROU},
				{"label": "Não entrou", "value": cint(pizza.get("nao_entrou")), "color": _COR_NAO_ENTROU},
			]
		),
		"waterfall": _waterfall(
			(payload.get("chart_data") or {}).get("waterfall") or [], flt(payload.get("resultado"))
		),
		"serie_janela": _serie(linha, "qtd"),
		"serie_acumulado": _serie(linha, "acumulado"),
	}


def _render_pdf_template(rel_path: str, ctx: dict) -> str:
	path = os.path.join(frappe.get_app_path("gris"), rel_path)
	with open(path, encoding="utf-8") as fh:
		return frappe.render_template(fh.read(), ctx)


def _gerar_relatorio_pdf_bytes(festa_name: str) -> bytes:
	"""Monta o PDF completo (capa + corpo) com WeasyPrint.

	O corpo é o documento mestre e inclui a capa numa página nomeada `cover`
	(full-bleed, sem rodapé). O número de página vem de `counter(page)` na
	margin box do `@page`; a faixa de marca do rodapé é um elemento
	`position:fixed`. `base_url` aponta para `gris/public/` para resolver a web
	font Figtree do `@font-face`.
	"""
	from weasyprint import HTML

	payload = build_relatorio_payload(festa_name)
	uel = frappe.get_cached_doc("Definicao da UEL")
	ctx = {
		**payload,
		"uel_logo": _logo_uel_data_uri(),
		"uel_tipo": uel.get("tipo_uel") or "",
		"uel_nome": uel.get("nome_da_uel") or "",
		"gerado_em": format_date(today(), "dd/MM/yyyy"),
		"visuais": _build_pdf_visuais(payload),
		# Compras/contratações já fatiadas em folhas (conteúdo rotacionado de lado).
		"compras_paginas": _paginar_compras(payload["compras"]),
		"contratacoes_paginas": _paginar_contratacoes(payload["contratacoes"]),
	}

	ctx["capa_html"] = _render_pdf_template(_CAPA_TEMPLATE, ctx)
	html = _render_pdf_template(_CORPO_TEMPLATE, ctx)
	base_url = frappe.get_app_path("gris", "public") + os.sep
	return HTML(string=html, base_url=base_url).write_pdf()


@frappe.whitelist()
def download_relatorio_pdf(festa_name: str) -> None:
	"""Gera e disponibiliza o relatório completo da festa em PDF (capa + corpo)."""
	if not festa_name:
		frappe.throw(_("Parâmetro 'festa_name' obrigatório."), frappe.ValidationError)
	if not frappe.has_permission("Festa", "read", festa_name):
		frappe.throw(_("Sem permissão para acessar esta festa."), frappe.PermissionError)
	if not relatorio_disponivel(festa_name):
		frappe.throw(_("Relatório indisponível: a avaliação da equipe ainda não foi iniciada."))

	nome_festa = frappe.db.get_value("Festa", festa_name, "nome_festa") or festa_name
	frappe.local.response.filename = f"relatorio-{frappe.scrub(nome_festa)}.pdf"
	frappe.local.response.filecontent = _gerar_relatorio_pdf_bytes(festa_name)
	frappe.local.response.type = "pdf"
