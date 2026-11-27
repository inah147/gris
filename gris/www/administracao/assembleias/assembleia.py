import frappe

from gris.api.assembleias.constantes import DOCTYPE_ASSEMBLEIA
from gris.api.assembleias.endpoints import contagem_de_inscricoes
from gris.api.assembleias.permissoes import pode_gerenciar_assembleias
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/administracao/assembleias/assembleia"


def get_context(context):
	name = frappe.form_dict.get("name") or ""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={ROTA}?name={name}"
		raise frappe.Redirect

	enrich_context(context, ROTA)
	if context.access_denied or not pode_gerenciar_assembleias():
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect

	if not name or not frappe.db.exists(DOCTYPE_ASSEMBLEIA, name):
		frappe.local.flags.redirect_location = "/administracao/assembleias"
		raise frappe.Redirect

	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.active_link = "/administracao/assembleias"

	doc = frappe.get_doc(DOCTYPE_ASSEMBLEIA, name)
	context.assembleia = doc
	context.inscricoes = contagem_de_inscricoes(name)
	return context
