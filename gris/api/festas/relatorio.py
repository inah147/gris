"""Relatório completo da festa.

Agregação somente-leitura usada pela página de portal `/festas/relatorio`. As
consultas são *set-based* (`frappe.get_all` com `fields=` + mapas em memória),
evitando o N+1 do payload da página de edição da festa. Receita de convites e
avaliações reaproveitam o código já existente.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint, flt, format_date

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
		mapa.setdefault(row.parent, []).append(
			{"nome": row.nome or "", "funcao": row.funcao or ""}
		)
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
	distribuicao = [sum(1 for n in notas if n == i) for i in range(11)]

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
		],
		order_by="nome_item asc",
	)
	forn_compra = _fornecedor_escolhido(
		"Cotacao Compra Festa", "Compra Festa", [c.name for c in compras]
	)
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
		}
		for c in contratacoes
	]

	# Despesa realizada por área (compras + contratações).
	despesa_area: dict[str, float] = {}
	for c in compras:
		despesa_area[c.area or ""] = despesa_area.get(c.area or "", 0.0) + flt(c.valor_total_realizado)
	for c in contratacoes:
		despesa_area[c.area or ""] = despesa_area.get(c.area or "", 0.0) + flt(c.valor_total_realizado)
	despesas_por_area = [
		{"label": area_nome.get(a, "Sem área") if a else "Sem área", "valor": v}
		for a, v in despesa_area.items()
	]
	despesas_por_area.sort(key=lambda x: x["valor"], reverse=True)

	# ── Totais do fechamento ────────────────────────────────────────────────
	arrecadacao_barracas = sum(flt(b.valor_arrecadado_realizado_real) for b in barracas)
	arrecadacao = receita_convites + receita_doacoes + arrecadacao_barracas
	despesas = sum(x["valor"] for x in despesas_por_area)
	resultado = arrecadacao - despesas

	# Passos do waterfall: entradas (+) e despesas por area (-); o JS acumula e
	# fecha com a barra de Resultado.
	waterfall = [{"label": "Convites", "valor": receita_convites}]
	if receita_doacoes:
		waterfall.append({"label": "Doações", "valor": receita_doacoes})
	waterfall += [{"label": b["label"], "valor": b["valor"]} for b in barracas_receita]
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
		"receitas_barracas": barracas_receita,
		"despesas_por_area": despesas_por_area,
		"arrecadacao": arrecadacao,
		"despesas": despesas,
		"resultado": resultado,
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
		frappe.throw("Parâmetro 'festa_name' obrigatório.", frappe.ValidationError)
	if not frappe.has_permission("Festa", "read", festa_name):
		frappe.throw("Sem permissão para acessar esta festa.", frappe.PermissionError)
	if not relatorio_disponivel(festa_name):
		frappe.throw("Relatório indisponível: a avaliação da equipe ainda não foi iniciada.")
	return build_relatorio_payload(festa_name)
