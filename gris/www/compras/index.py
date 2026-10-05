import frappe
from frappe import _

from gris.api.compras import permissoes
from gris.api.portal_access import enrich_context, user_has_access

no_cache = 1

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
		"Cada área (Programa Educativo, Manutenção e Administrativo) tem o seu responsável pela compra."
	)
	context.module_items = [
		{
			"href": "/compras/solicitar",
			"title": "Comprar",
			"description": "Peça insígnias, material de manutenção ou administrativo: escolha a área e monte o pedido.",
		},
		{
			"href": "/compras/minhas_solicitacoes",
			"title": "Minhas solicitações",
			"description": "Acompanhe os seus pedidos e confirme o recebimento.",
		},
		{
			"href": "/compras/fila",
			"title": "Lista de compras",
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
