import frappe

from gris.api.administracao.transparencia import (
	TIPOS_COM_CARTORIO,
	listar_documentos_transparencia,
	tipos_de_documento,
)
from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/administracao/transparencia"


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={ROTA}"
		raise frappe.Redirect

	# Só `Gestor da UEL` (página estrita em `portal_access`); os endpoints checam de novo.
	enrich_context(context, ROTA)
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = ROTA

	context.documentos = listar_documentos_transparencia()
	context.regras = {"tipos_com_cartorio": list(TIPOS_COM_CARTORIO)}
	# Os pareceres são geridos no Financeiro; o link só aparece para quem abre aquela página.
	context.pode_pareceres = user_has_access("/financeiro/pareceres")

	# Todo select começa com um item vazio: o componente do design system escolhe a
	# primeira opção sozinho ao inicializar, e o save gravaria um valor não escolhido.
	context.tipo_items = [
		{"label": "Selecione o tipo", "value": ""},
		*({"label": tipo, "value": tipo} for tipo in tipos_de_documento()),
	]
	context.area_items = [
		{"label": "Sem área", "value": ""},
		*(
			{"label": area, "value": area}
			for area in frappe.get_all("Unidade Organizacional", pluck="name", order_by="name asc")
		),
	]
	return context
