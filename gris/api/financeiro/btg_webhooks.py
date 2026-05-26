# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Endpoint público para recebimento de webhooks do BTG Empresas.

Registre a URL no BTG Developer Console (Webhooks):
  https://<seu-site>/api/method/gris.api.financeiro.btg_webhooks.webhook_btg

Segurança:
  O BTG envia um header de assinatura HMAC-SHA256 (X-BTG-Signature) calculado
  com o `webhook_secret` configurado em Configuracao BTG Empresas.
  Se `webhook_secret` estiver em branco, a validação é ignorada (não recomendado
  em produção).

Eventos suportados:
  - account.transaction.created  → insere Transacao BTG Empresas
  - payment.status.updated        → atualiza status de Iniciacao Pagamento BTG
  - charge.paid                   → atualiza status de Cobranca BTG
"""

import hashlib
import hmac
import json

import frappe

_SIGNATURE_HEADER = "X-BTG-Signature"


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook_btg():
	"""Recebe e processa eventos de webhook do BTG Empresas."""
	try:
		raw_body = frappe.request.get_data()
		payload = json.loads(raw_body)
	except (json.JSONDecodeError, AttributeError):
		frappe.local.response.http_status_code = 400
		return {"ok": False, "error": "INVALID_PAYLOAD"}

	# Validação de assinatura HMAC
	if not _validar_assinatura(raw_body):
		frappe.logger().warning("BTG webhook: assinatura inválida.")
		frappe.local.response.http_status_code = 401
		return {"ok": False, "error": "INVALID_SIGNATURE"}

	event_type = payload.get("event") or payload.get("eventType") or ""
	data = payload.get("data") or {}

	frappe.logger().info(f"BTG webhook recebido: event={event_type}")

	try:
		if "transaction" in event_type.lower():
			_processar_transacao(data)
		elif "payment" in event_type.lower():
			_processar_pagamento(data)
		elif "charge" in event_type.lower():
			_processar_cobranca(data)
		else:
			frappe.logger().info(f"BTG webhook: event_type '{event_type}' não tratado — ignorado.")
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"BTG Webhook: {event_type}")
		# Retorna 200 para evitar retentativas infinitas do BTG em erros internos
		return {"ok": False, "error": "PROCESSING_ERROR"}

	return {"ok": True}


# ---------------------------------------------------------------------------
# Handlers por tipo de evento
# ---------------------------------------------------------------------------

def _processar_transacao(data: dict) -> None:
	"""Insere uma transação recebida via webhook em Transacao BTG Empresas."""
	from gris.api.financeiro.btg import (
		_extrair_data,
		_extrair_descricao,
		_extrair_id,
		_extrair_tipo,
		_extrair_valor,
	)

	tx_id = _extrair_id(data)
	if not tx_id:
		frappe.logger().warning("BTG webhook transacao: id ausente, ignorado.")
		return

	# Idempotência
	if frappe.db.exists("Transacao BTG Empresas", {"id": tx_id}):
		frappe.logger().info(f"BTG webhook: transacao {tx_id} já existe, ignorada.")
		return

	doc = frappe.get_doc(
		{
			"doctype": "Transacao BTG Empresas",
			"id": tx_id,
			"data_transacao": _extrair_data(data),
			"descricao": _extrair_descricao(data),
			"valor": _extrair_valor(data),
			"tipo": _extrair_tipo(data),
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	frappe.logger().info(f"BTG webhook: transacao {tx_id} inserida.")


def _processar_pagamento(data: dict) -> None:
	"""Atualiza o status de uma Iniciacao Pagamento BTG a partir de evento webhook."""
	external_id = data.get("id") or data.get("paymentId") or ""
	status_btg = data.get("status") or ""

	if not external_id:
		return

	name = frappe.db.get_value("Iniciacao Pagamento BTG", {"external_id": external_id}, "name")
	if not name:
		frappe.logger().info(f"BTG webhook pagamento: external_id {external_id} não encontrado.")
		return

	status_map = {
		"APPROVED": "Aprovado",
		"CANCELLED": "Cancelado",
		"REJECTED": "Rejeitado",
		"PROCESSING": "Aguardando Aprovação",
	}
	novo_status = status_map.get(status_btg.upper(), "")
	if novo_status:
		frappe.db.set_value("Iniciacao Pagamento BTG", name, "status", novo_status)
		frappe.db.commit()
		frappe.logger().info(f"BTG webhook: pagamento {name} → {novo_status}")


def _processar_cobranca(data: dict) -> None:
	"""Atualiza o status de uma Cobranca BTG quando paga via webhook."""
	charge_id = data.get("id") or data.get("chargeId") or ""
	status_btg = data.get("status") or ""

	if not charge_id:
		return

	name = frappe.db.get_value("Cobranca BTG", {"charge_id": charge_id}, "name")
	if not name:
		frappe.logger().info(f"BTG webhook cobrança: charge_id {charge_id} não encontrado.")
		return

	status_map = {
		"PAID": "Pago",
		"EXPIRED": "Expirado",
		"CANCELLED": "Cancelado",
	}
	novo_status = status_map.get(status_btg.upper(), "")
	if novo_status:
		frappe.db.set_value("Cobranca BTG", name, "status", novo_status)
		# Salva transaction_id se disponível
		tx_id = data.get("transactionId") or data.get("transaction_id") or ""
		if tx_id:
			frappe.db.set_value("Cobranca BTG", name, "transaction_id", tx_id)
		frappe.db.commit()
		frappe.logger().info(f"BTG webhook: cobrança {name} → {novo_status}")


# ---------------------------------------------------------------------------
# Validação de assinatura HMAC
# ---------------------------------------------------------------------------

def _validar_assinatura(raw_body: bytes) -> bool:
	"""Valida a assinatura HMAC-SHA256 do webhook.

	Se o webhook_secret não estiver configurado, aceita sem validação
	(útil para testes; não recomendado em produção).
	"""
	try:
		secret = frappe.utils.password.get_decrypted_password(
			"Configuracao BTG Empresas",
			"Configuracao BTG Empresas",
			"webhook_secret",
		) or ""
	except Exception:
		secret = ""

	if not secret:
		return True  # Sem segredo configurado — aceita (apenas para sandbox/dev)

	signature_header = frappe.request.headers.get(_SIGNATURE_HEADER, "")
	if not signature_header:
		return False

	# Remove prefixo "sha256=" se presente
	received_sig = signature_header.removeprefix("sha256=")

	expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
	return hmac.compare_digest(expected, received_sig)
