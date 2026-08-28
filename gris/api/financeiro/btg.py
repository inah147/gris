import frappe
import pandas as pd
from ofxparse import OfxParser


# Sem @frappe.whitelist(): esta função abre um caminho de arquivo do servidor
# e só é chamada pelos controladores das páginas de /financeiro, que resolvem o
# caminho a partir de um File já validado. Exposta como endpoint, qualquer
# usuário logado poderia ler arquivo arbitrário do site.
def get_btg_bank_statement_df(file: str, filter_dt: str | None = None) -> pd.DataFrame:
	# Função não whitelisted: `file` é resolvido no servidor a partir de um File.
	with open(file, encoding="utf-8") as f:  # nosemgrep
		ofx = OfxParser.parse(f)

	transactions = []
	for t in ofx.account.statement.transactions:
		transactions.append(
			{
				"type": t.type,
				"timestamp": t.date,  # datetime
				"value": t.amount,
				"id": t.id,
				"checknum": getattr(t, "checknum", None),
				"description": t.memo,
			}
		)

	df = pd.DataFrame(transactions)

	if filter_dt:
		df = df[df["timestamp"] >= pd.to_datetime(filter_dt)]

	return df
