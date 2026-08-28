from typing import Optional

import frappe
import numpy as np
import pandas as pd


# Sem @frappe.whitelist(): esta função abre um caminho de arquivo do servidor
# e só é chamada pelos controladores das páginas de /financeiro, que resolvem o
# caminho a partir de um File já validado. Exposta como endpoint, qualquer
# usuário logado poderia ler arquivo arbitrário do site.
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
