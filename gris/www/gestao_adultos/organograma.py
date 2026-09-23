import frappe

from gris.api.gestao_adultos.organograma import (
	FILTRO_SEM_AREA,
	existe_associado_sem_area,
	listar_areas_para_filtro,
)
from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/gestao_adultos/organograma"
		raise frappe.Redirect

	enrich_context(context, "/gestao_adultos/organograma")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/gestao_adultos/organograma"

	opcoes = [{"value": "", "label": "Todas as áreas"}, *listar_areas_para_filtro()]
	if existe_associado_sem_area():
		opcoes.append({"value": FILTRO_SEM_AREA, "label": "Sem área definida"})
	context.opcoes_area = opcoes

	# Pergunta do usuário, não da pessoa do card: resolvida uma vez aqui em vez de a
	# cada abertura do painel.
	context.pode_abrir_ficha = user_has_access("/associados/detalhe")
	return context
