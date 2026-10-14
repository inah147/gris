"""Exportação completa da festa em PDF, aba por aba.

Cada aba da página `/festas/festa` vira uma seção do PDF que começa em página
nova (Dados gerais, Produtos vendidos, Compras, Contratações, Orçamento,
Fechamento, Gestão de tarefas, Convites e Avaliações). Diferente do relatório
(`relatorio.py`), que só existe após a avaliação da equipe, esta exportação
fica disponível desde o planejamento.

Os dados vêm dos mesmos montadores da página e do relatório, para o PDF bater
com o que a pessoa vê na tela: `build_festa_payload` (planejamento),
`build_relatorio_payload` (fechamento realizado, convites e avaliações).
Renderizado com WeasyPrint em A4 paisagem; as tabelas paginam sozinhas e
repetem o cabeçalho em cada folha.
"""

from __future__ import annotations

import base64
import io
import os
from urllib.parse import unquote, urlparse

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, format_date, getdate, today

from gris.api.festas.relatorio import _waterfall, build_relatorio_payload, relatorio_disponivel
from gris.api.portal_access import user_has_access

_TEMPLATE = "templates/pages/festa_dados_pdf.html"

_CENARIOS = (
	("min", "Mínimo"),
	("intermediario", "Intermediário"),
	("max", "Máximo"),
)

# Status da Gestão de Tarefas (valores do Select sem acento) -> rótulo e ordem.
_STATUS_TAREFA = {
	"Nao iniciado": "Não iniciado",
	"Em andamento": "Em andamento",
	"Atrasado": "Atrasado",
	"Validar": "Validar",
	"Concluido": "Concluído",
	"Cancelado": "Cancelado",
}
_ORDEM_STATUS_TAREFA = list(_STATUS_TAREFA)


def _data_br(value) -> str:
	return format_date(value, "dd/MM/yyyy") if value else ""


def _num(value) -> str:
	"""Número no formato brasileiro, com até 2 casas e sem zeros à direita (1.234,5)."""
	texto = f"{flt(value):,.2f}".rstrip("0").rstrip(".")
	return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _moeda(value) -> str:
	"""Valor em reais no formato brasileiro (R$ 1.234,50), independente da configuração do site."""
	return fmt_money(flt(value), precision=2, currency="BRL", format="#.###,##")


def _logo_data_uri() -> str:
	"""Logo da UEL (ou do Gris, como fallback) em data-URI PNG."""
	from gris.festas.utils.convite_qr import _carregar_logo

	try:
		logo = _carregar_logo()
	except Exception:
		frappe.log_error(message=frappe.get_traceback(), title="Falha ao carregar logo para PDF da festa")
		return ""
	if logo is None:
		return ""
	buf = io.BytesIO()
	logo.save(buf, format="PNG")
	return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _linhas_cenario(itens: list[dict]) -> dict:
	"""Linhas de uma tabela "esperado por cenário" (áreas/barracas) com o total."""
	total = {chave: 0.0 for chave, _rotulo in _CENARIOS}
	for item in itens:
		for chave, _rotulo in _CENARIOS:
			total[chave] += flt(item.get(f"esperado_{chave}"))
	return {"linhas": itens, "total": total}


def _montar_compras(compras: list[dict]) -> list[dict]:
	"""Compras previstas (aba Compras), com cotação escolhida e produtos que usam o item."""
	resultado = []
	for c in compras:
		if not c.get("previsto"):
			continue
		escolhida = next((cot for cot in c.get("cotacoes") or [] if cot.get("escolhida")), None)
		resultado.append(
			{
				**c,
				"fornecedor_escolhido": (escolhida or {}).get("fornecedor") or "",
				"cotacao_escolhida": escolhida,
				"produtos_uso": [u.get("produto_label") for u in c.get("usos_em_produto") or []],
			}
		)
	return resultado


def _montar_contratacoes(contratacoes: list[dict]) -> list[dict]:
	resultado = []
	for c in contratacoes:
		if not c.get("previsto"):
			continue
		escolhida = next((cot for cot in c.get("cotacoes") or [] if cot.get("escolhida")), None)
		resultado.append({**c, "fornecedor_escolhido": (escolhida or {}).get("fornecedor") or ""})
	return resultado


def _montar_tarefas(board_name: str) -> dict:
	"""Tarefas do board da festa, ordenadas por status e prazo, com contagem por status."""
	if not board_name:
		return {"linhas": [], "contagem": []}

	rows = frappe.get_all(
		"Gestao de Tarefas",
		filters={"board": board_name},
		fields=["descricao", "responsavel", "status", "data_inicio", "prazo", "data_entrega", "observacoes"],
		order_by="prazo asc, creation asc",
	)
	responsaveis = {r.responsavel for r in rows if r.responsavel}
	nomes = {}
	if responsaveis:
		nomes = {
			u.name: u.full_name or u.name
			for u in frappe.get_all(
				"User", filters={"name": ["in", list(responsaveis)]}, fields=["name", "full_name"]
			)
		}

	def _ordem(status: str) -> int:
		return _ORDEM_STATUS_TAREFA.index(status) if status in _ORDEM_STATUS_TAREFA else len(_STATUS_TAREFA)

	rows.sort(key=lambda r: _ordem(r.status or ""))
	linhas = [
		{
			"descricao": r.descricao or "",
			"responsavel": nomes.get(r.responsavel, r.responsavel or ""),
			"status": _STATUS_TAREFA.get(r.status, r.status or ""),
			"data_inicio": _data_br(r.data_inicio),
			"prazo": _data_br(r.prazo),
			"data_entrega": _data_br(r.data_entrega),
			"observacoes": r.observacoes or "",
		}
		for r in rows
	]
	contagem = []
	for status, rotulo in _STATUS_TAREFA.items():
		qtd = sum(1 for r in rows if r.status == status)
		if qtd:
			contagem.append({"status": rotulo, "qtd": qtd})
	return {"linhas": linhas, "contagem": contagem}


def _montar_convites(dashboard: dict, payload: dict) -> dict:
	"""Configuração, indicadores, tipos de convite, vendas por dia e pedidos (aba Convites)."""
	totais = dashboard.get("totais") or {}
	qtd_por_opcao = totais.get("qtd_por_opcao") or {}
	valor_por_opcao = totais.get("valor_por_opcao") or {}
	opcoes = dashboard.get("opcoes") or []

	tipos = [
		{
			**op,
			"qtd_paga": cint(qtd_por_opcao.get(op["name"], 0)),
			"valor_pago": flt(valor_por_opcao.get(op["name"], 0)),
		}
		for op in opcoes
	]

	total_vendidos = sum(cint(v) for v in qtd_por_opcao.values())
	receita = sum(flt(v) for v in valor_por_opcao.values())
	if dashboard.get("aceitar_doacoes"):
		receita += flt(totais.get("total_doacoes_valor"))

	cenario = dashboard.get("cenario_simulacao") or "Intermediário"
	esperado = {
		"Mínimo": payload.get("expectativa_min"),
		"Intermediário": payload.get("expectativa_intermediario"),
		"Máximo": payload.get("expectativa_max"),
	}.get(cenario)
	esperado = cint(esperado)

	vendas_dia: dict[str, dict] = {}
	for s in dashboard.get("series_por_dia") or []:
		dia = vendas_dia.setdefault(s["dia"], {"dia": _data_br(s["dia"]), "quantidade": 0, "valor": 0.0})
		dia["quantidade"] += cint(s.get("quantidade"))
		dia["valor"] += flt(s.get("valor"))

	pedidos = [
		{
			**p,
			"data": _data_br(getdate(p["creation"])) if p.get("creation") else "",
		}
		for p in dashboard.get("convites") or []
	]

	por_ramo = [
		{
			"ramo": ramo,
			**dados,
			"pct": (dados["qtd_vendida"] / dados["qtd_esperada"] * 100) if dados.get("qtd_esperada") else None,
			"faltam": max(cint(dados.get("qtd_esperada")) - cint(dados.get("qtd_vendida")), 0),
		}
		for ramo, dados in (dashboard.get("por_ramo") or {}).items()
	]

	return {
		"config": {
			"tipos_ativos": sum(1 for op in opcoes if op.get("ativo")),
			"tipos_total": len(opcoes),
			"aceitar_doacoes": bool(dashboard.get("aceitar_doacoes")),
			"venda_na_portaria": bool(dashboard.get("venda_na_portaria")),
			"data_limite_vendas": _data_br(dashboard.get("data_limite_vendas")),
		},
		"kpis": {
			"vendidos": total_vendidos,
			"receita": receita,
			"cenario": cenario,
			"esperado": esperado,
			"taxa": (total_vendidos / esperado * 100) if esperado else None,
		},
		"tipos": tipos,
		"doacoes": flt(totais.get("total_doacoes_valor")),
		"por_ramo": por_ramo if dashboard.get("convites_por_ramo") else [],
		"vendas_dia": list(vendas_dia.values()),
		"pedidos": pedidos,
	}


def build_exportacao_context(festa_name: str) -> dict:
	"""Contexto completo do PDF da festa (uma seção por aba da página)."""
	# Import tardio: `www/festas/festa.py` é módulo de página do portal.
	from gris.www.festas.festa import build_festa_payload

	payload = build_festa_payload(festa_name)
	relatorio = build_relatorio_payload(festa_name)
	uel = frappe.get_cached_doc("Definicao da UEL")

	produtos = sorted(
		payload["produtos"], key=lambda p: ((p["nome_barraca"] or "").casefold(), p["nome_produto"].casefold())
	)

	return {
		"festa": payload,
		"cenarios": _CENARIOS,
		"produtos": produtos,
		"compras": _montar_compras(payload["compras"]),
		"contratacoes": _montar_contratacoes(payload["contratacoes"]),
		"receitas_area": _linhas_cenario(payload["receitas_por_area"]),
		"despesas_area": _linhas_cenario(payload["despesas_por_area"]),
		"receitas_barraca": _linhas_cenario(payload["receitas_por_barraca"]),
		"despesas_barraca": _linhas_cenario(payload["despesas_por_barraca"]),
		"fechamento": relatorio,
		"waterfall": _waterfall(
			(relatorio.get("chart_data") or {}).get("waterfall") or [], flt(relatorio.get("resultado"))
		),
		"tarefas": _montar_tarefas(payload.get("festa_board_name")),
		"convites": _montar_convites(payload["convites_dashboard"], payload),
		"avaliacoes": relatorio.get("avaliacoes"),
		"avaliacao_equipe_iniciada": relatorio_disponivel(festa_name),
		"uel_logo": _logo_data_uri(),
		"uel_nome": ((uel.get("tipo_uel") or "") + " " + (uel.get("nome_da_uel") or "")).strip(),
		"gerado_em": _data_br(today()),
		"num": _num,
		"moeda": _moeda,
	}


def _render_template(ctx: dict) -> str:
	path = os.path.join(frappe.get_app_path("gris"), _TEMPLATE)
	# Caminho fixo do módulo (constante acima), nunca vem de entrada do usuário.
	with open(path, encoding="utf-8") as fh:  # nosemgrep
		return frappe.render_template(fh.read(), ctx)  # nosemgrep


def _url_fetcher(url: str, *args, **kwargs):
	"""Só deixa o WeasyPrint carregar data-URIs e arquivos de `gris/public/` (fonte).

	O PDF mostra texto digitado por usuários (e resumos de IA em markdown); mesmo
	escapado, nada no documento deve fazer o servidor buscar URLs externas.
	"""
	try:
		from weasyprint import URLFetcher

		fetch = URLFetcher().fetch
	except ImportError:  # WeasyPrint < 66
		from weasyprint import default_url_fetcher as fetch

	if url.startswith("data:"):
		return fetch(url, *args, **kwargs)
	if url.startswith("file://"):
		publico = os.path.realpath(frappe.get_app_path("gris", "public")) + os.sep
		caminho = os.path.realpath(unquote(urlparse(url).path))
		if caminho.startswith(publico):
			return fetch(url, *args, **kwargs)
	raise ValueError(f"Recurso externo bloqueado no PDF da festa: {url[:80]}")


def gerar_pdf_festa_bytes(festa_name: str) -> bytes:
	from weasyprint import HTML

	html = _render_template(build_exportacao_context(festa_name))
	# base_url em gris/public/ resolve a fonte Figtree do @font-face.
	base_url = frappe.get_app_path("gris", "public") + os.sep
	return HTML(string=html, base_url=base_url, url_fetcher=_url_fetcher).write_pdf()


@frappe.whitelist()
def download_festa_pdf(festa_name: str) -> None:
	"""Baixa todos os dados da festa em PDF, uma aba da página por seção."""
	if not festa_name:
		frappe.throw(_("Parâmetro 'festa_name' obrigatório."), frappe.ValidationError)
	if not frappe.db.exists("Festa", festa_name):
		frappe.throw(_("Festa não encontrada."), frappe.DoesNotExistError)
	if not user_has_access("/festas/festa") or not frappe.has_permission("Festa", "read", festa_name):
		frappe.throw(_("Sem permissão para acessar esta festa."), frappe.PermissionError)

	nome_festa = frappe.db.get_value("Festa", festa_name, "nome_festa") or festa_name
	frappe.local.response.filename = f"festa-{frappe.scrub(nome_festa)}.pdf"
	frappe.local.response.filecontent = gerar_pdf_festa_bytes(festa_name)
	frappe.local.response.type = "pdf"
