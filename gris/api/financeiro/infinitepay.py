import ast
import csv
import hashlib
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Optional

import dateparser
import frappe
import numpy as np
import pandas as pd
from ofxparse import OfxParser

# ----------------------------------------------------------

# Detecção de formato
#
# A Infinitepay mudou os formatos de exportação: o extrato passou a sair como
# página HTML ("Relatório de movimentações" da Conta Web — ainda com extensão
# .ofx no download) e os relatórios de vendas/recebimentos ganharam versão XML.
# Os formatos antigos (OFX e CSV) continuam suportados; o formato é detectado
# pelo conteúdo do arquivo, não pela extensão.

FORMATO_OFX = "ofx"
FORMATO_HTML = "html"
FORMATO_XML = "xml"
FORMATO_CSV = "csv"


def _read_text(file_path: str) -> str:
	"""Lê o arquivo como texto, tolerando UTF-8 (com ou sem BOM) e Latin-1."""
	# Helper privado: só recebe caminhos resolvidos no servidor a partir de um File.
	with open(file_path, "rb") as f:  # nosemgrep
		raw = f.read()
	for encoding in ("utf-8-sig", "latin-1"):
		try:
			return raw.decode(encoding)
		except UnicodeDecodeError:
			continue
	return raw.decode("utf-8", errors="replace")


def _detect_format(file_path: str) -> str:
	"""Descobre o formato do arquivo pelo conteúdo (não pela extensão)."""
	head = _read_text(file_path)[:4096].lstrip().lower()
	if "ofxheader" in head or "<ofx>" in head:
		return FORMATO_OFX
	if "<!doctype html" in head or "<html" in head:
		return FORMATO_HTML
	if head.startswith("<"):
		return FORMATO_XML
	return FORMATO_CSV


# Tipos de anexo Infinitepay reconhecidos por `identificar_tipo_arquivo`.
TIPO_EXTRATO = "extrato"
TIPO_VENDAS = "vendas"
TIPO_RECEBIMENTOS = "recebimentos"

_RAIZES_XML_VENDAS = {"sales_report"}
_RAIZES_XML_RECEBIMENTOS = {"transaction_payments", "proof_of_transfer"}


def identificar_tipo_arquivo(file_path: str) -> str | None:
	"""Identifica se um arquivo Infinitepay é o extrato, as vendas ou os recebimentos.

	Usada pela importação automática via e-mail, que recebe os três anexos sem nome
	de arquivo confiável (o cliente de e-mail pode renomeá-los) e precisa distinguir
	o conteúdo antes de escolher o parser certo. Devolve ``None`` quando o conteúdo
	não corresponde a nenhum dos três relatórios (ex.: PDF de capa do e-mail).
	"""
	formato = _detect_format(file_path)
	if formato in (FORMATO_HTML, FORMATO_OFX):
		return TIPO_EXTRATO
	if formato == FORMATO_XML:
		try:
			raiz = ET.fromstring(_read_text(file_path)).tag
		except ET.ParseError:
			return None
		if raiz in _RAIZES_XML_VENDAS:
			return TIPO_VENDAS
		if raiz in _RAIZES_XML_RECEBIMENTOS:
			return TIPO_RECEBIMENTOS
		return None
	if formato == FORMATO_CSV:
		# O CSV de recebimentos é sempre lido com delimitador ";" (ver
		# `get_infinitepay_receipts_df`); o de vendas usa o padrão "," do pandas.
		# Um limiar de colunas evita classificar como relatório qualquer texto
		# solto que caia no formato CSV por eliminação (ex.: anexo não relacionado
		# no mesmo e-mail do fechamento).
		texto = _read_text(file_path)
		primeira_linha = texto.splitlines()[0] if texto else ""
		colunas_minimas = len(COLUNAS_VENDAS) // 3
		if primeira_linha.count(";") >= colunas_minimas:
			return TIPO_RECEBIMENTOS
		if primeira_linha.count(",") >= colunas_minimas:
			return TIPO_VENDAS
		return None
	return None


def _limpar_espacos(texto: str) -> str:
	"""Normaliza espaços (inclui NBSP) e remove sobras nas pontas."""
	return re.sub(r"\s+", " ", (texto or "").replace("\xa0", " ")).strip()


def _normalize_column(col):
	nfkd = unicodedata.normalize("NFKD", col)
	no_accents = "".join([c for c in nfkd if not unicodedata.combining(c)])
	no_specials = re.sub(r"\W+", "_", no_accents)
	return no_specials.lower().strip("_")


def _parse_valor_br(texto) -> float | None:
	"""Converte valor no formato brasileiro ('+1.234,56', '- 12,50', 'R$ 7,00') em float.

	O ponto é sempre separador de milhar e a vírgula, decimal — é o formato usado
	no extrato HTML, no relatório de vendas XML e no comprovante de transferência.
	"""
	t = _limpar_espacos(str(texto)) if texto is not None else ""
	if not t:
		return None
	negativo = t.startswith("-")
	t = t.lstrip("+-").replace("R$", "").replace("'", "").strip()
	# sinal pode vir depois do prefixo (ex.: "'- 0,80")
	if t.startswith("-"):
		negativo = True
		t = t.lstrip("-").strip()
	t = t.replace(".", "").replace(",", ".")
	try:
		valor = float(t)
	except ValueError:
		return None
	return -valor if negativo else valor


def _parse_numero_flex(texto) -> float | None:
	"""Converte número que pode vir com decimal por vírgula ('12,50') ou ponto ('12.5')."""
	t = _limpar_espacos(str(texto)) if texto is not None else ""
	if not t:
		return None
	if "," in t:
		return _parse_valor_br(t)
	try:
		return float(t.replace("'", "").strip())
	except ValueError:
		return None


# ----------------------------------------------------------


# Bank statement helper methods
def _get_transaction_type(name):
	if name.startswith("Pix "):
		return "PIX"
	elif name == "Vendas":
		return "Depósito de vendas"
	else:
		return "Outro"


def _get_transaction_type_html(tipo_coluna: str, nome: str) -> str:
	"""Mapeia a coluna 'Tipo de transação' do extrato HTML para os tipos usados na conciliação."""
	tipo = _limpar_espacos(tipo_coluna).lower()
	if tipo.startswith("pix"):
		return "PIX"
	if "venda" in tipo:
		return "Depósito de vendas"
	if tipo:
		return "Outro"
	# Sem a coluna de tipo, cai na heurística pelo nome (mesma regra do OFX).
	return _get_transaction_type(nome or "")


_MESES_ABREV_PT = {
	"jan": 1,
	"fev": 2,
	"mar": 3,
	"abr": 4,
	"mai": 5,
	"jun": 6,
	"jul": 7,
	"ago": 8,
	"set": 9,
	"out": 10,
	"nov": 11,
	"dez": 12,
}

_RE_DATA_EXTRATO_HTML = re.compile(r"^(\d{1,2})\s+([^\W\d_]{3,})\.?,?\s+(\d{4})$", re.UNICODE)
_RE_HORA_EXTRATO_HTML = re.compile(r"^\d{1,2}:\d{2}$")


def _parse_data_extrato_html(texto: str) -> date | None:
	"""Interpreta o cabeçalho de dia do extrato HTML ('03 Mai, 2026')."""
	m = _RE_DATA_EXTRATO_HTML.match(_limpar_espacos(texto))
	if not m:
		return None
	dia, mes_txt, ano = m.groups()
	mes = _MESES_ABREV_PT.get(_normalize_column(mes_txt)[:3])
	if not mes:
		return None
	try:
		return date(int(ano), mes, int(dia))
	except ValueError:
		return None


class _TabelaHTMLParser(HTMLParser):
	"""Extrai as linhas de todas as tabelas do HTML, na ordem do documento.

	Usa pilhas de linha/célula para lidar com as tabelas aninhadas do relatório
	(a tabela externa é só o cabeçalho/rodapé da página): o texto vai sempre para
	a célula mais interna aberta, então uma linha externa nunca "engole" o
	conteúdo das linhas internas.
	"""

	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.rows: list[list[str]] = []
		self._row_stack: list[list[str]] = []
		self._cell_stack: list[list[str]] = []

	def handle_starttag(self, tag, attrs):
		if tag == "tr":
			self._row_stack.append([])
		elif tag in ("td", "th"):
			self._cell_stack.append([])

	def handle_endtag(self, tag):
		if tag == "tr" and self._row_stack:
			self.rows.append(self._row_stack.pop())
		elif tag in ("td", "th") and self._cell_stack:
			texto = _limpar_espacos("".join(self._cell_stack.pop()))
			if self._row_stack:
				self._row_stack[-1].append(texto)

	def handle_data(self, data):
		if self._cell_stack:
			self._cell_stack[-1].append(data)


def _gerar_fitid_extrato_html(
	data_hora: datetime, tipo: str, nome: str, detalhe: str, valor: float, ocorrencia: int
) -> str:
	"""Gera um identificador estável para a linha do extrato HTML.

	O relatório HTML não traz FITID (o OFX trazia), então o ID é derivado do
	conteúdo da linha. O contador de ocorrência distingue lançamentos idênticos
	no mesmo minuto e mantém a importação idempotente para o mesmo arquivo.
	"""
	base = "|".join(
		[
			data_hora.strftime("%Y-%m-%d %H:%M"),
			_limpar_espacos(tipo),
			_limpar_espacos(nome),
			_limpar_espacos(detalhe),
			f"{valor:.2f}",
			str(ocorrencia),
		]
	)
	return f"infinitepay-extrato-{hashlib.md5(base.encode('utf-8')).hexdigest()}"


def _bank_statement_rows_from_html(file_path: str) -> list[dict]:
	"""Lê o 'Relatório de movimentações' (Conta Web Infinitepay) em HTML.

	Estrutura: uma tabela por dia; o dia vem numa linha própria do `thead`
	('03 Mai, 2026') e cada lançamento é uma linha de 6 células
	(Data, Hora, Tipo de transação, Nome, Detalhe, Valor). A linha
	'Saldo do dia' tem menos células e é ignorada.
	"""
	parser = _TabelaHTMLParser()
	parser.feed(_read_text(file_path))
	parser.close()

	dia_atual: date | None = None
	ocorrencias: dict[str, int] = {}
	transactions: list[dict] = []

	for cells in parser.rows:
		if not cells:
			continue

		# Linha de cabeçalho de dia: célula única com a data.
		if len(cells) == 1:
			d = _parse_data_extrato_html(cells[0])
			if d:
				dia_atual = d
			continue

		if len(cells) != 6 or not _RE_HORA_EXTRATO_HTML.match(cells[1]):
			continue

		# Algumas variações do relatório repetem a data na primeira célula.
		d = _parse_data_extrato_html(cells[0])
		if d:
			dia_atual = d
		if not dia_atual:
			raise ValueError(
				f"Extrato HTML sem cabeçalho de data antes do lançamento das {cells[1]} ({cells[3]})."
			)

		valor = _parse_valor_br(cells[5])
		if valor is None:
			raise ValueError(f"Valor inválido no extrato HTML: {cells[5]!r} (linha {cells!r}).")

		hora, minuto = (int(p) for p in cells[1].split(":")[:2])
		data_hora = datetime(dia_atual.year, dia_atual.month, dia_atual.day, hora, minuto)

		chave = f"{data_hora:%Y-%m-%d %H:%M}|{cells[2]}|{cells[3]}|{cells[4]}|{valor:.2f}"
		ocorrencias[chave] = ocorrencias.get(chave, 0) + 1

		transactions.append(
			{
				"type": "credit" if valor >= 0 else "debit",
				"date": data_hora,
				"value": valor,
				"fitid": _gerar_fitid_extrato_html(
					data_hora, cells[2], cells[3], cells[4], valor, ocorrencias[chave]
				),
				"name": cells[3],
				"memo": cells[4],
				"transaction_type": _get_transaction_type_html(cells[2], cells[3]),
			}
		)

	return transactions


def _bank_statement_rows_from_ofx(file_path: str) -> list[dict]:
	# Helper privado: só recebe caminhos resolvidos no servidor a partir de um File.
	with open(file_path) as f:  # nosemgrep
		ofx = OfxParser.parse(f)

	return [
		{
			"type": t.type,  # TRNTYPE
			"date": t.date,  # DTPOSTED (datetime)
			"value": t.amount,  # TRNAMT
			"fitid": t.id,  # FITID
			"name": t.payee,  # NAME
			"memo": t.memo,  # MEMO
			"transaction_type": _get_transaction_type(t.payee or ""),
		}
		for t in ofx.account.statement.transactions
	]


# Sem @frappe.whitelist(): esta função abre um caminho de arquivo do servidor
# e só é chamada pelos controladores das páginas de /financeiro, que resolvem o
# caminho a partir de um File já validado. Exposta como endpoint, qualquer
# usuário logado poderia ler arquivo arbitrário do site.
def get_infinitepay_bank_statement_df(file: str, filter_dt: str | None = None) -> pd.DataFrame:
	"""Extrato bancário Infinitepay: aceita o OFX antigo e o relatório HTML atual."""
	formato = _detect_format(file)
	if formato == FORMATO_HTML:
		transactions = _bank_statement_rows_from_html(file)
	elif formato == FORMATO_OFX:
		transactions = _bank_statement_rows_from_ofx(file)
	else:
		raise ValueError(
			f"Formato de extrato Infinitepay não reconhecido ({formato}). "
			"Envie o arquivo OFX ou o relatório de movimentações em HTML."
		)

	df = pd.DataFrame(
		transactions, columns=["type", "date", "value", "fitid", "name", "memo", "transaction_type"]
	)

	if filter_dt:
		df = df[df["date"] >= filter_dt]
	return df


# ----------------------------------------------------------

# Sales report helper methods


def _parse_date(date_str):
	date_str = date_str.replace("·", " ").strip()
	dt = dateparser.parse(date_str, languages=["pt"])
	if dt is None:
		raise ValueError(f"Could not parse date: {date_str}")
	return dt


def _generate_infinite_id_money(row):
	if row["meio_meio"] == "Dinheiro":
		concat_str = f"{row['data_hora']}{row['meio_meio']}{row['tipo_dados_adicionais']}{row['identificador']}{row['valor']}"
		md5_hash = hashlib.md5(concat_str.encode("utf-8")).hexdigest()
		return f"infinitepay-dinheiro-{md5_hash}"
	return row["infinite_id"]


# Colunas do relatório de vendas, na ordem em que a Infinitepay exporta.
# Correspondem aos cabeçalhos do CSV depois de `_normalize_column`.
COLUNAS_VENDAS = [
	"data_e_hora",
	"meio_meio",
	"meio_bandeira",
	"meio_parcelas",
	"tipo_origem",
	"tipo_dados_adicionais",
	"identificador",
	"status",
	"valor_r",
	"liquido_r",
	"taxa_aplicada_valor_r",
	"taxa_aplicada_aplicada",
	"plano",
	"nsu",
	"origem_nome",
]

# No XML de vendas os campos monetários vêm com aspas duplicadas (`""26,50""`),
# o que quebra qualquer leitor de CSV: normaliza para aspas simples antes de ler.
_RE_ASPAS_DUPLICADAS = re.compile(r'""([^"]*)""')


def _sales_df_from_xml(file_path: str) -> pd.DataFrame:
	"""Lê o relatório de vendas em XML.

	Cada `<sale>` tem um único filho cujo nome concatena todos os cabeçalhos e
	cujo texto é a linha CSV correspondente.
	"""
	root = ET.fromstring(_read_text(file_path))
	registros = []
	invalidas = []

	for sale in root.findall(".//sale"):
		filhos = list(sale)
		linha = (filhos[0].text if filhos else sale.text) or ""
		linha = linha.strip()
		if not linha:
			continue
		valores = next(csv.reader(io.StringIO(_RE_ASPAS_DUPLICADAS.sub(r'"\1"', linha))), [])
		if len(valores) != len(COLUNAS_VENDAS):
			invalidas.append(linha)
			continue
		registros.append(dict(zip(COLUNAS_VENDAS, valores, strict=True)))

	if invalidas:
		amostra = "; ".join(invalidas[:3])
		raise ValueError(
			f"{len(invalidas)} linha(s) do relatório de vendas XML não têm as "
			f"{len(COLUNAS_VENDAS)} colunas esperadas. Exemplo: {amostra}"
		)

	df = pd.DataFrame(registros, columns=COLUNAS_VENDAS)
	# Campos vazios viram NaN, como no CSV lido por pandas.
	return df.replace("", np.nan)


def _prepare_sales_df(df: pd.DataFrame, filter_dt: str | None = None) -> pd.DataFrame:
	"""Normaliza colunas, datas e valores do relatório de vendas (CSV ou XML)."""
	df.columns = [_normalize_column(col) for col in df.columns]
	df["data_e_hora"] = df["data_e_hora"].apply(_parse_date)
	monetary_cols = ["valor_r", "liquido_r"]
	for col in monetary_cols:
		df[col] = (
			df[col]
			.astype(str)
			.str.replace(".", "", regex=False)  # remove thousands separators if any
			.str.replace(",", ".", regex=False)  # replace decimal comma with point
			.str.replace("'", "", regex=False)  # remove single quotes
			.str.replace("+", "", regex=False)  # remove plus sign if present
			.str.replace("-", "-", regex=False)  # keep minus sign if present
		)
		df[col] = pd.to_numeric(df[col], errors="coerce")
	df["taxa_aplicada_valor_r"] = df["valor_r"] - df["liquido_r"]
	df["taxa_aplicada_aplicada"] = df["taxa_aplicada_valor_r"] / df["valor_r"]
	df = df.rename(
		columns={
			"nsu": "infinite_id",
			"data_e_hora": "data_hora",
			"valor_r": "valor",
			"liquido_r": "valor_liquido",
			"taxa_aplicada_valor_r": "taxa_aplicada",
			"taxa_aplicada_aplicada": "taxa_aplicada_perc",
		}
	)
	df = df[df["status"] == "Aprovada"]
	df["infinite_id"] = df.apply(_generate_infinite_id_money, axis=1)

	if filter_dt:
		df = df[df["data_hora"] >= filter_dt]
	return df


# Sem @frappe.whitelist(): esta função abre um caminho de arquivo do servidor
# e só é chamada pelos controladores das páginas de /financeiro, que resolvem o
# caminho a partir de um File já validado. Exposta como endpoint, qualquer
# usuário logado poderia ler arquivo arbitrário do site.
def get_infinitepay_sales_df(file_path: str, filter_dt: str | None = None):
	"""Relatório de vendas Infinitepay: aceita o CSV antigo e o XML atual."""
	formato = _detect_format(file_path)
	if formato == FORMATO_XML:
		df = _sales_df_from_xml(file_path)
	elif formato == FORMATO_CSV:
		df = pd.read_csv(file_path)
	else:
		raise ValueError(
			f"Formato do relatório de vendas Infinitepay não reconhecido ({formato}). "
			"Envie o arquivo CSV ou XML."
		)
	return _prepare_sales_df(df, filter_dt)


# ----------------------------------------------------------

# Receipts report helper methods


def _parse_datetime_column(series: pd.Series) -> pd.Series:
	"""
	Parses the datetime column from format 'dd/mm/yyyy HHhMM' to timestamp
	"""

	def parse_single_datetime(date_str):
		try:
			# Replace 'h' with ':' and parse
			clean_date = date_str.replace("h", ":")
			return pd.to_datetime(clean_date, format="%d/%m/%Y %H:%M")
		except Exception:
			return pd.NaT

	return series.apply(parse_single_datetime)


def _parse_date_column(series: pd.Series) -> pd.Series:
	"""
	Parses the date column from format 'dd/mm/yyyy' to date
	"""

	def parse_single_date(date_str):
		try:
			return pd.to_datetime(date_str, format="%d/%m/%Y").date()
		except Exception:
			return pd.NaT

	return series.apply(parse_single_date)


# Colunas do relatório de recebimentos depois de `_normalize_column`,
# na ordem em que a Infinitepay exporta.
COLUNAS_RECEBIMENTOS = [
	"infinite_id",
	"origem",
	"data_da_venda",
	"autorizacao",
	"bandeira",
	"tipo",
	"valor_r",
	"total_de_parcelas",
	"no_da_parcela",
	"valor_da_parcela_r",
	"liquido_r",
	"recebido_r",
	"status",
	"data_do_deposito",
	"numero_unico_de_liquidacao_nuliquid",
	"antecipada",
]

# Colunas numéricas do relatório de recebimentos (pandas infere no CSV; no XML
# a conversão é explícita).
_RECEBIMENTOS_COLS_NUMERICAS = (
	"valor_r",
	"total_de_parcelas",
	"no_da_parcela",
	"valor_da_parcela_r",
	"liquido_r",
	"recebido_r",
)

_BANDEIRAS_RECEBIMENTOS = {
	"mastercard": "Mastercard",
	"visa": "Visa",
	"elo": "Elo",
	"hipercard": "Hipercard",
	"amex": "Amex",
	"american express": "American Express",
}

_METODOS_RECEBIMENTOS = {"credit": "Crédito", "debit": "Débito", "pix": "Pix", "money": "Dinheiro"}


def _receipts_df_from_transaction_payments_xml(root: ET.Element) -> pd.DataFrame:
	"""Lê o `transaction_payments_report.xml` (mesmos dados do CSV de recebimentos).

	As tags do XML perdem os caracteres acentuados (`autoriza_o`, `l_quido_r`),
	então o mapeamento é posicional — a ordem dos campos é a mesma do CSV.
	"""
	registros = []
	for transaction in root.findall(".//transaction"):
		valores = [(c.text or "").strip() for c in list(transaction)]
		if len(valores) != len(COLUNAS_RECEBIMENTOS):
			raise ValueError(
				f"Relatório de recebimentos XML com {len(valores)} campos, "
				f"esperado {len(COLUNAS_RECEBIMENTOS)}."
			)
		registros.append(dict(zip(COLUNAS_RECEBIMENTOS, valores, strict=True)))
	return pd.DataFrame(registros, columns=COLUNAS_RECEBIMENTOS)


def _receipts_df_from_proof_of_transfer_xml(root: ET.Element) -> pd.DataFrame:
	"""Lê o `proof_of_transfer_report.xml` (comprovante de transferência).

	Traz os mesmos recebimentos do relatório de pagamentos, agrupados por
	transferência e com nomes de campo em inglês. Não há campo de autorização.
	"""
	registros = []
	for transaction in root.findall(".//transaction"):

		def campo(tag, _t=transaction):
			return (_t.findtext(tag) or "").strip()

		data_venda = campo("transaction_date")  # 'YYYY-MM-DD HH:MM:SS'
		data_deposito = campo("payment_date")  # 'YYYY-MM-DD'
		antecipada = campo("anticipated").lower()
		registros.append(
			{
				"infinite_id": campo("nsu"),
				"origem": campo("capture_method"),
				# Convertidos para o formato do CSV, reaproveitando o mesmo parser.
				"data_da_venda": (
					f"{data_venda[8:10]}/{data_venda[5:7]}/{data_venda[0:4]} {data_venda[11:13]}h{data_venda[14:16]}"
					if len(data_venda) >= 16
					else ""
				),
				"autorizacao": "",
				"bandeira": _BANDEIRAS_RECEBIMENTOS.get(
					campo("card_brand").lower(), campo("card_brand").title()
				),
				"tipo": _METODOS_RECEBIMENTOS.get(
					campo("payment_method").lower(), campo("payment_method").title()
				),
				"valor_r": campo("amount"),
				"total_de_parcelas": campo("installments"),
				"no_da_parcela": campo("installment_number"),
				# O comprovante não separa valor total da venda e valor da parcela;
				# para vendas parceladas os dois campos ficam iguais.
				"valor_da_parcela_r": campo("amount"),
				"liquido_r": campo("net_amount"),
				"recebido_r": campo("receivable_amount"),
				"status": campo("status"),
				"data_do_deposito": (
					f"{data_deposito[8:10]}/{data_deposito[5:7]}/{data_deposito[0:4]}"
					if len(data_deposito) >= 10
					else ""
				),
				"numero_unico_de_liquidacao_nuliquid": campo("cip_liquidation_id"),
				"antecipada": "Sim" if antecipada in ("true", "1", "sim") else "Não",
			}
		)
	return pd.DataFrame(registros, columns=COLUNAS_RECEBIMENTOS)


def _receipts_df_from_xml(file_path: str) -> pd.DataFrame:
	root = ET.fromstring(_read_text(file_path))
	if root.tag == "proof_of_transfer":
		df = _receipts_df_from_proof_of_transfer_xml(root)
	elif root.tag == "transaction_payments":
		df = _receipts_df_from_transaction_payments_xml(root)
	else:
		raise ValueError(
			f"XML de recebimentos Infinitepay não reconhecido (raiz <{root.tag}>). "
			"Esperado <transaction_payments> ou <proof_of_transfer>."
		)

	for col in _RECEBIMENTOS_COLS_NUMERICAS:
		df[col] = pd.to_numeric(df[col].apply(_parse_numero_flex), errors="coerce")
	# Contagens de parcela viram inteiro, como no CSV lido por pandas.
	for col in ("total_de_parcelas", "no_da_parcela"):
		if df[col].notna().all():
			df[col] = df[col].astype("int64")
	return df.replace("", np.nan)


def _prepare_receipts_df(df: pd.DataFrame) -> pd.DataFrame:
	"""Normaliza colunas, datas e nomes do relatório de recebimentos (CSV ou XML)."""
	# Apply normalization to all column names
	df.columns = [_normalize_column(col) for col in df.columns]

	# Parse the data_da_venda column to timestamp
	if "data_da_venda" in df.columns:
		df["data_da_venda"] = _parse_datetime_column(df["data_da_venda"])

	# Parse the data_do_deposito column to date
	if "data_do_deposito" in df.columns:
		df["data_do_deposito"] = _parse_date_column(df["data_do_deposito"])

	return df.rename(
		columns={
			"data_da_venda": "data_venda",
			"valor_r": "valor",
			"total_de_parcelas": "total_parcelas",
			"no_da_parcela": "numero_parcela",
			"valor_da_parcela_r": "valor_parcela",
			"liquido_r": "valor_parcela_liquido",
			"recebido_r": "valor_parcela_recebido",
			"data_do_deposito": "data_deposito",
			"numero_unico_de_liquidacao_nuliquid": "numero_liquidacao",
		}
	)


# Sem @frappe.whitelist(): esta função abre um caminho de arquivo do servidor
# e só é chamada pelos controladores das páginas de /financeiro, que resolvem o
# caminho a partir de um File já validado. Exposta como endpoint, qualquer
# usuário logado poderia ler arquivo arbitrário do site.
def get_infinitepay_receipts_df(file_path: str, filter_dt: str | None = None) -> pd.DataFrame:
	"""Relatório de recebimentos Infinitepay: aceita o CSV antigo e os XML atuais."""
	formato = _detect_format(file_path)
	if formato == FORMATO_XML:
		df = _receipts_df_from_xml(file_path)
	elif formato == FORMATO_CSV:
		# Read CSV file with semicolon delimiter
		df = pd.read_csv(file_path, delimiter=";", encoding="utf-8")
	else:
		raise ValueError(
			f"Formato do relatório de recebimentos Infinitepay não reconhecido ({formato}). "
			"Envie o arquivo CSV ou XML."
		)
	return _prepare_receipts_df(df)


# ----------------------------------------------------------

# Bank Reconcilliation helper methods


# Sem @frappe.whitelist(): trabalha com DataFrames do pandas, que não trafegam por
# HTTP. Chamada só pelo controlador de /financeiro/contas.
def bank_reconcilliation(df_bank_statement, df_receipts, df_sales):
	# Agrega df_receipts por infinite_id
	df_receipts_agg = df_receipts.groupby("infinite_id", as_index=False).agg(
		data_deposito=("data_deposito", "min"), num_liquidacao=("numero_liquidacao", "min")
	)

	# Enriquece df_sales com dados agregados dos receipts
	df_enrich = pd.merge(df_sales, df_receipts_agg, on="infinite_id", how="left")
	df_enrich["type"] = "credit"
	df_enrich = df_enrich[df_enrich["meio_meio"] != "Pix"].copy()
	df_enrich["conciliado"] = 0

	cols = [
		"data_hora",
		"meio_meio",
		"origem_nome",
		"valor_liquido",
		"type",
		"infinite_id",
		"data_deposito",
		"num_liquidacao",
		"tipo_origem",
	]
	df_enrich = df_enrich[cols]

	# Filtro e padronização das colunas de df_bank_statement
	df_bank_statement = df_bank_statement[
		df_bank_statement["type"].eq("debit") | df_bank_statement["transaction_type"].isin(["PIX", "Outro"])
	].copy()

	df_bank_statement = df_bank_statement.rename(
		columns={
			"date": "data_hora",
			"name": "descricao",
			"value": "valor_liquido",
			"transaction_type": "meio_meio",
			"fitid": "infinite_id",
		}
	)

	df_bank_statement["data_deposito"] = df_bank_statement["data_hora"]
	df_bank_statement["num_liquidacao"] = None
	df_bank_statement["tipo_origem"] = "Débito na conta"

	# Remove prefixo "Pix " e preenche origem_nome para débito
	df_bank_statement["origem_nome"] = df_bank_statement["descricao"].str.replace(r"^Pix ", "", regex=True)
	mask_debit = df_bank_statement["type"] == "debit"
	df_bank_statement.loc[mask_debit, "origem_nome"] = (
		"GRUPO ESCOTEIRO PROFESSORA INAH DE MELO N 147. - INFINITEPAY"
	)

	df_bank_statement = df_bank_statement[cols]

	# Junta e ajusta tipos
	df_final = pd.concat([df_bank_statement, df_enrich], ignore_index=True)
	df_final["valor_liquido"] = df_final["valor_liquido"].astype(float)

	return df_final
