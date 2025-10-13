import frappe

from gris.api.portal_cache_utils import make_file_public


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
		# Torna o arquivo público antes de retornar
		arquivo_url = make_file_public(arq.arquivo) if arq.arquivo else None
		areas[area].append({"title": arq.title, "arquivo": arquivo_url})
	return {"areas": areas}
