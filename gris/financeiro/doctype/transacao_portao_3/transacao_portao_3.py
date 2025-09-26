# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import hashlib
import re
from datetime import datetime

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime


class TransacaoPortao3(Document):
	def _get_centro_de_custo(self):
		if not self.carteira:
			return None

		centro = frappe.db.get_value("Carteira", self.carteira, "centro_de_custo")
		return centro or None

	def _get_destination(self):
		if self.valor is None:
			return None

		if self.valor > 0:
			return f"Grupo Escoteiro Professora Inah De Melo N 147. - Portão 3 | {self.carteira}"

		desc = (self.descricao or "").strip()
		tipo = (self.tipo or "").strip().upper()

		if tipo == "CARTÃO":
			return desc or None

		if tipo == "PIX":
			m = re.search(r"pix realizado para\s+(.*)", desc, flags=re.IGNORECASE)
			return (m.group(1).strip() if m else None) or None

		if tipo == "BOLETO":
			m = re.search(r"pgto de boleto p/\s+(.*)", desc, flags=re.IGNORECASE)
			return (m.group(1).strip() if m else None) or None

		# Observação: mantendo grafia exata solicitada: 'TRANFERÊNCIA ENTRE CARTEIRAS'
		if tipo == "TRANFERÊNCIA ENTRE CARTEIRAS":
			return "Grupo Escoteiro Professora Inah De Melo N 147. - Portão 3"

		return None

	def _get_source(self):
		if self.valor is None:
			return None

		if self.valor < 0:
			return f"Grupo Escoteiro Professora Inah De Melo N 147. - Portão 3 | {self.carteira}"

		if self.valor > 0:
			desc = (self.descricao or "").strip()
			tipo = (self.tipo or "").strip().upper()

			if tipo == "PIX":
				m = re.search(r"pix recebido de\s+(.*)", desc, flags=re.IGNORECASE)
				return (m.group(1).strip() if m else None) or None

			if tipo == "TRANFERÊNCIA ENTRE CARTEIRAS":
				return "Grupo Escoteiro Professora Inah De Melo N 147. - Portão 3"

		return None

	def before_insert(self):
		# create id
		tx_id = (
			f"{self.timestamp}{self.descricao}{self.valor}{self.entrada_saida}"
			+ f"{self.carteira}{self.tipo}{self.tipo_de_transacao}"
		)

		tx_hash = hashlib.md5(tx_id.encode("utf-8")).hexdigest()
		self.id = f"Portao3-{tx_hash}"

		# parse date
		try:
			dt = get_datetime(self.timestamp)
		except Exception:
			dt = datetime.fromtimestamp(int(self.timestamp))
		self.data_transacao = dt.date()

	def after_insert(self):
		# is repasse
		if self.tipo == "TRANFERÊNCIA ENTRE CARTEIRAS":
			is_internal_tx = 1
		else:
			is_internal_tx = 0

		stats = {"extrato_inseridos": 0, "extrato_repetidos": 0, "extrato_erros": 0}
		try:
			if frappe.db.exists("Transacao Extrato Geral", {"id": self.id}):
				stats["extrato_repetidos"] += 1
			else:
				tx = frappe.get_doc(
					{
						"doctype": "Transacao Extrato Geral",
						"id": self.id,
						"data_transacao": self.data_transacao,
						"timestamp_transacao": self.timestamp,
						"descricao": self.descricao,
						"valor": self.valor,
						"valor_absoluto": abs(self.valor),
						"debito_credito": str(self.entrada_saida).capitalize()
						if self.entrada_saida
						else "Desconhecido",
						"metodo": str(self.tipo).capitalize() if self.tipo else "Desconhecido",
						"origem": self._get_source(),
						"destino": self._get_destination(),
						"instituicao": "Portão 3",
						"centro_de_custo": self._get_centro_de_custo(),
						"carteira": self.carteira,
						"repasse_entre_contas": is_internal_tx,
					}
				)
				tx.insert()
				stats["extrato_inseridos"] += 1
		except Exception as e:
			stats["extrato_erros"] += 1
			frappe.log_error(str(e), "Importação Transacao Extrato Geral")
		# Opcional: loga estatísticas no Error Log
		frappe.log_error(str(stats), "Stats Transacao Extrato Geral")
		pass
