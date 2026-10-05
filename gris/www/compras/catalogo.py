import frappe

from gris.api.compras import consultas, permissoes
from gris.api.portal_access import enrich_context

no_cache = 1


def get_context(context):
	slug = frappe.form_dict.get("area")
	if frappe.session.user == "Guest":
		destino = f"/compras/catalogo?area={slug}" if slug else "/compras/catalogo"
		frappe.local.flags.redirect_location = f"/login?redirect-to={destino}"
		raise frappe.Redirect

	permissoes.garantir_autenticado()
	area = consultas.area_da_requisicao(slug) if slug else None

	context.area = area
	context.area_slug = slug if area else ""
	context.active_link = "/compras/catalogo"
	context.filtros_area = [
		{"label": "Todas", "href": "/compras/catalogo", "ativo": not area},
		*[
			{
				"label": nome,
				"href": f"/compras/catalogo?area={meta['slug']}",
				"ativo": nome == area,
			}
			for nome, meta in permissoes.AREAS.items()
		],
	]

	itens = consultas.listar_catalogo_completo([area] if area else None)
	context.itens = itens
	context.total_ativos = len([i for i in itens if i["ativo"]])
	context.total_inativos = len(itens) - context.total_ativos

	# Áreas em que a pessoa pode cadastrar: PE só para a gestão de métodos.
	areas_cadastro = permissoes.areas_para(permissoes.pode_cadastrar_item)
	context.pode_cadastrar = bool(areas_cadastro)
	context.area_items = consultas.opcoes_select(areas_cadastro)
	context.area_padrao = area if area in areas_cadastro else (areas_cadastro[0] if areas_cadastro else "")
	context.tipo_items = consultas.opcoes_select(consultas.TIPOS_CATALOGO)
	context.ramo_items = consultas.opcoes_select(consultas.RAMOS_CATALOGO)
	context.area_programa_educativo = permissoes.AREA_PROGRAMA_EDUCATIVO

	enrich_context(context, "/compras/catalogo")
	return context
