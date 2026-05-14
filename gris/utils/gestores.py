from __future__ import annotations

import frappe


def buscar_destinatarios_gestores() -> list[frappe._dict]:
	"""Retorna lista de {nome, telefone} de usuários habilitados com role 'Gestor de Associado'.

	Resolve telefone via User.mobile_no; para usuários sem número, busca fallback em
	Associado.telefone pelo campo id_escoteiros.
	"""
	role_assignments = frappe.get_all(
		"Has Role",
		filters={"role": "Gestor de Associado", "parenttype": "User"},
		fields=["parent"],
	)
	user_emails = [r.parent for r in role_assignments if r.parent]
	if not user_emails:
		return []

	users = frappe.get_all(
		"User",
		filters={"name": ["in", user_emails], "enabled": 1},
		fields=["name", "full_name", "mobile_no"],
	)

	users_sem_telefone = [u.name for u in users if not (u.get("mobile_no") or "").strip()]
	associado_por_user: dict[str, frappe._dict] = {}
	if users_sem_telefone:
		associados_gestores = frappe.get_all(
			"Associado",
			filters={"id_escoteiros": ["in", users_sem_telefone]},
			fields=["id_escoteiros", "telefone"],
		)
		associado_por_user = {
			str(a.get("id_escoteiros")): a for a in associados_gestores if a.get("id_escoteiros")
		}

	destinatarios: list[frappe._dict] = []
	for user in users:
		telefone = (user.get("mobile_no") or "").strip()
		if not telefone:
			assoc = associado_por_user.get(str(user.name))
			if assoc:
				telefone = (assoc.get("telefone") or "").strip()
		if not telefone:
			continue
		destinatarios.append(
			frappe._dict(
				{
					"nome": (user.get("full_name") or str(user.name)).strip(),
					"telefone": telefone,
				}
			)
		)

	return destinatarios
