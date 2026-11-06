import frappe
from frappe import _
from frappe.utils import getdate, today

from gris.api import recepcao_fila
from gris.api.portal_access import enrich_context
from gris.api.recepcao import formatar_idade, processar_desistencia
from gris.api.recepcao_vagas import calcular_vagas_por_ramo, dados_do_dialog

no_cache = 1


def get_context(context):
	context.active_link = "/recepcao"
	enrich_context(context, "/recepcao")

	# Check permissions
	if (
		not frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "Recepcao"})
		and frappe.session.user != "Administrator"
	):
		frappe.throw(_("Acesso negado"), frappe.PermissionError)

	ramos = ["Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"]

	# Ocupação de cada ramo: a mesma conta que marca os cards da visão geral.
	ocupacao_por_ramo = calcular_vagas_por_ramo()

	# Variantes do badge Basecoat (corresponde a .badge-ramo-* no CSS local).
	# Mantém paridade com visao_geral.py.
	ramo_variant_map = {
		"Filhotes": "ramo-filhotes",
		"Lobinho": "ramo-lobinho",
		"Escoteiro": "ramo-escoteiro",
		"Sênior": "ramo-senior",
		"Pioneiro": "ramo-pioneiro",
	}

	# Fetch Fila de Espera
	fila_items = frappe.get_all(
		"Fila de Espera",
		fields=["name", "associado", "ramo", "dt_inclusao_fila"],
		order_by=recepcao_fila.ORDEM_DA_FILA,
	)

	# Group fila items by ramo for prediction calculation
	fila_by_ramo = {r: [] for r in ramos}
	for item in fila_items:
		if item.ramo in fila_by_ramo:
			fila_by_ramo[item.ramo].append(item)

	kanban_data = {ramo: [] for ramo in ramos}

	# Months mapping
	months_map = [
		"Janeiro",
		"Fevereiro",
		"Março",
		"Abril",
		"Maio",
		"Junho",
		"Julho",
		"Agosto",
		"Setembro",
		"Outubro",
		"Novembro",
		"Dezembro",
	]

	# Recalculate stats and predictions per ramo
	for ramo in ramos:
		ocupacao = ocupacao_por_ramo[ramo]
		limite = ocupacao.limite
		ativos = ocupacao.ativos
		novos = ocupacao.novos
		saidas_futuras = ocupacao.saidas_futuras

		# Prediction Logic
		vagas_reais_agora = limite - (ativos + novos)
		availability_timeline = []

		# 1. Immediate spots
		if vagas_reais_agora > 0:
			for _vaga in range(vagas_reais_agora):
				availability_timeline.append(getdate(today()))

		# 2. Future spots from exits
		future_exits_start_index = 0
		if vagas_reais_agora < 0:
			future_exits_start_index = abs(vagas_reais_agora)

		future_valid_exits = [d for d in saidas_futuras if d >= getdate(today())]

		if future_exits_start_index < len(future_valid_exits):
			availability_timeline.extend(future_valid_exits[future_exits_start_index:])

		# Assign to queue items
		queue_items = fila_by_ramo[ramo]

		for i, item in enumerate(queue_items):
			if item.associado:
				associado = frappe.db.get_value(
					"Novo Associado", item.associado, ["nome_completo", "data_de_nascimento"], as_dict=True
				)
				if associado:
					item.nome_completo = associado.nome_completo

					# Idade recalculada a cada carregamento da página
					item.idade = formatar_idade(associado.data_de_nascimento)

					responsavel_vinculo = frappe.get_all(
						"Responsavel Vinculo",
						filters={"beneficiario_novo_associado": item.associado},
						fields=["responsavel"],
						limit=1,
					)

					if responsavel_vinculo:
						responsavel_id = responsavel_vinculo[0].responsavel
						responsavel_nome = frappe.db.get_value("Responsavel", responsavel_id, "nome_completo")
						item.responsavel_nome = responsavel_nome
					else:
						item.responsavel_nome = "Responsável não encontrado"

					item.posicao = i + 1

					# Set prediction
					if i < len(availability_timeline):
						date_available = availability_timeline[i]
						if date_available <= getdate(today()):
							item.previsao = "Imediata"
						else:
							month_name = months_map[date_available.month - 1]
							item.previsao = f"{month_name}/{date_available.year}"
					else:
						item.previsao = "Sem previsão"

					kanban_data[ramo].append(item)

	# Para onde cada um volta ao ser chamado e as passagens anteriores pela fila: o dialog
	# mostra os dois. Uma consulta para todos os cards, não uma por card.
	nomes_na_fila = [card.associado for cards in kanban_data.values() for card in cards]
	retorno_por_associado = recepcao_fila.status_de_retorno_por_associado(nomes_na_fila)
	for cards in kanban_data.values():
		for card in cards:
			card.status_retorno = retorno_por_associado.get(card.associado, "")
	context.historico_fila_por_associado = recepcao_fila.historico_por_associado(nomes_na_fila)

	context.kanban_columns = ramos
	context.kanban_data = kanban_data
	# Números do cabeçalho de cada coluna e do dialog "Cálculo de Vagas" (include compartilhado).
	context.vagas_por_ramo = dados_do_dialog(ocupacao_por_ramo)
	context.ramo_variant_map = ramo_variant_map

	return context


@frappe.whitelist(methods=["POST"])
def chamar_associado(fila_id: str):
	"""Tira o jovem da fila e o devolve ao status em que estava ao entrar, etapas intactas."""
	return {"status": recepcao_fila.chamar(fila_id)}


@frappe.whitelist(methods=["POST"])
def reordenar_fila(ramo: str, ordem: str | list):
	"""Grava a ordem que a recepção montou arrastando os cards da coluna do ramo."""
	return {"ordem": recepcao_fila.reordenar(ramo, frappe.parse_json(ordem))}


@frappe.whitelist()
def registrar_desistencia(fila_id: str, motivo: str | None = None):
	if not fila_id:
		frappe.throw(_("ID da fila não fornecido"))

	fila_item = frappe.get_doc("Fila de Espera", fila_id)
	if not fila_item.associado:
		frappe.throw(_("Associado não encontrado na fila"))

	# Process withdrawal using the shared API
	processar_desistencia(fila_item.associado, motivo=motivo)

	# Ensure Fila de Espera is gone (processar_desistencia handles it, but just in case)
	if frappe.db.exists("Fila de Espera", fila_id):
		frappe.delete_doc("Fila de Espera", fila_id)

	return "Ok"
