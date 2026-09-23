from __future__ import annotations

import frappe

# Sementes que antes viviam em `gris/fixtures/unidade_organizacional.json`. Saíram
# das fixtures porque a Gestão de Adultos passou a editar áreas pela interface, e
# o import de fixtures sobrescrevia essas edições a cada migrate.
SEMENTES = ("Presidência", "Financeiro")


def execute():
	if not frappe.db.table_exists("Unidade Organizacional"):
		return

	criadas = 0
	for area in SEMENTES:
		if frappe.db.exists("Unidade Organizacional", area):
			continue
		frappe.get_doc({"doctype": "Unidade Organizacional", "area": area, "ativa": 1}).insert(
			ignore_permissions=True
		)
		criadas += 1

	if criadas:
		frappe.db.commit()
