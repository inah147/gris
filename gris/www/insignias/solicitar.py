import frappe

from gris.api.insignias import consultas, permissoes
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

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
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/insignias/solicitar"
		raise frappe.Redirect

	permissoes.garantir_solicitante()

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/insignias/solicitar"

	catalogo = consultas.itens_catalogo()
	context.catalogo_vazio = not catalogo
	# Define se o estado vazio oferece o atalho para cadastrar ou só orienta a pedir.
	context.pode_gerenciar_catalogo = permissoes.pode_gerenciar_catalogo()
	# O macro `select` pré-seleciona o primeiro item quando não recebe `selected`.
	# A opção vazia à frente evita que o formulário abra com um item já escolhido.
	context.catalogo_items = [
		{"label": "Selecione o item", "value": "", "type": "item"},
		*catalogo,
	]
	context.associados_items = [
		{"label": "Nenhum", "value": "", "type": "item"},
		*consultas.itens_associados(),
	]
	context.ramo_items = [
		{"label": "Selecione o ramo", "value": "", "type": "item"},
		*[{"label": ramo, "value": ramo, "type": "item"} for ramo in RAMOS],
	]
	# Preços expostos ao JS apenas para exibir o total estimado; o servidor recalcula tudo.
	# Serializado no template com `tojson`, que escapa e marca como seguro — uma string
	# JSON pronta seria escapada pelo autoescape e quebraria o JSON.parse.
	context.precos = consultas.precos_catalogo()
	enrich_context(context, "/insignias/solicitar")
	return context
