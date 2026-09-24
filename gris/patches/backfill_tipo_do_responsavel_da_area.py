"""Marca como `Associado` o líder das áreas gravadas antes de o responsável poder liderar.

`Unidade Organizacional.responsavel` virou Dynamic Link para aceitar os dois tipos de
pessoa do organograma, e quem diz de qual cadastro é o `tipo_responsavel`. Toda área que
já existia aponta para um `Associado` — o campo só aceitava esse DocType —, mas a coluna
nasce vazia, e um Dynamic Link sem tipo recusa a próxima gravação da área.

Escrito em SQL de propósito: passar por `save()` dispararia o `validate()` de cada área,
que recusa responsável hoje inativo e faria o migrate parar por um dado legado.
"""

from __future__ import annotations

import frappe


def execute():
	if not frappe.db.table_exists("Unidade Organizacional"):
		return
	if not frappe.db.has_column("Unidade Organizacional", "tipo_responsavel"):
		return

	# Toda área, inclusive a que ainda não tem líder: `_validate_links` roda **antes** do
	# `validate()` do controller, então um tipo vazio no banco faria a primeira gravação
	# que escolhesse um responsável morrer antes de o default ter chance de entrar.
	frappe.db.sql(
		"""
		UPDATE `tabUnidade Organizacional`
		SET `tipo_responsavel` = 'Associado'
		WHERE COALESCE(`tipo_responsavel`, '') = ''
		"""
	)
	frappe.db.commit()
	print("  → tipo_responsavel preenchido nas unidades organizacionais")
