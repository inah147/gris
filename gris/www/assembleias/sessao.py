from urllib.parse import quote

import frappe

from gris.api.assembleias import constantes as c
from gris.api.assembleias.pessoas import opcoes_de_pessoas
from gris.api.assembleias.sessao import PAPEL_GESTOR, estado_da_sessao, papel_na_assembleia
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/assembleias/sessao"


def get_context(context):
	"""Modo sessão: só para quem gerencia e para a mesa da assembleia (RF-16)."""
	name = frappe.form_dict.get("assembleia") or ""
	if frappe.session.user == "Guest":
		volta = quote(f"{ROTA}?assembleia={name}", safe="")
		frappe.local.flags.redirect_location = f"/login?redirect-to={volta}"
		raise frappe.Redirect

	enrich_context(context, ROTA)
	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None

	context.encontrada = bool(name and frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, name))
	if not context.encontrada:
		return context
	doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, name)
	context.assembleia = doc
	context.papel = papel_na_assembleia(doc)
	if not context.papel:
		return context
	context.sessao = estado_da_sessao(doc, context.papel)
	context.e_gestor = context.papel == PAPEL_GESTOR
	context.pessoas_16 = opcoes_de_pessoas(16, doc.data) if context.e_gestor else []
	if context.e_gestor:
		context.active_link = "/administracao/assembleias"
	return context
