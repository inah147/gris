# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import json

import frappe


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook_infinitepay():
	"""Endpoint para receber notificações de pagamento da InfinitePay.

	allow_guest=True: endpoint chamado externamente pela InfinitePay,
	sem autenticação Frappe. A validação é feita conferindo se o order_nsu
	existe como documento no sistema.

	Responde 200 OK em sucesso ou 400 Bad Request em erro
	(InfinitePay reenvia automaticamente em caso de 400).
	"""
	try:
		data = json.loads(frappe.request.get_data(as_text=True))
	except (json.JSONDecodeError, AttributeError):
		frappe.local.response.http_status_code = 400
		return {"ok": False, "error": {"code": "INVALID_PAYLOAD", "message": "Payload inválido."}}

	order_nsu = data.get("order_nsu")
	if not order_nsu:
		frappe.local.response.http_status_code = 400
		return {"ok": False, "error": {"code": "MISSING_ORDER_NSU", "message": "order_nsu ausente."}}

	if not frappe.db.exists("Cobranca Infinitepay", order_nsu):
		frappe.local.response.http_status_code = 400
		return {"ok": False, "error": {"code": "ORDER_NOT_FOUND", "message": "Cobrança não encontrada."}}

	campos_webhook = {
		"invoice_slug": data.get("invoice_slug", ""),
		"amount": data.get("amount", 0),
		"paid_amount": data.get("paid_amount", 0),
		"installments": data.get("installments", 0),
		"capture_method": data.get("capture_method", ""),
		"transaction_nsu": data.get("transaction_nsu", ""),
		"receipt_url": data.get("receipt_url", ""),
		"status": "Pago",
	}

	frappe.db.set_value(
		"Cobranca Infinitepay",
		order_nsu,
		campos_webhook,
		update_modified=True,
	)
	frappe.db.commit()

	frappe.logger().info(f"Webhook InfinitePay processado para order_nsu={order_nsu}")

	return {"ok": True}
