import frappe

from gris.api.portal_cache_utils import make_file_public


def build_areas_por_ano(ano_referencia):
	if not ano_referencia:
		return {}

	# Conteúdo público: ignora permissões para permitir acesso a Guest.
	arquivos = frappe.get_all(
		"Transparencia",
		fields=["title", "arquivo", "area", "tipo_arquivo", "trimestre_referencia"],
		filters={"ano_referencia": ano_referencia, "publicado": 1},
		ignore_permissions=True,
	)
	areas = {}
	for arq in arquivos:
		area = arq.area or "Sem área"
		if area not in areas:
			areas[area] = []

		arquivo_url = make_file_public(arq.arquivo) if arq.arquivo else None
		title = arq.title
		if arq.tipo_arquivo == "Parecer trimestral da comissão fiscal" and arq.trimestre_referencia:
			title = f"{arq.title} - {arq.trimestre_referencia}º Trimestre"

		areas[area].append({"title": title, "arquivo": arquivo_url})

	return areas


# Público por intenção: é a página de transparência do grupo, cujos arquivos são
# publicados justamente para consulta aberta.
@frappe.whitelist(allow_guest=True)  # nosemgrep
def get_arquivos_por_ano(ano_referencia):
	return {"areas": build_areas_por_ano(ano_referencia)}
