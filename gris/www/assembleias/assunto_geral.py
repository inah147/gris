from urllib.parse import quote

import frappe

from gris.api.assembleias import constantes as c
from gris.api.assembleias.formularios import pessoa_do_usuario, situacao_agora
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ROTA = "/assembleias/assunto_geral"


def get_context(context):
	assembleia = frappe.form_dict.get("assembleia") or ""
	if frappe.session.user == "Guest":
		volta = quote(f"{ROTA}?assembleia={assembleia}", safe="")
		frappe.local.flags.redirect_location = f"/login?redirect-to={volta}"
		raise frappe.Redirect

	enrich_context(context, ROTA)
	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None

	context.encontrada = bool(assembleia and frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, assembleia))
	if not context.encontrada:
		return context
	doc = frappe.get_doc(c.DOCTYPE_ASSEMBLEIA, assembleia)
	situacao = situacao_agora(doc, c.FORMULARIO_ASSUNTOS_GERAIS)
	context.assembleia = doc
	context.situacao = situacao
	context.fecha_em = frappe.utils.get_datetime(situacao["fecha_em"])
	context.pessoa = pessoa_do_usuario()
	return context
