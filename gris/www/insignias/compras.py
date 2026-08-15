from datetime import date

import frappe
from frappe.utils import flt

from gris.api.insignias import consultas, permissoes
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

# A fila de trabalho do financeiro: pedidos que ainda exigem alguma ação.
STATUS_ABERTOS = ["Solicitada", "Comprada", "Recebida"]


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/insignias/compras"
		raise frappe.Redirect

	permissoes.garantir_financeiro()

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/insignias/compras"

	abertas = consultas.listar_solicitacoes({"status": ["in", STATUS_ABERTOS]})
	encerradas = consultas.listar_solicitacoes({"status": ["in", ["Entregue", "Cancelada"]]}, limite=100)

	# Pendentes primeiro (Solicitada > Comprada > Recebida), depois as mais antigas.
	ordem = {status: indice for indice, status in enumerate(STATUS_ABERTOS)}
	abertas.sort(key=lambda linha: (ordem.get(linha["status"], 99), linha["data_solicitacao"] or date.min))

	context.solicitacoes_abertas = abertas
	context.solicitacoes_encerradas = encerradas
	context.aguardando_compra = [linha for linha in abertas if linha["status"] == "Solicitada"]

	context.total_aguardando = len(context.aguardando_compra)
	context.valor_aguardando = consultas.formatar_moeda(
		sum(flt(linha["valor_estimado"]) for linha in context.aguardando_compra)
	)
	context.total_em_transito = len([linha for linha in abertas if linha["status"] == "Comprada"])
	context.total_a_entregar = len([linha for linha in abertas if linha["status"] == "Recebida"])

	enrich_context(context, "/insignias/compras")
	return context
