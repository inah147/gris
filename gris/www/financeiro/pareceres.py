import frappe

from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/financeiro/pareceres"
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
	context.active_link = "/financeiro/pareceres"
	enrich_context(context, "/financeiro/pareceres")

	# Fetch transparency records limited to the two Parecer tipos (trimestral & anual)
	parecer_types = [
		"Parecer trimestral da comissão fiscal",
		"Parecer anual da comissão fiscal",
	]
	docs = frappe.get_all(
		"Transparencia",
		filters={"tipo_arquivo": ["in", parecer_types]},
		fields=[
			"name",
			"tipo_arquivo",
			"publicado",
			"trimestre_referencia",
			"ano_referencia",
			"arquivo",
			"area",
		],
		order_by="ano_referencia desc, trimestre_referencia desc",
	)

	annual = []
	quarterly = []

	for d in docs:
		_tipo = d.tipo_arquivo or ""
		published = bool(d.publicado)
		trimestre = d.trimestre_referencia
		ano = d.ano_referencia

		area = getattr(d, "area", None)
		arquivo = getattr(d, "arquivo", None)
		if _tipo == "Parecer trimestral da comissão fiscal":
			if trimestre and ano:
				period = f"{int(trimestre)}º de {ano}"
			else:
				period = "—"
			quarterly.append(
				{
					"name": d.name,
					"tipo_arquivo": _tipo,
					"period": period,
					"published": published,
					"area": area,
					"ano_referencia": ano,
					"trimestre_referencia": trimestre,
					"arquivo": arquivo,
				}
			)
		elif _tipo == "Parecer anual da comissão fiscal":
			period = str(ano) if ano else "—"
			annual.append(
				{
					"name": d.name,
					"tipo_arquivo": _tipo,
					"period": period,
					"published": published,
					"area": area,
					"ano_referencia": ano,
					"arquivo": arquivo,
				}
			)

	context.annual_parecers = annual
	context.quarterly_parecers = quarterly
	# Years for filter (unique, sorted desc)
	years = {p.get("ano_referencia") for p in annual + quarterly if p.get("ano_referencia")}
	context.parecer_years = sorted(years, reverse=True)
	# Permission flag for showing edit controls
	context.can_edit_pareceres = frappe.has_permission("Transparencia", ptype="write")
	context.can_delete_pareceres = frappe.has_permission("Transparencia", ptype="delete")
	return context
