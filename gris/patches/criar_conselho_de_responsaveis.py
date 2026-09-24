"""Cria a área e a função fixas do Conselho de Responsáveis.

A estrutura não entra como fixture pelo mesmo motivo de
`semear_unidades_organizacionais`: a Gestão de Adultos edita áreas pela interface, e o
import de fixtures sobrescreveria essas edições a cada migrate.

Os responsáveis em si não são gravados — os nós do organograma são derivados do cadastro
de `Responsavel`. O que este patch cria é só o lugar onde eles aparecem.
"""

from __future__ import annotations

import frappe


def execute():
	if not frappe.db.table_exists("Unidade Organizacional"):
		return
	if not frappe.db.table_exists("Funcao Voluntario"):
		return

	from gris.api.gestao_adultos.responsaveis import garantir_estrutura_do_conselho

	criados = garantir_estrutura_do_conselho()
	if any(criados.values()):
		print(f"  → Conselho de Responsáveis: {criados}")
		frappe.db.commit()
