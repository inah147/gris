import frappe

from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	token = (frappe.form_dict.get("token") or "").strip()

	context.title = "Avaliação da Festa"
	context.show_sidebar = False
	context.no_header = True
	context.no_footer = True
	context.token = token
	context.page_state = "invalid"
	context.festa_titulo = ""
	context.rating_options = [{"value": str(i), "label": str(i)} for i in range(11)]

	uel_data = get_uel_cached()
	if uel_data:
		context.logo = uel_data.get("logo")
		context.subtitle = (
			f"{uel_data.get('tipo_uel', '')} {uel_data.get('nome_da_uel', '')} "
			f"- {uel_data.get('numeral', '')}/{uel_data.get('regiao', '')}"
		).strip()

	if not token:
		return context

	festa_name = frappe.db.get_value("Avaliacao Festa", {"token_convidado": token}, "festa")
	if not festa_name:
		return context

	context.festa_titulo = frappe.db.get_value("Festa", festa_name, "nome_festa") or festa_name
	context.page_state = "form"

	return context
