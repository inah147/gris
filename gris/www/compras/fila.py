from datetime import date

import frappe
from frappe import _

from gris.api.compras import consultas, permissoes
from gris.api.portal_access import enrich_context

no_cache = 1

# A fila de trabalho do gestor da área: pedidos que ainda exigem alguma ação.
STATUS_ABERTOS = ["Solicitada", "Comprada", "Recebida"]
STATUS_ENCERRADOS = ["Entregue", "Cancelada"]

ROTULOS_STATUS = {
	"Solicitada": "Aguardando compra",
	"Comprada": "Compradas, a caminho",
	"Recebida": "Recebidas, a entregar",
	"Entregue": "Entregues",
	"Cancelada": "Canceladas",
}


def _url(slug: str | None, **params) -> str:
	partes = [f"area={slug}"] if slug else []
	partes += [f"{chave}={valor}" for chave, valor in params.items() if valor]
	return "/compras/fila" + (f"?{'&'.join(partes)}" if partes else "")


def get_context(context):
	slug = frappe.form_dict.get("area")
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={_url(slug)}"
		raise frappe.Redirect

	areas_visiveis = permissoes.areas_para(permissoes.pode_ver_fila)
	if not areas_visiveis:
		frappe.throw(_("Você não acompanha a fila de compras de nenhuma área."), frappe.PermissionError)

	area = consultas.area_da_requisicao(slug) if slug else None
	if area and area not in areas_visiveis:
		frappe.throw(f"Você não acompanha a fila de compras de {area}.", frappe.PermissionError)

	areas = [area] if area else areas_visiveis
	slug = slug if area else None
	filtro_area = {"area": ["in", areas]}

	context.area = area
	context.area_slug = slug or ""
	context.active_link = "/compras/fila"
	context.titulo_lista = f"Lista de compras · {area}" if area else "Lista de compras"
	context.pode_agir = any(permissoes.pode_comprar(a) for a in areas)
	context.filtros_area = (
		[
			{"label": "Todas", "href": _url(None), "ativo": not area},
			*[
				{"label": nome, "href": _url(permissoes.slug_da_area(nome)), "ativo": nome == area}
				for nome in areas_visiveis
			],
		]
		if len(areas_visiveis) > 1
		else []
	)

	# O que já foi comprado (ou encerrado) só aparece quando a pessoa pede: clicando
	# num indicador (filtra por status) ou em "Ver todos".
	status_param = frappe.form_dict.get("status")
	mostrar = frappe.form_dict.get("mostrar")
	visiveis = consultas.status_visiveis(status_param, mostrar)
	context.mostrando_todas = visiveis is None
	context.status_filtrado = visiveis[0] if visiveis else None
	context.filtro_padrao = visiveis == consultas.STATUS_PADRAO_VISIVEL

	contagem = consultas.contar_por_status(filtro_area)
	context.indicadores = [
		{
			"status": status,
			"rotulo": ROTULOS_STATUS[status],
			"valor": contagem.get(status, 0),
			"href": _url(slug, status=status),
			"ativo": context.status_filtrado == status and not context.mostrando_todas,
		}
		for status in STATUS_ABERTOS
	]
	context.url_todas = _url(slug, mostrar=consultas.MOSTRAR_TODAS)
	context.url_padrao = _url(slug)

	filtros = dict(filtro_area)
	if visiveis is not None:
		filtros["status"] = ["in", visiveis]
	pedidos = consultas.listar_solicitacoes(filtros)

	if context.mostrando_todas:
		abertas = [linha for linha in pedidos if linha["status"] in STATUS_ABERTOS]
		context.solicitacoes_encerradas = [linha for linha in pedidos if linha["status"] in STATUS_ENCERRADOS]
	else:
		abertas = pedidos
		context.solicitacoes_encerradas = []

	# Pendentes primeiro (Solicitada > Comprada > Recebida), depois as mais antigas.
	ordem = {status: indice for indice, status in enumerate(STATUS_ABERTOS)}
	abertas.sort(key=lambda linha: (ordem.get(linha["status"], 99), linha["data_solicitacao"] or date.min))
	for linha in abertas:
		linha["pode_agir"] = permissoes.pode_comprar(linha["area"])

	context.solicitacoes_abertas = abertas
	context.titulo_pedidos = (
		"Todos os pedidos em aberto"
		if context.mostrando_todas
		else f"Pedidos · {ROTULOS_STATUS.get(context.status_filtrado, context.status_filtrado)}"
	)

	# A lista consolidada é o roteiro de quem vai à loja: só aparece para quem compra,
	# e só com os pedidos das áreas em que a pessoa compra.
	context.aguardando_compra = [
		linha for linha in abertas if linha["status"] == "Solicitada" and linha["pode_agir"]
	]
	context.lista_de_compras = consultas.lista_de_compras(
		[linha["name"] for linha in context.aguardando_compra]
	)
	context.lista_total_pecas = sum(linha["quantidade"] for linha in context.lista_de_compras)
	context.lista_valor_total = consultas.formatar_moeda(
		sum(linha["valor_total"] for linha in context.lista_de_compras)
	)
	context.total_aguardando = len(context.aguardando_compra)

	enrich_context(context, "/compras/fila")
	return context
