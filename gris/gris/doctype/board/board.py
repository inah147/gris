from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate

BOARD_REFERENCIA_PERMITIDAS: set[str] = {"Projeto", "Festa", "User"}
NIVEIS_ACESSO: set[str] = {"Gerenciar", "Editar", "Visualizar"}
NIVEL_PESO: dict[str, int] = {"Visualizar": 1, "Editar": 2, "Gerenciar": 3}


class Board(Document):
	def validate(self) -> None:
		self._validate_referencia()

	def before_insert(self) -> None:
		referencia_doctype = (self.referencia_doctype or "").strip()
		if referencia_doctype == "User":
			return

		criador = (self.owner or frappe.session.user or "").strip()
		if criador and criador != "Guest":
			self._adicionar_usuario(criador, nivel_acesso="Gerenciar")

		if referencia_doctype == "Projeto" and (self.referencia_nome or "").strip():
			self._popular_envolvidos_projeto(self.referencia_nome)
		elif referencia_doctype == "Festa" and (self.referencia_nome or "").strip():
			self._popular_envolvidos_festa(self.referencia_nome)

	def _validate_referencia(self) -> None:
		referencia_doctype = (self.referencia_doctype or "").strip()
		referencia_nome = (self.referencia_nome or "").strip()

		if not referencia_doctype and not referencia_nome:
			return

		if not referencia_doctype or not referencia_nome:
			frappe.throw(_("Informe o tipo e o registro do dono ou deixe ambos em branco para quadro solto."))

		if referencia_doctype not in BOARD_REFERENCIA_PERMITIDAS:
			frappe.throw(
				_("DocType de referencia '{0}' nao e permitido para Board.").format(referencia_doctype)
			)

		if not frappe.db.exists(referencia_doctype, referencia_nome):
			frappe.throw(
				_("Registro '{0}' do tipo {1} nao encontrado.").format(referencia_nome, referencia_doctype)
			)

	def _adicionar_usuario(self, user_email: str, nivel_acesso: str = "Visualizar") -> None:
		user_email = (user_email or "").strip()
		if not user_email or user_email == "Guest":
			return
		if not frappe.db.exists("User", user_email):
			return
		if nivel_acesso not in NIVEIS_ACESSO:
			nivel_acesso = "Visualizar"
		for row in self.usuarios_autorizados or []:
			if (row.user or "").strip() == user_email:
				atual = row.nivel_acesso or "Visualizar"
				if NIVEL_PESO.get(nivel_acesso, 0) > NIVEL_PESO.get(atual, 0):
					row.nivel_acesso = nivel_acesso
				return
		self.append(
			"usuarios_autorizados",
			{"user": user_email, "nivel_acesso": nivel_acesso, "adicionado_em": nowdate()},
		)

	def _popular_envolvidos_projeto(self, projeto_name: str) -> None:
		envolvidos = frappe.get_all(
			"Envolvido no Projeto",
			filters={"parent": projeto_name, "parenttype": "Projeto"},
			fields=["user", "email", "associado", "coordenador"],
		)
		for row in envolvidos:
			user = (row.get("user") or "").strip()
			if not user:
				email = (row.get("email") or "").strip()
				if email and frappe.db.exists("User", email):
					user = email
			if user:
				nivel = "Gerenciar" if row.get("coordenador") else "Editar"
				self._adicionar_usuario(user, nivel_acesso=nivel)

		coordenador = frappe.db.get_value("Projeto", projeto_name, "coordenador")
		if coordenador:
			email = frappe.db.get_value("Associado", coordenador, "email")
			if email and frappe.db.exists("User", email):
				self._adicionar_usuario(email, nivel_acesso="Gerenciar")

	def _popular_envolvidos_festa(self, festa_name: str) -> None:
		from gris.gestao_de_tarefas.board_sync_festa import coletar_usuarios_da_festa

		for user, nivel in coletar_usuarios_da_festa(festa_name).items():
			self._adicionar_usuario(user, nivel_acesso=nivel)
