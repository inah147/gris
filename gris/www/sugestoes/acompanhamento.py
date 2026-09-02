import frappe
from frappe import _

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached
from gris.api.sugestoes.constantes import COLUNAS, MODULOS, TIPOS, coluna_inicial
from gris.api.sugestoes.portal import desenvolvedores, pode_triar

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/sugestoes/acompanhamento"
		raise frappe.Redirect

	if not user_has_access("/sugestoes/acompanhamento"):
		frappe.throw(_("Você não tem permissão para acessar esta página."), frappe.PermissionError)

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/sugestoes/acompanhamento"

	# O quadro em si é carregado por AJAX (listar_board): o get_context só monta
	# o shell e os filtros, então a página aparece antes da consulta terminar.
	context.pode_triar = pode_triar()
	context.colunas = list(COLUNAS)

	context.filtro_tipo_items = [
		{"label": "Todos os tipos", "value": "", "type": "item"},
		*[{"label": tipo, "value": tipo, "type": "item"} for tipo in TIPOS],
	]
	context.filtro_modulo_items = [
		{"label": "Todos os módulos", "value": "", "type": "item"},
		*[{"label": modulo, "value": modulo, "type": "item"} for modulo in MODULOS],
	]

	# As opções do select de responsável precisam existir no HTML inicial: o
	# select.js do Basecoat captura a lista de `[role="option"]` uma única vez,
	# na inicialização, e ignora nós injetados depois — tanto no clique quanto
	# no setter de `.value`.
	# O JS precisa saber quais colunas representam tipo para detectar, no drop,
	# que o arrasto é um pedido de reclassificação e não uma mudança de status.
	context.coluna_de_triagem_por_tipo = {tipo: coluna_inicial(tipo) for tipo in TIPOS}

	context.responsavel_items = [
		{"label": "Sem responsável", "value": "", "type": "item"},
		*[{"label": dev["nome"], "value": dev["email"], "type": "item"} for dev in desenvolvedores()],
	]

	enrich_context(context, "/sugestoes/acompanhamento")
	return context
