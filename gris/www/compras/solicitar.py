import frappe

from gris.api.compras import consultas, permissoes
from gris.api.compras.endpoints import RAMOS_VALIDOS
from gris.api.portal_access import enrich_context

no_cache = 1

DESCRICOES_AREA = {
	permissoes.AREA_PROGRAMA_EDUCATIVO: "Insígnias e distintivos do Plano Educativo.",
	permissoes.AREA_MANUTENCAO: "Material e serviços para a sede e os equipamentos do grupo.",
	permissoes.AREA_ADMINISTRATIVO: "Material de escritório, impressões e demais itens da administração.",
}

RAMOS = [
	"Filhotes",
	"Lobinho",
	"Escoteiro",
	"Sênior",
	"Pioneiro",
	"Escotistas e Dirigentes",
	"Grupo (geral)",
]


def get_context(context):
	slug = frappe.form_dict.get("area")
	if frappe.session.user == "Guest":
		destino = f"/compras/solicitar?area={slug}" if slug else "/compras"
		frappe.local.flags.redirect_location = f"/login?redirect-to={destino}"
		raise frappe.Redirect

	if not slug:
		# Sem área, a página oferece a escolha da área; o formulário vem depois.
		permissoes.garantir_autenticado()
		context.area = None
		context.escolher_area = True
		context.active_link = "/compras/solicitar"
		context.areas_compra = [
			{
				"href": f"/compras/solicitar?area={meta['slug']}",
				"title": nome,
				"description": DESCRICOES_AREA[nome],
			}
			for nome, meta in permissoes.AREAS.items()
		]
		enrich_context(context, "/compras/solicitar")
		return context

	area = consultas.area_da_requisicao(slug)
	permissoes.garantir_autenticado()

	context.area = area
	context.area_slug = slug
	context.programa_educativo = area == permissoes.AREA_PROGRAMA_EDUCATIVO
	context.active_link = "/compras/solicitar"

	catalogo = consultas.itens_catalogo(area)
	context.catalogo_vazio = not catalogo
	# Define se a página oferece o cadastro de item novo ou só orienta a pedir à gestão.
	context.pode_cadastrar_item = permissoes.pode_cadastrar_item(area)
	# O macro `select` pré-seleciona o primeiro item quando não recebe `selected`.
	# A opção vazia à frente evita que o formulário abra com um item já escolhido.
	context.catalogo_items = [
		{"label": "Selecione o item", "value": "", "type": "item"},
		*catalogo,
	]
	context.ramo_items = [
		{"label": "Selecione o ramo", "value": "", "type": "item"},
		*[{"label": ramo, "value": ramo, "type": "item"} for ramo in RAMOS if ramo in RAMOS_VALIDOS],
	]
	# Preços expostos ao JS apenas para exibir o total estimado; o servidor recalcula tudo.
	# Serializado no template com `tojson`, que escapa e marca como seguro — uma string
	# JSON pronta seria escapada pelo autoescape e quebraria o JSON.parse.
	context.precos = consultas.precos_catalogo(area)
	context.tipo_items = consultas.opcoes_select(consultas.TIPOS_CATALOGO)
	context.ramo_catalogo_items = consultas.opcoes_select(consultas.RAMOS_CATALOGO)
	context.item_novo = frappe.form_dict.get("item_novo") or ""
	enrich_context(context, "/compras/solicitar")
	return context
