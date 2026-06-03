import frappe

from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def get_context(context):
	token = (frappe.form_dict.get("token") or "").strip()

	context.title = "Avaliação de Festa"
	context.show_sidebar = False
	context.no_header = True
	context.no_footer = True
	context.token = token
	context.page_state = "invalid"
	context.avaliador_nome = ""
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

	row = frappe.db.get_value(
		"Avaliacao Individual Festa",
		{"token": token},
		["avaliador", "avaliacao_concluida", "parent"],
		as_dict=True,
	)

	if not row:
		return context

	if row.avaliacao_concluida:
		context.page_state = "already_submitted"
		context.avaliador_nome = row.avaliador or ""
		return context

	festa_name = frappe.db.get_value("Avaliacao Festa", row.parent, "festa")
	if festa_name:
		context.festa_titulo = frappe.db.get_value("Festa", festa_name, "nome_festa") or festa_name

	context.avaliador_nome = row.avaliador or ""
	context.page_state = "form"

	return context
