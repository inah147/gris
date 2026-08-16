import frappe

from gris.api.insignias import consultas, permissoes
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

TIPOS = [
	"Distintivo de Progressão",
	"Especialidade",
	"Insígnia Especial",
	"Distintivo de Identificação",
	"Distintivo de Função",
	"Outro",
]

RAMOS = [
	"Todos",
	"Filhotes",
	"Lobinho",
	"Escoteiro",
	"Sênior",
	"Pioneiro",
	"Escotistas e Dirigentes",
]


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/insignias/catalogo"
		raise frappe.Redirect

	permissoes.garantir_gestor_catalogo()

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/insignias/catalogo"

	itens = consultas.listar_catalogo_completo()
	context.itens = itens
	context.total_ativos = len([i for i in itens if i["ativo"]])
	context.total_inativos = len(itens) - context.total_ativos

	context.tipo_items = [{"label": t, "value": t, "type": "item"} for t in TIPOS]
	context.ramo_items = [{"label": r, "value": r, "type": "item"} for r in RAMOS]

	enrich_context(context, "/insignias/catalogo")
	return context
