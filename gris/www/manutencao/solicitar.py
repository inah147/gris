from gris.api.manutencao import constantes as c
from gris.api.manutencao.pagina import itens_select, preparar

no_cache = 1


def get_context(context):
	preparar(context, "/manutencao/solicitar")

	context.categoria_items = itens_select(c.CATEGORIAS, vazio="Selecione")
	context.urgencias = [
		{
			"valor": c.URGENCIA_PODE_ESPERAR,
			"dica": "Incomoda, mas dá para usar normalmente.",
			"icone": "clock",
		},
		{
			"valor": c.URGENCIA_ATRAPALHA,
			"dica": "Impede ou atrapalha alguma atividade do grupo.",
			"icone": "triangle-alert",
		},
		{
			"valor": c.URGENCIA_RISCO,
			"dica": "Fio exposto, vazamento, algo que pode machucar alguém.",
			"icone": "siren",
		},
	]
	context.titulo_max = c.TITULO_MAX
	context.local_max = c.LOCAL_MAX
	context.descricao_max = c.DESCRICAO_MAX
	return context
