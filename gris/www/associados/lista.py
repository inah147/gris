import frappe

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

RAMOS_ORDER = ["Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"]


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/associados/lista"
		raise frappe.Redirect
	# Enrich + permissão
	enrich_context(context, "/associados/lista")
	if context.access_denied:
		frappe.local.flags.redirect_location = "/403"
		raise frappe.Redirect
	# Logo
	uel_data = get_uel_cached()
	context.portal_logo = uel_data.get("logo") if uel_data else None
	context.can_create_associate_users = "Acesso ao Desk" in frappe.get_roles(frappe.session.user)
	# Link ativo
	context.active_link = "/associados/lista"

	rows = frappe.db.sql(
		"""
		SELECT DISTINCT
			NULLIF(categoria,'') AS categoria,
			NULLIF(ramo,'')      AS ramo,
			NULLIF(secao,'')     AS secao,
			NULLIF(funcao,'')    AS funcao,
			NULLIF(area,'')      AS area,
			NULLIF(status,'')    AS status
		FROM `tabAssociado`
		WHERE status_no_grupo='Ativo'
		""",
		as_dict=True,
	)

	def collect(key):
		return sorted({r.get(key) for r in rows if r.get(key)})

	ramos_distinct = collect("ramo")
	ramos_ordenados = [r for r in RAMOS_ORDER if r in ramos_distinct]
	if "Não se aplica" in ramos_distinct:
		ramos_ordenados.append("Não se aplica")

	def as_items(values, all_label):
		return [{"value": "", "label": all_label}] + [{"value": v, "label": v} for v in values]

	context.filter_items_categoria = as_items(collect("categoria"), "Todas")
	context.filter_items_ramo = as_items(ramos_ordenados, "Todos")
	context.filter_items_secao = as_items(collect("secao"), "Todas")
	context.filter_items_funcao = as_items(collect("funcao"), "Todas")
	context.filter_items_area = as_items(collect("area"), "Todas")
	context.filter_items_status = as_items(collect("status"), "Todos")
	context.filter_items_status_no_grupo = [
		{"value": "Ativo", "label": "Ativo"},
		{"value": "Afastado", "label": "Afastado"},
		{"value": "Inativo", "label": "Inativo"},
		{"value": "", "label": "Todos"},
	]

	return context
