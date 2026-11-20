from datetime import datetime

import frappe

from gris.api.financeiro.demonstrativo import listar_anos_disponiveis, montar_demonstrativo, normalizar_ano
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/financeiro/relatorios"
		raise frappe.Redirect

	# Recupera logo e define para sidebar
	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"
	context.active_link = "/financeiro/relatorios"
	enrich_context(context, "/financeiro/relatorios")

	ano = normalizar_ano(frappe.form_dict.get("ano") or datetime.now().year)
	context.demonstrativo = montar_demonstrativo(ano)
	context.demonstrativo["year_options"] = listar_anos_disponiveis(ano)

	# include static assets
	context.add_css = "/financeiro/demonstrativo.css"
	context.add_js = "/financeiro/demonstrativo.js"
