import frappe

from gris.api.compras import consultas, permissoes
from gris.api.portal_access import enrich_context

no_cache = 1

ROTA = "/compras/minhas_solicitacoes"


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={ROTA}"
		raise frappe.Redirect

	permissoes.garantir_autenticado()
	context.active_link = ROTA

	slug = frappe.form_dict.get("area")
	area = consultas.area_da_requisicao(slug) if slug else None
	slug = slug if area else None
	context.area = area

	def url(**params) -> str:
		partes = [f"area={slug}"] if slug else []
		partes += [f"{chave}={valor}" for chave, valor in params.items()]
		return ROTA + (f"?{'&'.join(partes)}" if partes else "")

	# Por padrão só os pedidos aguardando compra; o resto aparece quando a pessoa
	# clica num status do resumo ou em "Ver todas".
	status_param = frappe.form_dict.get("status")
	visiveis = consultas.status_visiveis(status_param, frappe.form_dict.get("mostrar"))
	context.mostrando_todas = visiveis is None
	context.status_filtrado = visiveis[0] if visiveis else None
	context.filtro_padrao = visiveis == consultas.STATUS_PADRAO_VISIVEL
	context.url_todas = url(mostrar=consultas.MOSTRAR_TODAS)
	context.url_padrao = url()

	context.solicitacoes = consultas.minhas_solicitacoes(status=visiveis, area=area)

	filtros_contagem = {"solicitante": frappe.session.user}
	if area:
		filtros_contagem["area"] = area
	contagem = consultas.contar_por_status(filtros_contagem)
	context.total_solicitacoes = sum(contagem.values())
	context.resumo = [
		{
			"rotulo": status,
			"valor": valor,
			"href": url(status=status),
			"ativo": context.status_filtrado == status and not context.mostrando_todas,
		}
		for status, valor in contagem.items()
	]
	context.filtros_area = [
		{"label": "Todas", "href": ROTA, "ativo": not area},
		*[
			{
				"label": nome,
				"href": f"{ROTA}?area={meta['slug']}",
				"ativo": nome == area,
			}
			for nome, meta in permissoes.AREAS.items()
		],
	]
	context.href_nova = f"/compras/solicitar?area={slug}" if slug else "/compras/solicitar"

	enrich_context(context, ROTA)
	return context
