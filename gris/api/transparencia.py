import frappe


@frappe.whitelist(allow_guest=True)
def get_arquivos_por_ano(ano_referencia):
	# Conteúdo público: ignora permissões para permitir acesso a Guest
	arquivos = frappe.get_all(
		"Transparencia",
		fields=["title", "arquivo", "area"],
		filters={"ano_referencia": ano_referencia, "publicado": 1},
		ignore_permissions=True,
	)
	areas = {}
	for arq in arquivos:
		area = arq.area or "Sem área"
		if area not in areas:
			areas[area] = []
		areas[area].append({"title": arq.title, "arquivo": arq.arquivo})
	return {"areas": areas}
