import frappe

from gris.api.manutencao import constantes as c
from gris.api.manutencao.pagina import itens_select, preparar
from gris.api.manutencao.portal import FILTRO_ABERTAS, FILTRO_TODAS, listar_gestao

no_cache = 1


def get_context(context):
	preparar(context, "/manutencao/gestao")

	form = frappe.form_dict
	dados = listar_gestao(
		status=form.get("status"),
		prioridade=form.get("prioridade"),
		categoria=form.get("categoria"),
		busca=form.get("busca"),
	)

	context.itens = dados["itens"]
	context.filtros = dados["filtros"]
	context.contagem = dados["contagem"]
	context.atrasadas = dados["atrasadas"]
	context.total_abertas = sum(dados["contagem"][s] for s in c.STATUS_ABERTOS)

	# Resumo no topo: cada cartão é também um atalho para o filtro do status.
	context.resumo = [
		{
			"rotulo": status,
			"valor": dados["contagem"][status],
			"href": f"/manutencao/gestao?status={status}",
			"ativo": dados["filtros"]["status"] == status,
		}
		for status in c.STATUS_ABERTOS
	]

	context.filtro_status_items = [
		{"label": "Abertas", "value": FILTRO_ABERTAS, "type": "item"},
		{"label": "Todas", "value": FILTRO_TODAS, "type": "item"},
		*itens_select(c.STATUS),
	]
	context.filtro_prioridade_items = itens_select(c.PRIORIDADES, vazio="Todas as prioridades")
	context.filtro_categoria_items = itens_select(c.CATEGORIAS, vazio="Todas as categorias")

	# As opções dos selects do dialog precisam existir no HTML inicial: o
	# select.js do Basecoat captura a lista de opções uma única vez.
	context.status_items = itens_select(c.STATUS)
	context.prioridade_items = itens_select(c.PRIORIDADES)
	context.categoria_items = itens_select(c.CATEGORIAS)
	return context
