# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Integração BTG Empresas — Iniciação de Pagamentos.

Documentação: POST /v1/payment
Todos os pagamentos ficam em status "Aguardando Aprovação" até que um
aprovador execute a liberação no app/internet banking do BTG.

Tipos suportados:
  PIX_KEY, PIX_QR_CODE, PIX_MANUAL, BANKSLIP, TED, UTILITIES, DARF, PIX_REVERSAL
"""

import json

import frappe
import requests


@frappe.whitelist()
def iniciar_pagamento(name: str) -> dict:
	"""Envia um pedido de pagamento para a API BTG.

	O documento Iniciacao Pagamento BTG deve estar submetido (docstatus=1).
	Salva o external_id retornado e atualiza o status para 'Aguardando Aprovação'.
	"""
	from gris.api.financeiro.btg_auth import get_api_base, get_api_headers

	doc = frappe.get_doc("Iniciacao Pagamento BTG", name)

	# Monta o payload combinando campos do doc com o details_json
	try:
		details = json.loads(doc.details_json or "{}")
	except json.JSONDecodeError as exc:
		frappe.throw(f"Details JSON inválido: {exc}")

	payload = {
		"type": doc.tipo,
		"amount": round(doc.valor * 100),  # centavos
		"description": doc.descricao or "",
		**details,
	}

	headers = get_api_headers()
	headers["Idempotency-Key"] = doc.idempotency_key

	response = requests.post(
		f"{get_api_base()}/v1/payment",
		headers=headers,
		json=payload,
		timeout=30,
	)

	response_data = _parse_response(response)

	if not response.ok:
		error_msg = response_data.get("message") or response_data.get("error") or response.text
		frappe.db.set_value("Iniciacao Pagamento BTG", name, {
			"status": "Rejeitado",
			"error_message": error_msg[:500],
		})
		frappe.db.commit()
		frappe.throw(f"BTG recusou o pagamento: {error_msg}")

	external_id = (
		response_data.get("id")
		or response_data.get("paymentId")
		or response_data.get("data", {}).get("id")
		or ""
	)
	frappe.db.set_value("Iniciacao Pagamento BTG", name, {
		"status": "Aguardando Aprovação",
		"external_id": external_id,
		"error_message": "",
	})
	frappe.db.commit()

	frappe.logger().info(f"BTG pagamento criado: name={name}, external_id={external_id}")
	return {"external_id": external_id, "response": response_data}


@frappe.whitelist()
def cancelar_pagamento(name: str) -> dict:
	"""Solicita o cancelamento de um pagamento pendente no BTG.

	DELETE /v1/payment/{id}
	Só funciona enquanto o pagamento ainda não foi aprovado no BTG.
	"""
	from gris.api.financeiro.btg_auth import get_api_base, get_api_headers

	doc = frappe.get_doc("Iniciacao Pagamento BTG", name)

	if not doc.external_id:
		frappe.throw("Pagamento sem ID externo BTG; não é possível cancelar.")

	response = requests.delete(
		f"{get_api_base()}/v1/payment/{doc.external_id}",
		headers=get_api_headers(),
		timeout=30,
	)

	response_data = _parse_response(response)

	if not response.ok:
		error_msg = response_data.get("message") or response_data.get("error") or response.text
		frappe.throw(f"Erro ao cancelar pagamento no BTG: {error_msg}")

	frappe.db.set_value("Iniciacao Pagamento BTG", name, "status", "Cancelado")
	frappe.db.commit()

	frappe.logger().info(f"BTG pagamento cancelado: name={name}, external_id={doc.external_id}")
	return {"ok": True, "response": response_data}


def _parse_response(response: requests.Response) -> dict:
	try:
		return response.json()
	except Exception:
		return {}
