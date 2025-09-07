import frappe


@frappe.whitelist()
def get_arquivos_por_ano(ano_referencia):
	arquivos = frappe.get_all(
		"Transparencia", fields=["title", "arquivo", "area"], filters={"ano_referencia": ano_referencia}
	)
	areas = {}
	for arq in arquivos:
		area = arq.area or "Sem área"
		if area not in areas:
			areas[area] = []
		areas[area].append({"title": arq.title, "arquivo": arq.arquivo})
	return {"areas": areas}
