# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document

INFINITEPAY_CHECKOUT_URL = "https://api.infinitepay.io/invoices/public/checkout/links"


class CobrancaInfinitepay(Document):
	def validate(self):
		self._validar_itens()

	def after_insert(self):
		self._criar_link_pagamento()

	def _validar_itens(self):
		if not self.itens:
			frappe.throw("É necessário adicionar pelo menos 1 item na cobrança.")

		for item in self.itens:
			if not item.descricao:
				frappe.throw("Todos os itens devem ter uma descrição.")
			if not item.quantidade or item.quantidade <= 0:
				frappe.throw(f"Item '{item.descricao}': quantidade deve ser maior que zero.")
			if not item.preco or item.preco <= 0:
				frappe.throw(f"Item '{item.descricao}': preço deve ser maior que zero.")

	def _criar_link_pagamento(self):
		handle = frappe.db.get_single_value("Configuracao infinitepay", "handle")
		if not handle:
			frappe.db.set_value("Cobranca Infinitepay", self.name, "status", "Erro")
			frappe.throw("Handle não configurado em Configuracao infinitepay.")

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
			frappe.logger().info(
				f"Link de pagamento criado para {self.name}: {link}"
			)

		except requests.exceptions.RequestException as e:
			frappe.db.set_value("Cobranca Infinitepay", self.name, "status", "Erro")
			frappe.logger().error(
				f"Erro ao criar link InfinitePay para {self.name}: {e}"
			)
			frappe.throw("Erro ao criar link de pagamento na InfinitePay. Tente novamente.")

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
