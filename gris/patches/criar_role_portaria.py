from __future__ import annotations

import frappe


def execute():
	"""Cria a role 'Portaria' se ainda não existir.

	Usada pela página /festas/portaria e pelos endpoints de operação de
	entrada. Sem desk_access — é uma role exclusivamente de portal.
	"""
	if frappe.db.exists("Role", "Portaria"):
		return
	role = frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": "Portaria",
			"desk_access": 0,
			"home_page": "/festas/portaria",
		}
	)
	role.insert(ignore_permissions=True)
	frappe.db.commit()
