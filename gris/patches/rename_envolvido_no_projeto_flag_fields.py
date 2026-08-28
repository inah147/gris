from __future__ import annotations

import frappe

DOCTYPE_NAME = "Envolvido no Projeto"
FIELD_RENAMES = (
	("e_coordenador", "coordenador"),
	("e_padrinho_orientador", "padrinho_orientador"),
	("e_aprovador", "aprovador"),
)


def execute() -> None:
	if not frappe.db.table_exists(DOCTYPE_NAME):
		return

	for old_field, new_field in FIELD_RENAMES:
		_rename_or_sync_flag_field(old_field, new_field)


def _rename_or_sync_flag_field(old_field: str, new_field: str) -> None:
	has_old = frappe.db.has_column(DOCTYPE_NAME, old_field)
	has_new = frappe.db.has_column(DOCTYPE_NAME, new_field)

	if has_old and not has_new:
		frappe.db.rename_column(DOCTYPE_NAME, old_field, new_field)
		return

	if not (has_old and has_new):
		return

	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	frappe.db.sql(
		f"""
		UPDATE `tab{DOCTYPE_NAME}`
		SET `{new_field}` = CASE
			WHEN IFNULL(`{new_field}`, 0) = 1 OR IFNULL(`{old_field}`, 0) = 1 THEN 1
			ELSE 0
		END
		"""
	)
