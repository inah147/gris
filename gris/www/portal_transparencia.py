import frappe


def get_context(context):
	years = frappe.get_all(
		"Transparencia", fields=["ano_referencia"], distinct=True, order_by="ano_referencia desc"
	)
	context.years = [row.ano_referencia for row in years if row.ano_referencia]

	# Captura o ano selecionado do formulário HTML
	ano_selecionado = frappe.form_dict.get("ano_referencia")
	context.ano_selecionado = ano_selecionado

	# Se nenhum ano foi selecionado, usa o mais recente como padrão
	if not ano_selecionado and context.years:
		ano_selecionado = context.years[0]
		context.ano_selecionado = ano_selecionado

	# Recupera logo do single DocType
	uel_def = frappe.get_doc("Definicao da UEL")
	context.logo = uel_def.logo

	# Define subtitulo
	context.subtitle = f"{uel_def.tipo_uel} {uel_def.nome_da_uel} - {uel_def.numeral}/{uel_def.regiao}"

	# Recupera documentos públicos da child table
	documentos_publicos = [
		{"nome": doc.nome_do_documento, "arquivo": doc.arquivo} for doc in uel_def.documentos if doc.publico
	]
	context.documentos_gerais = documentos_publicos if documentos_publicos else None
