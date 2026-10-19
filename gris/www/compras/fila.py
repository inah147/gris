from datetime import date

import frappe
from frappe import _

from gris.api.compras import consultas, permissoes
from gris.api.portal_access import enrich_context

no_cache = 1

# O fluxo de um pedido, na ordem em que acontece. Cada etapa vira uma aba da lista,
# com o que a pessoa faz nela: para quem compra é uma tarefa, para quem só
# acompanha é a explicação de quem está com o pedido.
ETAPAS = [
	{
		"status": "Solicitada",
		"tarefa": "Compre e registre a compra",
		"acompanhamento": "O gestor da área compra",
	},
	{
		"status": "Comprada",
		"tarefa": "Marque quando chegar à sede",
		"acompanhamento": "O material está a caminho",
	},
	{
		"status": "Recebida",
		"tarefa": "Entregue a quem pediu",
		"acompanhamento": "Quem pediu retira na sede",
	},
	{
		"status": "Entregue",
		"tarefa": "Pedido concluído",
		"acompanhamento": "Pedido concluído",
	},
]

# O que a aba mostra logo abaixo do título: o que fazer com os pedidos desta etapa.
ORIENTACAO_DA_ETAPA = {
	"Solicitada": (
		"Estes pedidos esperam a compra. Use o roteiro para a loja, mais abaixo, para comprar tudo de "
		"uma vez; depois clique em “Registrar compra” em cada pedido."
	),
	"Comprada": ("A compra já foi feita. Quando o material chegar à sede, clique em “Marcar como recebido”."),
	"Recebida": (
		"O material está na sede. Quando entregar a quem pediu, clique em “Registrar entrega” — "
		"a própria pessoa também pode confirmar pelo portal."
	),
	"Entregue": "Pedidos que já chegaram às mãos de quem pediu.",
}
ORIENTACAO_TODOS = "Todos os pedidos, de todas as etapas, inclusive entregues e cancelados."

# Ordem de exibição: o que exige ação primeiro, o que está encerrado por último.
ORDEM_STATUS = [*consultas.STATUS_ORDEM, "Cancelada"]
STATUS_ENCERRADOS = {"Entregue", "Cancelada"}

#: Sinal de vezes, como em "4 vezes Lenço". chr() porque o ruff barra o caractere literal como ambíguo.
VEZES = chr(0xD7)

# Pedido parado nesta etapa há mais tempo que isso ganha destaque na lista.
DIAS_PARA_ALERTA = 7


def _url(slug: str | None, **params) -> str:
	partes = [f"area={slug}"] if slug else []
	partes += [f"{chave}={valor}" for chave, valor in params.items() if valor]
	return "/compras/fila" + (f"?{'&'.join(partes)}" if partes else "")


def _proximo_passo(linha: dict) -> dict:
	"""O que acontece a seguir com o pedido, e se quem está vendo é quem faz."""
	status = linha["status"]
	area = linha.get("area") or "da área"
	primeiro_nome = (linha.get("solicitante_nome") or "").split(" ")[0] or "quem pediu"

	if status == "Solicitada":
		if linha["pode_agir"]:
			return {"acao": "comprar", "rotulo": "Registrar compra"}
		return {"texto": f"Com o gestor de {area}, para comprar"}
	if status == "Comprada":
		if linha["pode_agir"]:
			return {"acao": "receber", "rotulo": "Marcar como recebido"}
		return {"texto": "A caminho da sede"}
	if status == "Recebida":
		if linha["pode_agir"]:
			return {"acao": "entregar", "rotulo": "Registrar entrega"}
		return {"texto": f"Na sede, esperando {primeiro_nome} retirar"}
	if status == "Entregue":
		return {"texto": "Concluído"}
	return {"texto": "Cancelado"}


def _resumo_itens(itens: list[dict], limite: int = 2) -> dict:
	"""Os primeiros itens do pedido por extenso e quantos ficaram de fora."""
	return {
		"visiveis": itens[:limite],
		"restantes": max(len(itens) - limite, 0),
		"completo": ", ".join(f"{item['quantidade']}{VEZES} {item['nome']}" for item in itens),
	}


def get_context(context):
	slug = frappe.form_dict.get("area")
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={_url(slug)}"
		raise frappe.Redirect

	areas_visiveis = permissoes.areas_para(permissoes.pode_ver_fila)
	if not areas_visiveis:
		frappe.throw(_("Você não acompanha a lista de compras de nenhuma área."), frappe.PermissionError)

	area = consultas.area_da_requisicao(slug) if slug else None
	if area and area not in areas_visiveis:
		frappe.throw(f"Você não acompanha a lista de compras de {area}.", frappe.PermissionError)

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
			{"label": "Todas as áreas", "href": _url(None), "ativo": not area},
			*[
				{"label": nome, "href": _url(permissoes.slug_da_area(nome)), "ativo": nome == area}
				for nome in areas_visiveis
			],
		]
		if len(areas_visiveis) > 1
		else []
	)

	# Sem parâmetro a lista abre em "Aguardando compra"; cada etapa é uma aba, e
	# "Todos" mostra o histórico inteiro, inclusive entregues e cancelados.
	status_param = frappe.form_dict.get("status")
	mostrar = frappe.form_dict.get("mostrar")
	visiveis = consultas.status_visiveis(status_param, mostrar)
	context.mostrando_todas = visiveis is None
	context.status_filtrado = visiveis[0] if visiveis else None

	contagem = consultas.contar_por_status(filtro_area)
	context.etapas = [
		{
			"numero": numero,
			"status": etapa["status"],
			"rotulo": consultas.STATUS_META[etapa["status"]]["etapa"],
			"icone": consultas.STATUS_META[etapa["status"]]["icone"],
			"tom": consultas.STATUS_META[etapa["status"]]["tom"],
			"dica": etapa["tarefa"] if context.pode_agir else etapa["acompanhamento"],
			"valor": contagem.get(etapa["status"], 0),
			"href": _url(slug, status=etapa["status"]),
			"ativo": context.status_filtrado == etapa["status"] and not context.mostrando_todas,
		}
		for numero, etapa in enumerate(ETAPAS, start=1)
	]
	context.total_todos = sum(contagem.values())
	context.url_todas = _url(slug, mostrar=consultas.MOSTRAR_TODAS)

	filtros = dict(filtro_area)
	if visiveis is not None:
		filtros["status"] = ["in", visiveis]
	pedidos = consultas.listar_solicitacoes(filtros, com_itens=True)

	# Etapa por etapa, na ordem do fluxo; dentro da etapa, quem espera há mais tempo
	# primeiro. Encerrados ficam no fim, os mais recentes antes.
	ordem = {status: indice for indice, status in enumerate(ORDEM_STATUS)}
	abertos = [linha for linha in pedidos if linha["status"] not in STATUS_ENCERRADOS]
	encerrados = [linha for linha in pedidos if linha["status"] in STATUS_ENCERRADOS]
	abertos.sort(key=lambda linha: (ordem.get(linha["status"], 99), linha["data_solicitacao"] or date.min))
	encerrados.sort(key=lambda linha: linha["data_solicitacao"] or date.min, reverse=True)
	encerrados.sort(key=lambda linha: ordem.get(linha["status"], 99))

	for linha in abertos + encerrados:
		linha["pode_agir"] = permissoes.pode_comprar(linha["area"])
		linha["proximo_passo"] = _proximo_passo(linha)
		linha["resumo_itens"] = _resumo_itens(linha.get("itens") or [])
		linha["parado"] = (
			linha["status"] not in STATUS_ENCERRADOS and (linha["dias_na_etapa"] or 0) >= DIAS_PARA_ALERTA
		)

	context.solicitacoes = abertos + encerrados
	context.mostrar_area = not area

	if context.mostrando_todas:
		context.titulo_pedidos = "Todos os pedidos"
		context.orientacao = ORIENTACAO_TODOS
	else:
		context.titulo_pedidos = consultas.STATUS_META[context.status_filtrado]["etapa"]
		context.orientacao = ORIENTACAO_DA_ETAPA.get(context.status_filtrado, "")
		if not context.pode_agir:
			context.orientacao = consultas.STATUS_META[context.status_filtrado]["descricao"]

	# O roteiro para a loja só aparece para quem compra, e só com os pedidos das
	# áreas em que a pessoa compra.
	aguardando = [linha for linha in abertos if linha["status"] == "Solicitada" and linha["pode_agir"]]
	por_nome = {linha["name"]: linha for linha in aguardando}
	itens_lista = consultas.lista_de_compras([linha["name"] for linha in aguardando])
	for item in itens_lista:
		item["destinos"] = [
			{
				"pedido": pedido,
				"quantidade": quantidade,
				"nome": por_nome[pedido]["solicitante_nome"] or por_nome[pedido]["solicitante"],
				"secao": por_nome[pedido]["secao"],
				"ramo_slug": por_nome[pedido]["ramo_slug"],
			}
			for pedido, quantidade in item["quantidade_por_pedido"].items()
			if pedido in por_nome
		]

	grupos: dict[str, list[dict]] = {}
	for item in itens_lista:
		grupos.setdefault(item["area"] or "Outros", []).append(item)
	ordem_areas = {nome: indice for indice, nome in enumerate(permissoes.AREAS)}
	context.roteiro = [
		{
			"area": nome,
			"itens": itens,
			"pecas": sum(item["quantidade"] for item in itens),
			"valor_fmt": consultas.formatar_moeda(sum(item["valor_total"] for item in itens)),
		}
		for nome, itens in sorted(grupos.items(), key=lambda grupo: ordem_areas.get(grupo[0], 99))
	]
	context.roteiro_pedidos = ",".join(linha["name"] for linha in aguardando)
	context.roteiro_total_itens = len(itens_lista)
	context.roteiro_total_pecas = sum(item["quantidade"] for item in itens_lista)
	context.roteiro_valor_total = consultas.formatar_moeda(sum(item["valor_total"] for item in itens_lista))
	context.total_aguardando = len(aguardando)
	context.mostrar_roteiro = bool(itens_lista) and context.status_filtrado == "Solicitada"

	enrich_context(context, "/compras/fila")
	return context
