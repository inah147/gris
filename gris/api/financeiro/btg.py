import hashlib

import frappe
import pandas as pd
import requests
from ofxparse import OfxParser

# ---------------------------------------------------------------------------
# OFX file import (legacy — mantido como fallback)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# API BTG Empresas — Conta PJ: Saldo e Extrato
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_account_info() -> dict:
	"""Busca informações da conta PJ BTG e salva o accountId no config.

	GET /v1/account
	Retorna lista de contas; salva o accountId da primeira conta encontrada.
	"""
	from gris.api.financeiro.btg_auth import get_api_base, get_api_headers

	response = requests.get(
		f"{get_api_base()}/v1/account",
		headers=get_api_headers(),
		timeout=30,
	)
	response.raise_for_status()
	data = response.json()

	# A resposta é um array de contas; usa a primeira
	accounts = data if isinstance(data, list) else data.get("accounts") or data.get("data") or []
	if not accounts:
		frappe.throw("Nenhuma conta PJ retornada pela API BTG. Verifique o token e os escopos.")

	account = accounts[0]
	account_id = account.get("accountId") or account.get("id") or account.get("account_id") or ""

	if account_id:
		frappe.db.set_single_value("Configuracao BTG Empresas", "account_id", account_id)
		frappe.db.commit()

	frappe.logger().info(f"BTG: account_id obtido: {account_id}")
	return {"account_id": account_id, "account": account}


@frappe.whitelist()
def get_saldo() -> dict:
	"""Consulta o saldo atual da conta BTG PJ.

	GET /v1/account/{accountId}/balance
	"""
	from gris.api.financeiro.btg_auth import get_api_base, get_api_headers

	account_id = frappe.db.get_single_value("Configuracao BTG Empresas", "account_id")
	if not account_id:
		frappe.throw("Account ID não configurado. Execute 'Buscar Account ID' primeiro.")

	response = requests.get(
		f"{get_api_base()}/v1/account/{account_id}/balance",
		headers=get_api_headers(),
		timeout=30,
	)
	response.raise_for_status()
	return response.json()


@frappe.whitelist()
def get_extrato_api(data_inicio: str, data_fim: str) -> list:
	"""Consulta o extrato bancário via API BTG para o período informado.

	GET /v1/account/{accountId}/statement?from={data_inicio}&to={data_fim}
	Datas no formato YYYY-MM-DD.
	"""
	from gris.api.financeiro.btg_auth import get_api_base, get_api_headers

	account_id = frappe.db.get_single_value("Configuracao BTG Empresas", "account_id")
	if not account_id:
		frappe.throw("Account ID não configurado. Execute 'Buscar Account ID' primeiro.")

	response = requests.get(
		f"{get_api_base()}/v1/account/{account_id}/statement",
		headers=get_api_headers(),
		params={"from": data_inicio, "to": data_fim},
		timeout=30,
	)
	response.raise_for_status()
	data = response.json()

	# Normaliza: a API pode retornar lista diretamente ou dentro de uma chave
	if isinstance(data, list):
		return data
	return data.get("transactions") or data.get("data") or data.get("statement") or []


@frappe.whitelist()
def sync_extrato_btg(data_inicio: str, data_fim: str) -> dict:
	"""Puxa o extrato via API BTG e insere as transações em Transacao BTG Empresas.

	Idempotente: transações já existentes (mesmo id) são ignoradas.
	Retorna estatísticas { total, inserted, skipped_exist, failed }.
	"""
	transactions = get_extrato_api(data_inicio, data_fim)

	stats = {"total": len(transactions), "inserted": 0, "skipped_exist": 0, "failed": 0}
	errors = []

	for tx in transactions:
		try:
			tx_id = _extrair_id(tx)
			if not tx_id:
				stats["failed"] += 1
				errors.append(f"Transação sem id: {tx}")
				continue

			if frappe.db.exists("Transacao BTG Empresas", {"id": tx_id}):
				stats["skipped_exist"] += 1
				continue

			doc = frappe.get_doc(
				{
					"doctype": "Transacao BTG Empresas",
					"id": tx_id,
					"data_transacao": _extrair_data(tx),
					"descricao": _extrair_descricao(tx),
					"valor": _extrair_valor(tx),
					"tipo": _extrair_tipo(tx),
				}
			)
			doc.insert(ignore_permissions=False)
			stats["inserted"] += 1
		except Exception as exc:
			stats["failed"] += 1
			msg = str(exc)
			errors.append(msg)
			frappe.log_error(msg, "BTG Sync Extrato")

	frappe.db.commit()
	frappe.logger().info(f"BTG sync_extrato: {stats}")
	return {"stats": stats, "errors": errors}


# ---------------------------------------------------------------------------
# Helpers de normalização de campos da API BTG
# ---------------------------------------------------------------------------

def _extrair_id(tx: dict) -> str:
	raw_id = tx.get("id") or tx.get("transactionId") or tx.get("fitid") or ""
	if not raw_id:
		# Gera id determinístico a partir do conteúdo para idempotência
		conteudo = f"{tx.get('date','')}{tx.get('amount','')}{tx.get('description','')}"
		raw_id = "btg-" + hashlib.md5(conteudo.encode()).hexdigest()
	return str(raw_id)


def _extrair_data(tx: dict) -> str:
	return (
		tx.get("date")
		or tx.get("transactionDate")
		or tx.get("dateTime", "")[:10]
		or ""
	)


def _extrair_descricao(tx: dict) -> str:
	return tx.get("description") or tx.get("memo") or tx.get("name") or ""


def _extrair_valor(tx: dict) -> float:
	# A API BTG retorna valor em reais (float); créditos positivos, débitos negativos
	valor = tx.get("amount") or tx.get("value") or 0
	try:
		return float(valor)
	except (TypeError, ValueError):
		return 0.0


def _extrair_tipo(tx: dict) -> str:
	return tx.get("type") or tx.get("transactionType") or ""
