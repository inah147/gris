"""Candidaturas de uma assembleia: página pública, sem login (RF-13).

Mostra só nome, registro escoteiro, motivação e biografia das inscrições ativas. Nada
de CPF, telefone, e-mail, idade ou usuário.
"""

import frappe

from gris.api.assembleias import constantes as c
from gris.api.assembleias.formularios import dados_publicos
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	context.no_cache = 1
	uel_data = get_uel_cached(use_cache=False) or {}
	context.logo = uel_data.get("logo")
	context.nome_uel = uel_data.get("nome_da_uel") or ""

	name = frappe.form_dict.get("assembleia") or ""
	context.encontrada = bool(name and frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, name))
	if not context.encontrada:
		return context
	assembleia = frappe.db.get_value(c.DOCTYPE_ASSEMBLEIA, name, ["titulo", "data", "local"], as_dict=True)
	context.titulo = assembleia.titulo
	context.local = assembleia.local
	context.dados = dados_publicos(name)
	context.vazio = not context.dados["chapas"] and not any(
		g["candidaturas"] for g in context.dados["cargos"]
	)
	return context
