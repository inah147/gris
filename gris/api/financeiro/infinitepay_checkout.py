# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import json

import frappe
import requests

INFINITEPAY_PAYMENT_CHECK_URL = "https://api.checkout.infinitepay.io/payment_check"


def _verificar_pagamento(
	handle: str,
	order_nsu: str,
	transaction_nsu: str | None = None,
	slug: str | None = None,
) -> dict:
	"""Confirma server-to-server se o pagamento é legítimo na InfinitePay.

	A InfinitePay aceita `handle`, `order_nsu`, `transaction_nsu` e `slug`.
	Quanto mais parâmetros, maior a chance de a busca casar.

	Retorna o dict da resposta em caso de sucesso.
	Levanta requests.exceptions.RequestException em caso de falha de rede ou HTTP.
	Levanta ValueError se a resposta indicar success=False.
	"""
	payload: dict = {"handle": handle, "order_nsu": order_nsu}
	if transaction_nsu:
		payload["transaction_nsu"] = transaction_nsu
	if slug:
		payload["slug"] = slug

	response = requests.post(
		INFINITEPAY_PAYMENT_CHECK_URL,
		json=payload,
		headers={"Content-Type": "application/json"},
		timeout=15,
	)
	response.raise_for_status()
	data = response.json()
	if not data.get("success"):
		# Inclui o corpo da resposta na exceção para diagnosticar o motivo
		# (mensagem de erro da InfinitePay, código, etc.).
		frappe.logger().warning(
			f"payment_check success=False para order_nsu={order_nsu} "
			f"transaction_nsu={transaction_nsu} payload={payload} resposta={data}"
		)
		raise ValueError(
			f"payment_check retornou success=False para order_nsu={order_nsu}. "
			f"Resposta da InfinitePay: {data}"
		)
	return data


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook_infinitepay():
	"""Endpoint para receber notificações de pagamento da InfinitePay.

	allow_guest=True: endpoint chamado externamente pela InfinitePay,
	sem autenticação Frappe.

	Fluxo de segurança:
	1. Valida que o order_nsu existe no sistema.
	2. Idempotência: se transaction_nsu já estiver preenchido, o pagamento
	   já foi processado — retorna 200 sem reprocessar.
	3. Confirma o pagamento server-to-server via /payment_check (InfinitePay).
	4. Valida que paid=True e que paid_amount >= valor esperado dos itens.
	5. Só então persiste o pagamento.

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

	doc = frappe.get_doc("Cobranca Infinitepay", order_nsu)

	# Idempotência: transaction_nsu preenchido significa que este pagamento
	# já foi confirmado e persistido anteriormente.
	if doc.transaction_nsu:
		frappe.logger().info(f"Webhook InfinitePay ignorado (já processado) para order_nsu={order_nsu}")
		return {"ok": True}

	handle = frappe.db.get_single_value("Configuracao infinitepay", "handle")
	if not handle:
		frappe.logger().error(f"Handle não configurado. Webhook para order_nsu={order_nsu} não processado.")
		frappe.local.response.http_status_code = 400
		return {"ok": False, "error": {"code": "MISSING_HANDLE", "message": "Configuração ausente."}}

	# Confirmação server-to-server: usa o máximo de identificadores que vieram
	# no payload do webhook (transaction_nsu + invoice_slug) para a InfinitePay
	# confirmar essa transação específica.
	transaction_nsu_webhook = data.get("transaction_nsu") or None
	invoice_slug_webhook = data.get("invoice_slug") or doc.invoice_slug or None
	try:
		verificacao = _verificar_pagamento(handle, order_nsu, transaction_nsu_webhook, invoice_slug_webhook)
	except (requests.exceptions.RequestException, ValueError) as e:
		frappe.logger().error(f"Falha na verificação InfinitePay para order_nsu={order_nsu}: {e}")
		frappe.local.response.http_status_code = 400
		return {
			"ok": False,
			"error": {"code": "VERIFICATION_FAILED", "message": "Não foi possível confirmar o pagamento."},
		}

	# Validação de pagamento efetivo
	if not verificacao.get("paid"):
		frappe.logger().warning(f"Webhook rejeitado: paid=False para order_nsu={order_nsu}")
		frappe.local.response.http_status_code = 400
		return {"ok": False, "error": {"code": "NOT_PAID", "message": "Pagamento não confirmado."}}

	# Validação cruzada de valor: paid_amount deve cobrir o total dos itens.
	# paid_amount pode ser maior que o esperado (juros de parcelamento são aceitos).
	valor_esperado_centavos = sum(item.quantidade * round(item.preco * 100) for item in doc.itens)
	paid_amount = verificacao.get("paid_amount", 0)
	if paid_amount < valor_esperado_centavos:
		frappe.logger().warning(
			f"Webhook rejeitado: paid_amount={paid_amount} < esperado={valor_esperado_centavos} "
			f"para order_nsu={order_nsu}"
		)
		frappe.local.response.http_status_code = 400
		return {"ok": False, "error": {"code": "INSUFFICIENT_AMOUNT", "message": "Valor pago insuficiente."}}

	campos_webhook = {
		"invoice_slug": data.get("invoice_slug", ""),
		"amount": verificacao.get("amount", 0),
		"paid_amount": paid_amount,
		"installments": verificacao.get("installments", 0),
		"capture_method": verificacao.get("capture_method", ""),
		"transaction_nsu": data.get("transaction_nsu", ""),
		"receipt_url": data.get("receipt_url", ""),
		"status": "Pago",
	}

	# Usamos save() em vez de db.set_value para que o on_update da Cobranca
	# dispare e os handlers registrados em doc_events (módulo Festas e futuros
	# consumidores) reajam à transição de status.
	doc.update(campos_webhook)
	doc.save(ignore_permissions=True)
	# Commit explícito: a InfinitePay não reenvia o webhook depois de receber 200.
	# O pagamento precisa estar persistido antes da resposta, mesmo que uma etapa
	# posterior deste handler falhe.
	frappe.db.commit()  # nosemgrep

	frappe.logger().info(f"Webhook InfinitePay processado para order_nsu={order_nsu}")

	return {"ok": True}
