# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document

STATUS_NAO_ENTROU = "Não entrou"
STATUS_ENTROU = "Entrou"

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ListaEntradaFesta(Document):
	def validate(self):
		self._sanitizar_email()
		self._sanitizar_telefone()
		self._validar_status_consistente()

	def _sanitizar_email(self):
		if not self.email:
			self.email = None
			return
		email = self.email.strip().lower()
		if not EMAIL_REGEX.match(email):
			frappe.throw(_("E-mail do convidado inválido."))
		self.email = email

	def _sanitizar_telefone(self):
		if not self.telefone:
			self.telefone = None
			return
		digitos = re.sub(r"\D", "", self.telefone)
		self.telefone = digitos or None

	def _validar_status_consistente(self):
		# hora_entrada e status devem andar juntos.
		if self.status == STATUS_ENTROU and not self.hora_entrada:
			frappe.throw(_("Hora de entrada é obrigatória quando o status é 'Entrou'."))
		if self.status == STATUS_NAO_ENTROU:
			self.hora_entrada = None
			self.entrada_registrada_por = None

	@staticmethod
	def marcar_entrada(name: str, user: str | None = None) -> dict:
		"""Marca uma entrada de forma atômica (evita race condition em duplo scan).

		Atualiza apenas se status atual = 'Não entrou'. Retorna:
		- {ok: True, ja_entrou_antes: False, hora_entrada}  se efetivou
		- {ok: True, ja_entrou_antes: True, hora_entrada, registrado_por} se já tinha entrado
		"""
		from frappe.utils import now

		user = user or frappe.session.user
		agora = now()

		# UPDATE atômico: só altera linha cujo status ainda é 'Não entrou'.
		# Retorna número de linhas afetadas; se 0, alguém já marcou antes.
		frappe.db.sql(
			"""
			UPDATE `tabLista Entrada Festa`
			   SET status = %(status)s,
			       hora_entrada = %(agora)s,
			       entrada_registrada_por = %(user)s,
			       modified = %(agora)s,
			       modified_by = %(user)s
			 WHERE name = %(name)s
			   AND status = %(status_atual)s
			""",
			{
				"status": STATUS_ENTROU,
				"status_atual": STATUS_NAO_ENTROU,
				"agora": agora,
				"user": user,
				"name": name,
			},
		)

		# frappe.db.sql retorna () em UPDATE — rowcount é exposto via _cursor.
		cursor = getattr(frappe.db, "_cursor", None)
		linhas = getattr(cursor, "rowcount", 0) if cursor else 0

		if linhas:
			frappe.db.commit()
			return {
				"ok": True,
				"ja_entrou_antes": False,
				"hora_entrada": agora,
				"registrado_por": user,
			}

		# Não atualizou — busca estado atual para retornar info correta.
		row = frappe.db.get_value(
			"Lista Entrada Festa",
			name,
			["status", "hora_entrada", "entrada_registrada_por"],
			as_dict=True,
		)
		return {
			"ok": True,
			"ja_entrou_antes": bool(row and row.status == STATUS_ENTROU),
			"hora_entrada": (row or {}).get("hora_entrada"),
			"registrado_por": (row or {}).get("entrada_registrada_por"),
		}
