import frappe

from gris.api.manutencao.pagina import preparar
from gris.api.manutencao.portal import listar_acompanhamento

no_cache = 1


def get_context(context):
	preparar(context, "/manutencao/acompanhamento")

	# Página renderizada no servidor: é só leitura, e assim aparece completa
	# mesmo em conexão ruim, sem esperar uma segunda requisição.
	somente_minhas = frappe.form_dict.get("minhas")
	dados = listar_acompanhamento(somente_minhas)

	context.somente_minhas = dados["somente_minhas"]
	context.secoes = [
		{
			"id": "em-execucao",
			"titulo": "Em execução",
			"descricao": "Alguém já está cuidando destas.",
			"icone": "hammer",
			"itens": dados["em_execucao"],
		},
		{
			"id": "proximas",
			"titulo": "Próximas manutenções",
			"descricao": "Já avaliadas e na fila, pela data prevista.",
			"icone": "calendar-clock",
			"itens": dados["proximas"],
		},
		{
			"id": "em-analise",
			"titulo": "Aguardando avaliação",
			"descricao": "Recebidas; a equipe ainda vai definir prioridade e data.",
			"icone": "inbox",
			"itens": dados["em_analise"],
		},
		{
			"id": "encerradas",
			"titulo": "Encerradas recentemente",
			"descricao": "Concluídas ou recusadas nos últimos 30 dias.",
			"icone": "circle-check",
			"itens": dados["encerradas"],
		},
	]
	context.total = sum(len(secao["itens"]) for secao in context.secoes)
	return context
