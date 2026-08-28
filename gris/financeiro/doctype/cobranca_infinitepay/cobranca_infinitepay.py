# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe import _
from frappe.model.document import Document

INFINITEPAY_CHECKOUT_URL = "https://api.infinitepay.io/invoices/public/checkout/links"


class CobrancaInfinitepay(Document):
	def validate(self):
		self._validar_itens()

	def after_insert(self):
		self._criar_link_pagamento()

	def _validar_itens(self):
		if not self.itens:
			frappe.throw(_("É necessário adicionar pelo menos 1 item na cobrança."))

		for item in self.itens:
			if not item.descricao:
				frappe.throw(_("Todos os itens devem ter uma descrição."))
			if not item.quantidade or item.quantidade <= 0:
				frappe.throw(f"Item '{item.descricao}': quantidade deve ser maior que zero.")
			if not item.preco or item.preco <= 0:
				frappe.throw(f"Item '{item.descricao}': preço deve ser maior que zero.")

	def _criar_link_pagamento(self):
		handle = frappe.db.get_single_value("Configuracao infinitepay", "handle")
		if not handle:
			frappe.db.set_value("Cobranca Infinitepay", self.name, "status", "Erro")
			frappe.throw(_("Handle não configurado em Configuracao infinitepay."))

		payload = self._montar_payload(handle)

		try:
			response = requests.post(
				INFINITEPAY_CHECKOUT_URL,
				json=payload,
				headers={"Content-Type": "application/json"},
				timeout=30,
			)
			response.raise_for_status()
			data = response.json()

			link = data.get("checkout_url") or data.get("link") or data.get("url") or ""
			if not link and isinstance(data, dict):
				for value in data.values():
					if isinstance(value, str) and value.startswith("http"):
						link = value
						break

			frappe.db.set_value("Cobranca Infinitepay", self.name, "link_pagamento", link)
			frappe.logger().info(f"Link de pagamento criado para {self.name}: {link}")

		except requests.exceptions.RequestException as e:
			frappe.db.set_value("Cobranca Infinitepay", self.name, "status", "Erro")
			frappe.logger().error(f"Erro ao criar link InfinitePay para {self.name}: {e}")
			frappe.throw(_("Erro ao criar link de pagamento na InfinitePay. Tente novamente."))

	def _montar_payload(self, handle):
		webhook_url = (
			frappe.utils.get_url()
			+ "/api/method/gris.api.financeiro.infinitepay_checkout.webhook_infinitepay"
		)

		payload = {
			"handle": handle,
			"items": [
				{
					"description": item.descricao,
					"quantity": int(item.quantidade),
					"price": int(item.preco * 100),
				}
				for item in self.itens
			],
			"order_nsu": self.name,
			"webhook_url": webhook_url,
		}

		if self.redirect_url:
			payload["redirect_url"] = self.redirect_url

		if self.customer_name or self.customer_email or self.customer_phone:
			customer = {}
			if self.customer_name:
				customer["name"] = self.customer_name
			if self.customer_email:
				customer["email"] = self.customer_email
			if self.customer_phone:
				customer["phone_number"] = self.customer_phone
			payload["customer"] = customer

		if self.address_cep or self.address_street:
			address = {}
			if self.address_cep:
				address["cep"] = self.address_cep
			if self.address_street:
				address["street"] = self.address_street
			if self.address_neighborhood:
				address["neighborhood"] = self.address_neighborhood
			if self.address_number:
				address["number"] = self.address_number
			if self.address_complement:
				address["complement"] = self.address_complement
			payload["address"] = address

		return payload


@frappe.whitelist()
def sincronizar_pagamento(
	name: str,
	transaction_nsu: str | None = None,
	slug: str | None = None,
) -> dict:
	"""Consulta a InfinitePay para confirmar pagamento e atualiza a Cobranca.

	Útil quando o webhook não chegou (falha de rede, URL inacessível, etc.).
	Faz a mesma verificação server-to-server do webhook e, se aprovado,
	atualiza os campos e salva — disparando o on_update normal (que propaga
	pra Convite Festa via doc_events).

	`slug` é opcional. Quando informado (ou já presente no campo invoice_slug)
	é enviado ao payment_check, aumentando a chance de a InfinitePay localizar
	a fatura.
	"""
	from gris.api.financeiro.infinitepay_checkout import _verificar_pagamento

	doc = frappe.get_doc("Cobranca Infinitepay", name)
	doc.check_permission("write")

	if doc.status == "Pago":
		return {"ok": True, "status": "Pago", "message": _("Cobrança já está paga.")}

	handle = frappe.db.get_single_value("Configuracao infinitepay", "handle")
	if not handle:
		frappe.throw(_("Handle não configurado em Configuracao infinitepay."))

	tx = (transaction_nsu or doc.transaction_nsu or "").strip() or None
	slug_final = (slug or doc.invoice_slug or "").strip() or None

	try:
		verificacao = _verificar_pagamento(handle, doc.name, tx, slug_final)
	except (requests.exceptions.RequestException, ValueError) as exc:
		frappe.throw(_("Não foi possível confirmar o pagamento na InfinitePay: {0}").format(str(exc)))

	if not verificacao.get("paid"):
		return {
			"ok": False,
			"status": doc.status,
			"message": _("A InfinitePay informa que esta cobrança ainda não foi paga."),
		}

	valor_esperado_centavos = sum(
		int(item.quantidade or 0) * round(float(item.preco) * 100) for item in doc.itens
	)
	paid_amount = verificacao.get("paid_amount", 0)
	if paid_amount < valor_esperado_centavos:
		frappe.throw(
			_("Valor pago ({0}) menor que o esperado ({1}). Pagamento não foi sincronizado.").format(
				paid_amount, valor_esperado_centavos
			)
		)

	doc.update(
		{
			"invoice_slug": verificacao.get("invoice_slug") or slug_final or doc.invoice_slug or "",
			"amount": verificacao.get("amount", 0),
			"paid_amount": paid_amount,
			"installments": verificacao.get("installments", 0),
			"capture_method": verificacao.get("capture_method", ""),
			"transaction_nsu": tx or verificacao.get("transaction_nsu", "") or doc.transaction_nsu,
			"receipt_url": verificacao.get("receipt_url", doc.receipt_url or ""),
			"status": "Pago",
		}
	)
	doc.save(ignore_permissions=True)

	return {
		"ok": True,
		"status": "Pago",
		"message": _("Cobrança sincronizada como Paga."),
	}


@frappe.whitelist()
def marcar_pago_manualmente(name: str, transaction_nsu: str, justificativa: str) -> dict:
	"""Marca a Cobranca como Paga sem consultar a InfinitePay.

	Escape hatch para quando o webhook falhou e o `payment_check` não consegue
	identificar o pagamento (precisaria do `slug`, que só vem por webhook).
	Restrito a System Manager; loga quem fez e a justificativa via Comment.
	"""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Apenas administradores podem marcar pagamento manualmente."))
	if not transaction_nsu or len(transaction_nsu.strip()) < 8:
		frappe.throw(_("Informe o Transaction NSU real da InfinitePay."))
	if not justificativa or len(justificativa.strip()) < 10:
		frappe.throw(_("Informe uma justificativa detalhada (mínimo 10 caracteres)."))

	doc = frappe.get_doc("Cobranca Infinitepay", name)
	if doc.status == "Pago":
		return {"ok": True, "message": _("Cobrança já está paga.")}

	valor_centavos = sum(int(it.quantidade or 0) * round(float(it.preco) * 100) for it in doc.itens)
	doc.update(
		{
			"transaction_nsu": transaction_nsu.strip(),
			"amount": valor_centavos,
			"paid_amount": valor_centavos,
			"status": "Pago",
		}
	)
	doc.save(ignore_permissions=True)
	doc.add_comment(
		"Comment",
		text=(
			f"Pagamento marcado manualmente por {frappe.session.user}. "
			f"transaction_nsu={transaction_nsu.strip()}. "
			f"Justificativa: {justificativa.strip()}"
		),
	)

	return {"ok": True, "message": _("Cobrança marcada como Paga manualmente.")}
