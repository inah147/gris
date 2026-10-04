import frappe
from frappe import _

from gris.api.compras import permissoes
from gris.api.portal_access import enrich_context, user_has_access

no_cache = 1

DESCRICOES = {
	permissoes.AREA_PROGRAMA_EDUCATIVO: "Insígnias e distintivos do Plano Educativo.",
	permissoes.AREA_MANUTENCAO: "Material e serviços para a sede e os equipamentos do grupo.",
	permissoes.AREA_ADMINISTRATIVO: "Material de escritório, impressões e demais itens da administração.",
}


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/compras"
		raise frappe.Redirect

	if not user_has_access("/compras"):
		frappe.throw(_("Você não tem permissão para acessar Compras."), frappe.PermissionError)

	context.active_link = "/compras"
	context.module_title = "Compras"
	context.module_subtitle = (
		"Solicite o que o grupo precisa comprar e acompanhe o pedido até a entrega. "
		"Cada área tem o seu responsável pela compra."
	)
	context.module_items = [
		*[
			{
				"href": f"/compras/{meta['slug']}",
				"title": area,
				"description": DESCRICOES[area],
			}
			for area, meta in permissoes.AREAS.items()
		],
		{
			"href": "/compras/minhas_solicitacoes",
			"title": "Minhas solicitações",
			"description": "Acompanhe os seus pedidos e confirme o recebimento.",
		},
		{
			"href": "/compras/fila",
			"title": "Fila de compras",
			"description": "Pedidos aguardando compra nas áreas que você acompanha.",
			"visible": permissoes.pode_ver_alguma_fila(),
		},
		{
			"href": "/compras/catalogo",
			"title": "Catálogo",
			"description": "Itens que podem ser solicitados, separados por área.",
		},
	]
	enrich_context(context, "/compras")
	return context
