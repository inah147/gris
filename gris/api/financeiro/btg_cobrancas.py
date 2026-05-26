# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Integração BTG Empresas — Cobranças (Charge API).

POST /v1/charge — cria cobrança e retorna link de pagamento e QR Code
GET  /v1/charge/{id} — consulta status da cobrança
"""

import frappe
import requests


@frappe.whitelist()
def criar_cobranca(name: str) -> dict:
	"""Envia uma cobrança para a API BTG e salva o charge_id, link e QR Code.

	Chamado automaticamente em after_insert; pode ser re-chamado manualmente.
	"""
	from gris.api.financeiro.btg_auth import get_api_base, get_api_headers

	doc = frappe.get_doc("Cobranca BTG", name)

	payload = {
		"amount": round(doc.valor * 100),  # centavos
		"description": doc.descricao,
	}

	if doc.expiracao:
		payload["expiration"] = str(doc.expiracao)  # YYYY-MM-DD

	if doc.customer_name or doc.customer_email or doc.customer_phone:
		customer = {}
		if doc.customer_name:
			customer["name"] = doc.customer_name
		if doc.customer_email:
			customer["email"] = doc.customer_email
		if doc.customer_phone:
			customer["phone"] = doc.customer_phone
		payload["customer"] = customer

	response = requests.post(
		f"{get_api_base()}/v1/charge",
		headers=get_api_headers(),
		json=payload,
		timeout=30,
	)
	response_data = _parse_response(response)

	if not response.ok:
		error_msg = response_data.get("message") or response_data.get("error") or response.text
		frappe.throw(f"Erro ao criar cobrança no BTG: {error_msg}")

	charge_id = (
		response_data.get("id")
		or response_data.get("chargeId")
		or response_data.get("data", {}).get("id")
		or ""
	)
	link_pagamento = (
		response_data.get("paymentUrl")
		or response_data.get("link")
		or response_data.get("data", {}).get("paymentUrl")
		or ""
	)
	qr_code_emv = (
		response_data.get("emv")
		or response_data.get("qrCode")
		or response_data.get("pixCopyPaste")
		or response_data.get("data", {}).get("emv")
		or ""
	)

	frappe.db.set_value("Cobranca BTG", name, {
		"charge_id": charge_id,
		"link_pagamento": link_pagamento,
		"qr_code_emv": qr_code_emv,
	})
	frappe.db.commit()

	frappe.logger().info(f"BTG cobrança criada: name={name}, charge_id={charge_id}")
	return {"charge_id": charge_id, "link_pagamento": link_pagamento, "response": response_data}


@frappe.whitelist()
def consultar_cobranca(name: str) -> dict:
	"""Consulta o status atual de uma cobrança no BTG e atualiza o documento.

	GET /v1/charge/{id}
	"""
	from gris.api.financeiro.btg_auth import get_api_base, get_api_headers

	doc = frappe.get_doc("Cobranca BTG", name)

	if not doc.charge_id:
		frappe.throw("Cobrança sem charge_id BTG; crie a cobrança primeiro.")

	response = requests.get(
		f"{get_api_base()}/v1/charge/{doc.charge_id}",
		headers=get_api_headers(),
		timeout=30,
	)
	response_data = _parse_response(response)

	if not response.ok:
		error_msg = response_data.get("message") or response_data.get("error") or response.text
		frappe.throw(f"Erro ao consultar cobrança no BTG: {error_msg}")

	status_btg = (
		response_data.get("status")
		or response_data.get("data", {}).get("status")
		or ""
	).upper()
	status_map = {
		"PAID": "Pago",
		"EXPIRED": "Expirado",
		"CANCELLED": "Cancelado",
		"PENDING": "Pendente",
	}
	novo_status = status_map.get(status_btg, doc.status)

	updates = {"status": novo_status}
	transaction_id = (
		response_data.get("transactionId")
		or response_data.get("transaction_id")
		or response_data.get("data", {}).get("transactionId")
		or ""
	)
	if transaction_id:
		updates["transaction_id"] = transaction_id

	frappe.db.set_value("Cobranca BTG", name, updates)
	frappe.db.commit()

	frappe.logger().info(f"BTG cobrança consultada: name={name}, status={novo_status}")
	return {"status": novo_status, "response": response_data}


def _parse_response(response: requests.Response) -> dict:
	try:
		return response.json()
	except Exception:
		return {}
