from __future__ import annotations

import frappe

from gris.api.sugestoes.constantes import ROLE_ACOMPANHAMENTO
from gris.api.users.roles import add_user_roles


def execute():
	"""Cria a role de acompanhamento e concede a todo usuário de Associado.

	O usuário do associado é criado com o `id_escoteiros` como e-mail (ver
	`gris.api.users.user_manager.create_associate_user`), então é por esse campo
	que ligamos Associado a User.

	Idempotente: `add_user_roles` grava as linhas de `Has Role` diretamente e
	ignora quem já tem a role — de propósito, porque passar por `User.save()`
	repopularia os papéis a partir do Role Profile e apagaria concessões manuais.
	"""
	from gris.install import _garantir_role_acompanhamento_sugestoes

	_garantir_role_acompanhamento_sugestoes()

	emails = [
		(id_escoteiros or "").strip()
		for id_escoteiros in frappe.get_all("Associado", pluck="id_escoteiros", limit_page_length=0)
		if (id_escoteiros or "").strip()
	]
	if not emails:
		frappe.db.commit()
		return

	usuarios = frappe.get_all(
		"User",
		filters={"name": ("in", emails)},
		pluck="name",
		limit_page_length=0,
	)
	for user in usuarios:
		add_user_roles(user, [ROLE_ACOMPANHAMENTO])

	frappe.db.commit()
