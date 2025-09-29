import frappe
import pandas as pd
from ofxparse import OfxParser


@frappe.whitelist()
def get_btg_bank_statement_df(file: str, filter_dt: str | None = None) -> pd.DataFrame:
	with open(file, encoding="utf-8") as f:
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
