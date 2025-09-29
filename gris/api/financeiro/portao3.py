from typing import Optional

import frappe
import numpy as np
import pandas as pd


@frappe.whitelist()
def get_portao3_bank_statement_df(file_path, filter_date: str | None = None):
	df = pd.read_csv(file_path)

	df["Valor"] = df["Valor"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
	df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")

	df["Tipo"] = df["Tipo"].str.capitalize()
	df["Date"] = pd.to_datetime(df["Date"], dayfirst=True)

	df["date_only"] = df["Date"].dt.date

	df["Cartão final"] = df["Cartão final"].astype(str)

	df = df.replace({np.nan: None})

	return df
