"""Demonstrativo financeiro anual: cálculo compartilhado e exportação em Excel.

A página `/financeiro/demonstrativo` e o download em `.xlsx` usam o mesmo
`montar_demonstrativo`, para que o arquivo exportado bata linha a linha com o
que a tela mostra.
"""

import io
from datetime import datetime

import frappe
from frappe import _

from gris.api.portal_access import user_has_access

DOCTYPE = "Transacao Extrato Geral"
# A página do demonstrativo é aberta a partir de Relatórios e herda a mesma regra de acesso.
ROTA_ACESSO = "/financeiro/relatorios"

MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

FILTROS_BASE = [
	["metodo", "!=", "Dinheiro"],
	["repasse_entre_contas", "=", 0],
	["excluir_do_total", "=", 0],
]


def normalizar_ano(ano) -> int:
	try:
		return int(ano)
	except (TypeError, ValueError):
		return datetime.now().year


def _mes_da_data(data) -> int | None:
	if not data:
		return None
	if isinstance(data, str):
		try:
			return int(data.split("-")[1])
		except (IndexError, ValueError):
			return None
	return data.month


def montar_demonstrativo(ano) -> dict:
	"""Soma as transações do ano por seção (entradas/saídas), categoria e mês.

	Considera só transações fora de dinheiro, que não são repasse entre contas e
	não estão marcadas para excluir do total. O saldo inicial de janeiro é a soma
	de tudo antes do ano; cada mês seguinte começa no saldo final do anterior.
	"""
	ano = normalizar_ano(ano)
	sufixo = str(ano)[-2:]
	months = [{"key": i + 1, "label": f"{abrev}-{sufixo}"} for i, abrev in enumerate(MESES_ABREV)]
	chaves = [m["key"] for m in months]

	inicio = f"{ano}-01-01"
	fim = f"{ano}-12-31"

	trans = frappe.get_all(
		DOCTYPE,
		fields=["data_deposito", "categoria", "valor_absoluto", "debito_credito", "ordinaria_extraordinaria"],
		filters=[["data_deposito", ">=", inicio], ["data_deposito", "<=", fim], *FILTROS_BASE],
		limit_page_length=0,
	)

	data = {"entradas": {}, "saidas": {}}
	month_totals = {"entradas": dict.fromkeys(chaves, 0.0), "saidas": dict.fromkeys(chaves, 0.0)}
	month_totals_ordinarias = {
		"entradas": dict.fromkeys(chaves, 0.0),
		"saidas": dict.fromkeys(chaves, 0.0),
	}

	for t in trans:
		m = _mes_da_data(t.get("data_deposito"))
		if not m:
			continue
		cat = t.get("categoria") or "(Sem Categoria)"
		val = t.get("valor_absoluto") or 0.0
		sec = "entradas" if t.get("debito_credito") == "Crédito" else "saidas"

		data[sec].setdefault(cat, {}).setdefault(m, 0.0)
		data[sec][cat][m] += val
		month_totals[sec][m] += val
		if t.get("ordinaria_extraordinaria") == "Ordinária":
			month_totals_ordinarias[sec][m] += val

	pre_tx = frappe.get_all(
		DOCTYPE,
		fields=["SUM(valor) as total"],
		filters=[["data_deposito", "<", inicio], *FILTROS_BASE],
		limit_page_length=0,
	)
	total_antes = (pre_tx[0].get("total") or 0.0) if pre_tx else 0.0

	saldo_inicial = {}
	saldo_final = {}
	for m in chaves:
		saldo_inicial[m] = total_antes if m == 1 else saldo_final[m - 1]
		saldo_final[m] = saldo_inicial[m] + month_totals["entradas"][m] - month_totals["saidas"][m]

	return {
		"year": ano,
		"months": months,
		"entradas_cats": sorted(data["entradas"]),
		"saidas_cats": sorted(data["saidas"]),
		"data": data,
		"month_totals": month_totals,
		"month_totals_ordinarias": month_totals_ordinarias,
		"saldo_inicial": saldo_inicial,
		"saldo_final": saldo_final,
	}


def listar_anos_disponiveis(ano_atual: int) -> list[int]:
	"""Anos com transação no extrato, do mais recente ao mais antigo, sempre incluindo `ano_atual`."""
	try:
		rows = frappe.db.sql(
			"""
			SELECT DISTINCT YEAR(data_deposito) AS y
			FROM `tabTransacao Extrato Geral`
			WHERE data_deposito IS NOT NULL
			ORDER BY y DESC
			""",
			as_list=True,
		)
		anos = [int(r[0]) for r in rows if r and r[0]]
	except Exception:
		return list(range(ano_atual - 4, ano_atual + 2))
	if ano_atual not in anos:
		anos.insert(0, ano_atual)
	return anos


def gerar_planilha_demonstrativo(demo: dict) -> bytes:
	"""Monta o .xlsx com a mesma estrutura da tabela da página."""
	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
	from openpyxl.utils import get_column_letter

	months = demo["months"]
	n_cols = len(months) + 1
	formato_moeda = '"R$" #,##0.00;[Red]-"R$" #,##0.00'
	formato_valor = "#,##0.00;[Red]-#,##0.00"

	wb = Workbook()
	ws = wb.active
	ws.title = f"Demonstrativo {demo['year']}"

	fonte_titulo = Font(bold=True, size=14)
	fonte_negrito = Font(bold=True)
	fonte_cabecalho = Font(bold=True, color="FFFFFF")
	fill_cabecalho = PatternFill(start_color="0D4D91", end_color="0D4D91", fill_type="solid")
	fill_saldo = PatternFill(start_color="E8EEF6", end_color="E8EEF6", fill_type="solid")
	fill_entradas = PatternFill(start_color="E6F4EA", end_color="E6F4EA", fill_type="solid")
	fill_saidas = PatternFill(start_color="FCE8E6", end_color="FCE8E6", fill_type="solid")
	borda_topo = Border(top=Side(style="thin", color="999999"))
	centro = Alignment(horizontal="center", vertical="center")

	ws.cell(row=1, column=1, value=f"Demonstrativo Financeiro {demo['year']}").font = fonte_titulo
	ws.cell(
		row=2,
		column=1,
		value=f"Gerado em {frappe.utils.format_datetime(frappe.utils.now_datetime(), 'dd/MM/yyyy HH:mm')}",
	).font = Font(italic=True, color="666666")

	linha = 4
	cabecalho = ["Categoria"] + [m["label"] for m in months]
	for col, titulo in enumerate(cabecalho, start=1):
		cell = ws.cell(row=linha, column=col, value=titulo)
		cell.font = fonte_cabecalho
		cell.fill = fill_cabecalho
		cell.alignment = centro
	linha_cabecalho = linha

	def escrever_linha(rotulo, valores, *, negrito=False, fill=None, formato=formato_valor, borda=None):
		nonlocal linha
		linha += 1
		cell = ws.cell(row=linha, column=1, value=rotulo)
		if negrito:
			cell.font = fonte_negrito
		for col, valor in enumerate(valores, start=2):
			c = ws.cell(row=linha, column=col, value=round(valor or 0.0, 2))
			c.number_format = formato
			if negrito:
				c.font = fonte_negrito
		for col in range(1, n_cols + 1):
			c = ws.cell(row=linha, column=col)
			if fill:
				c.fill = fill
			if borda:
				c.border = borda

	def escrever_secao(rotulo, fill):
		nonlocal linha
		linha += 1
		ws.cell(row=linha, column=1, value=rotulo).font = fonte_negrito
		for col in range(1, n_cols + 1):
			ws.cell(row=linha, column=col).fill = fill

	chaves = [m["key"] for m in months]
	totais = demo["month_totals"]
	ordinarias = demo["month_totals_ordinarias"]

	escrever_linha(
		"Saldo Inicial",
		[demo["saldo_inicial"].get(k) for k in chaves],
		negrito=True,
		fill=fill_saldo,
		formato=formato_moeda,
	)

	escrever_secao("Entradas (Créditos)", fill_entradas)
	for cat in demo["entradas_cats"]:
		escrever_linha(f"  {cat}", [demo["data"]["entradas"].get(cat, {}).get(k) for k in chaves])
	escrever_linha(
		"Total Entradas",
		[totais["entradas"].get(k) for k in chaves],
		negrito=True,
		formato=formato_moeda,
		borda=borda_topo,
	)

	escrever_secao("Saídas (Débitos)", fill_saidas)
	for cat in demo["saidas_cats"]:
		escrever_linha(f"  {cat}", [demo["data"]["saidas"].get(cat, {}).get(k) for k in chaves])
	escrever_linha(
		"Total Saídas",
		[totais["saidas"].get(k) for k in chaves],
		negrito=True,
		formato=formato_moeda,
		borda=borda_topo,
	)

	escrever_linha(
		"Resultado do Mês",
		[(totais["entradas"].get(k) or 0) - (totais["saidas"].get(k) or 0) for k in chaves],
		negrito=True,
		formato=formato_moeda,
	)
	escrever_linha(
		"Resultado Ordinário",
		[(ordinarias["entradas"].get(k) or 0) - (ordinarias["saidas"].get(k) or 0) for k in chaves],
		negrito=True,
		formato=formato_moeda,
	)
	escrever_linha(
		"Saldo Final",
		[demo["saldo_final"].get(k) for k in chaves],
		negrito=True,
		fill=fill_saldo,
		formato=formato_moeda,
	)

	ws.column_dimensions["A"].width = 40
	for col in range(2, n_cols + 1):
		ws.column_dimensions[get_column_letter(col)].width = 15
	ws.freeze_panes = ws.cell(row=linha_cabecalho + 1, column=2)

	out = io.BytesIO()
	wb.save(out)
	return out.getvalue()


@frappe.whitelist()
def exportar_demonstrativo_excel(ano: str | int | None = None) -> None:
	"""Baixa o demonstrativo financeiro do ano em .xlsx (mesmo conteúdo da página)."""
	if frappe.session.user == "Guest" or not user_has_access(ROTA_ACESSO):
		frappe.throw(_("Sem permissão para exportar o demonstrativo financeiro."), frappe.PermissionError)

	demo = montar_demonstrativo(ano or datetime.now().year)

	frappe.local.response.filename = f"demonstrativo-financeiro-{demo['year']}.xlsx"
	frappe.local.response.filecontent = gerar_planilha_demonstrativo(demo)
	frappe.local.response.type = "download"
