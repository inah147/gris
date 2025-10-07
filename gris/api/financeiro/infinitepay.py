import ast
import hashlib
import re
import unicodedata
from typing import Optional

import dateparser
import frappe
import numpy as np
import pandas as pd
from ofxparse import OfxParser


# Bank statement helper methods
def _get_transaction_type(name):
	if name.startswith("Pix "):
		return "PIX"
	elif name == "Vendas":
		return "Depósito de vendas"
	else:
		return "Outro"


@frappe.whitelist()
def get_infinitepay_bank_statement_df(file: str, filter_dt: str | None = None) -> pd.DataFrame:
	with open(file) as f:
		ofx = OfxParser.parse(f)

	transactions = [
		{
			"type": t.type,  # TRNTYPE
			"date": t.date,  # DTPOSTED (datetime)
			"value": t.amount,  # TRNAMT
			"fitid": t.id,  # FITID
			"name": t.payee,  # NAME
			"memo": t.memo,  # MEMO
		}
		for t in ofx.account.statement.transactions
	]

	df = pd.DataFrame(transactions)

	df["transaction_type"] = df["name"].apply(_get_transaction_type)

	if filter_dt:
		df = df[df["date"] >= filter_dt]
	return df


# ----------------------------------------------------------

# Sales report helper methods


def _normalize_column(col):
	nfkd = unicodedata.normalize("NFKD", col)
	no_accents = "".join([c for c in nfkd if not unicodedata.combining(c)])
	no_specials = re.sub(r"\W+", "_", no_accents)
	return no_specials.lower().strip("_")


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


@frappe.whitelist()
def get_infinitepay_sales_df(file_path: str, filter_dt: str | None = None):
	df = pd.read_csv(file_path)
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
		df = df[df["date"] >= filter_dt]
	return df


# ----------------------------------------------------------

# Receipts report helper methods


def _normalize_column(col):
	nfkd = unicodedata.normalize("NFKD", col)
	no_accents = "".join([c for c in nfkd if not unicodedata.combining(c)])
	no_specials = re.sub(r"\W+", "_", no_accents)
	return no_specials.lower().strip("_")


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


@frappe.whitelist()
def get_infinitepay_receipts_df(file_path: str, filter_dt: str | None = None) -> pd.DataFrame:
	# Read CSV file with semicolon delimiter
	df = pd.read_csv(file_path, delimiter=";", encoding="utf-8")

	# Apply normalization to all column names
	df.columns = [_normalize_column(col) for col in df.columns]

	# Parse the data_da_venda column to timestamp
	if "data_da_venda" in df.columns:
		df["data_da_venda"] = _parse_datetime_column(df["data_da_venda"])

	# Parse the data_do_deposito column to date
	if "data_do_deposito" in df.columns:
		df["data_do_deposito"] = _parse_date_column(df["data_do_deposito"])

	df = df.rename(
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

	return df


# ----------------------------------------------------------

# Bank Reconcilliation helper methods


@frappe.whitelist()
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
