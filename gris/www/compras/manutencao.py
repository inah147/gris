from gris.api.compras import consultas

no_cache = 1


def get_context(context):
	return consultas.contexto_submodulo(context, "manutencao")
