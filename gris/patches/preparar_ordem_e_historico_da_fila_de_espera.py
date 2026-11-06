import frappe

from gris.api.recepcao_fila import CAMPO_HISTORICO, DOCTYPE_FILA, DOCTYPE_PASSAGEM, STATUS_FILA


def execute():
	"""Dá posição a quem já estava na fila e abre a passagem pela fila de cada um.

	A fila passou a ter ordem própria (``Fila de Espera.posicao``), que a recepção pode
	mudar arrastando o card. Quem já estava nela recebe a posição da ordem de entrada,
	que era a ordem exibida até aqui.

	A passagem aberta guarda o status de onde o jovem veio, mas quem entrou antes não
	tem esse dado: a linha nasce sem ``status_anterior``, a tela diz "Não registrado" e
	o chamar devolve o jovem ao status que as etapas concluídas indicam (ver
	``gris.api.recepcao_fila.status_de_retorno``). Inventar o status de origem seria
	mostrar como fato o que é palpite.
	"""
	if not frappe.db.table_exists(DOCTYPE_FILA):
		return

	fila = frappe.get_all(
		DOCTYPE_FILA,
		fields=["name", "associado", "ramo", "dt_inclusao_fila"],
		order_by="dt_inclusao_fila asc, creation asc",
	)

	posicoes: dict[str, int] = {}
	for linha in fila:
		chave = linha.ramo or ""
		posicoes[chave] = posicoes.get(chave, 0) + 1
		frappe.db.set_value(DOCTYPE_FILA, linha.name, "posicao", posicoes[chave], update_modified=False)

	associados = list({linha.associado for linha in fila if linha.associado})
	if not associados:
		return

	com_passagem_aberta = set(
		frappe.get_all(
			DOCTYPE_PASSAGEM,
			filters={
				"parenttype": "Novo Associado",
				"parentfield": CAMPO_HISTORICO,
				"parent": ["in", associados],
				"saida_em": ["is", "not set"],
			},
			pluck="parent",
		)
	)
	# Só quem está de fato com status "Fila de espera": numa entrada órfã a passagem nunca
	# seria fechada, porque o controller fecha a passagem quando o status sai da fila.
	na_fila = set(
		frappe.get_all(
			"Novo Associado",
			filters={"name": ["in", associados], "status": STATUS_FILA},
			pluck="name",
		)
	)

	entrada_por_associado: dict[str, object] = {}
	for linha in fila:
		if linha.associado and linha.associado not in entrada_por_associado:
			entrada_por_associado[linha.associado] = linha.dt_inclusao_fila

	for associado, entrada_em in entrada_por_associado.items():
		if associado in com_passagem_aberta or associado not in na_fila:
			continue
		# Passagens anteriores (já fechadas) podem existir se o patch rodar de novo.
		ultimo_idx = frappe.db.count(
			DOCTYPE_PASSAGEM,
			{"parenttype": "Novo Associado", "parentfield": CAMPO_HISTORICO, "parent": associado},
		)
		frappe.get_doc(
			{
				"doctype": DOCTYPE_PASSAGEM,
				"parenttype": "Novo Associado",
				"parentfield": CAMPO_HISTORICO,
				"parent": associado,
				"idx": ultimo_idx + 1,
				"entrada_em": entrada_em,
				"status_anterior": "",
			}
		).db_insert()
