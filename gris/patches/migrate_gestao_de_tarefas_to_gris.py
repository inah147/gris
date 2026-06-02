"""Migra Gestao de Tarefas de child table (modulo Gestao de Projetos) para
DocType independente (modulo Gris).

Estrategia drop+insert (aprovada pelo usuario): as linhas antigas (parent/parentfield/idx)
sao apagadas; o Patch B (create_board_for_projetos_existentes) ira garantir o Board
para cada Projeto e novas tarefas sao criadas pelos fluxos da aplicacao.
"""

from __future__ import annotations

import frappe


def execute() -> None:
	_drop_legacy_rows()
	_drop_orphan_comments()
	_drop_legacy_parent_column()
	_delete_legacy_doctype_record()


def _drop_legacy_rows() -> None:
	"""Apaga todas as linhas antigas da tabela child Gestao de Tarefas."""
	if not frappe.db.table_exists("Gestao de Tarefas"):
		return

	frappe.db.sql("DELETE FROM `tabGestao de Tarefas`")


def _drop_orphan_comments() -> None:
	"""Remove Comments cujos `reference_name` apontam para linhas ja deletadas.

	A coluna `reference_doctype = 'Gestao de Tarefas'` continua valida para o
	novo DocType independente; orfaos serao apagados para evitar ruido.
	"""
	frappe.db.sql(
		"""
		DELETE FROM `tabComment`
		WHERE reference_doctype = %s
		""",
		("Gestao de Tarefas",),
	)


def _drop_legacy_parent_column() -> None:
	"""Remove coluna `tarefas` em tabProjeto caso o framework nao tenha removido."""
	if not frappe.db.table_exists("Projeto"):
		return
	if frappe.db.has_column("Projeto", "tarefas"):
		try:
			frappe.db.sql("ALTER TABLE `tabProjeto` DROP COLUMN `tarefas`")
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title="Falha ao remover coluna legacy `tarefas` de tabProjeto",
			)


def _delete_legacy_doctype_record() -> None:
	"""Remove o DocType antigo (modulo Gestao de Projetos) para forcar resync
	do novo DocType (modulo Gris) na proxima etapa de migration.
	"""
	if not frappe.db.exists("DocType", "Gestao de Tarefas"):
		return

	current_module = frappe.db.get_value("DocType", "Gestao de Tarefas", "module")
	if current_module == "Gris":
		return

	frappe.db.sql(
		"DELETE FROM `tabDocType` WHERE name = %s",
		("Gestao de Tarefas",),
	)
	frappe.db.sql(
		"DELETE FROM `tabDocField` WHERE parent = %s",
		("Gestao de Tarefas",),
	)
