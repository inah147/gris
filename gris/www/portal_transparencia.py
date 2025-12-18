import frappe

from gris.api.portal_cache_utils import get_transparency_years_cached, get_uel_cached


def get_context(context):
	"""Página de transparência totalmente pública (Guest permitido)."""

	# Inclui CSS customizado
	context.style = "/assets/gris/css/portal_transparencia.css"

	# Lista anos (conteúdo público) usando cache controlado
	context.years = get_transparency_years_cached()

	# Ano selecionado (querystring)
	ano_selecionado = frappe.form_dict.get("ano_referencia")
	context.ano_selecionado = ano_selecionado
	if not ano_selecionado and context.years:
		context.ano_selecionado = context.years[0]

	# Dados institucionais (tentar ignorar permissões, fallback se falhar)
	uel_data = get_uel_cached()
	if uel_data:
		context.logo = uel_data.get("logo")
		context.subtitle = f"{uel_data.get('tipo_uel', '')} {uel_data.get('nome_da_uel', '')} - {uel_data.get('numeral', '')}/{uel_data.get('regiao', '')}".strip()
		publicos = [
			{"nome": d.get("nome_do_documento", "Documento"), "arquivo": d.get("arquivo")}
			for d in (uel_data.get("documentos") or [])
			if d.get("publico")
		]
		context.documentos_gerais = publicos or None
	else:
		context.logo = None
		context.subtitle = ""
		context.documentos_gerais = None

	return context
