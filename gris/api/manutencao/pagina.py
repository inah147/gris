# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Peças comuns das páginas de `/manutencao/*` (contexto Jinja, selos, opções).

Sem `@frappe.whitelist()`: só os controladores em `gris/www/manutencao` chamam.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from gris.api.manutencao import constantes as c
from gris.api.portal_access import enrich_context, user_has_access

# Tom (cor do token do tema) e ícone de cada status. Cor nunca sozinha: o selo
# sempre leva ícone e texto.
SELO_STATUS: dict[str, dict[str, str]] = {
	c.STATUS_RECEBIDA: {"tom": "neutro", "icone": "inbox"},
	c.STATUS_PLANEJADA: {"tom": "info", "icone": "calendar-clock"},
	c.STATUS_EM_ANDAMENTO: {"tom": "primario", "icone": "hammer"},
	c.STATUS_AGUARDANDO: {"tom": "alerta", "icone": "package-search"},
	c.STATUS_CONCLUIDA: {"tom": "sucesso", "icone": "circle-check"},
	c.STATUS_NAO_SERA_FEITA: {"tom": "perigo", "icone": "circle-x"},
}

SELO_PRIORIDADE: dict[str, dict[str, str]] = {
	c.PRIORIDADE_BAIXA: {"tom": "neutro", "icone": "arrow-down"},
	c.PRIORIDADE_MEDIA: {"tom": "info", "icone": "minus"},
	c.PRIORIDADE_ALTA: {"tom": "alerta", "icone": "arrow-up"},
	c.PRIORIDADE_URGENTE: {"tom": "perigo", "icone": "siren"},
}


def preparar(context, rota: str) -> None:
	"""Login obrigatório, checagem de acesso e sidebar do portal."""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={rota}"
		raise frappe.Redirect

	if not user_has_access(rota):
		frappe.throw(_("Você não tem permissão para acessar esta página."), frappe.PermissionError)

	context.active_link = rota
	context.selo_status = SELO_STATUS
	context.selo_prioridade = SELO_PRIORIDADE
	enrich_context(context, rota)


def itens_select(opcoes: tuple[str, ...] | list[str], vazio: str | None = None) -> list[dict[str, Any]]:
	"""Opções no formato da macro `select` do design system.

	A opção vazia à frente evita que o formulário abra com um valor já
	escolhido — a macro pré-seleciona o primeiro item sem ela.
	"""
	itens = [{"label": vazio, "value": "", "type": "item"}] if vazio is not None else []
	itens += [{"label": opcao, "value": opcao, "type": "item"} for opcao in opcoes]
	return itens
