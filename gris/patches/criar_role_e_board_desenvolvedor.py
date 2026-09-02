from __future__ import annotations

import frappe


def execute():
	"""Provisiona o módulo Sugestões e Problemas em sites já existentes.

	Cria a role 'Desenvolvedor' e o quadro "Desenvolvimento do GRIS", que é onde
	as tarefas espelho das solicitações nascem. Ambos são idempotentes, então o
	patch é seguro de reexecutar.
	"""
	from gris.gestao_de_tarefas.board_sync_sugestoes import (
		ensure_board_desenvolvimento,
		sincronizar_desenvolvedores_no_board,
	)
	from gris.install import _garantir_role_desenvolvedor

	_garantir_role_desenvolvedor()
	ensure_board_desenvolvimento()
	sincronizar_desenvolvedores_no_board()
	frappe.db.commit()
