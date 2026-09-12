import frappe
from frappe import _
from frappe.utils import add_months, getdate, today

from gris.api.portal_access import enrich_context
from gris.api.recepcao import formatar_idade, processar_desistencia
from gris.api.recepcao_vagas import calcular_vagas_por_ramo

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
	vagas_por_ramo = {}

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
		order_by="dt_inclusao_fila asc",
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

		# Chart Data: Next 12 months
		chart_labels = []
		chart_values = []

		current_date = getdate(today())
		start_of_month = current_date.replace(day=1)
		months_short = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

		vagas_base = limite - ativos - novos

		for i in range(12):
			future_month = add_months(start_of_month, i)
			month_idx = future_month.month - 1
			label = f"{months_short[month_idx]}/{str(future_month.year)[2:]}"
			chart_labels.append(label)

			next_month = add_months(future_month, 1)

			cumulative_exits = 0
			for d in saidas_futuras:
				d_date = getdate(d)
				if d_date < next_month:
					cumulative_exits += 1
			chart_values.append(vagas_base + cumulative_exits)

		vagas_por_ramo[ramo] = {
			"disponiveis": ocupacao.disponiveis,
			"limite": limite,
			"ativos": ativos,
			"novos": novos,
			"saindo": ocupacao.saindo,
			"chart_labels": chart_labels,
			"chart_values": chart_values,
		}

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

	context.kanban_columns = ramos
	context.kanban_data = kanban_data
	context.vagas_por_ramo = vagas_por_ramo
	context.ramo_variant_map = ramo_variant_map

	return context


@frappe.whitelist()
def chamar_associado(fila_id: str):
	if not fila_id:
		frappe.throw(_("ID da fila não fornecido"))

	fila_item = frappe.get_doc("Fila de Espera", fila_id)
	if not fila_item.associado:
		frappe.throw(_("Associado não encontrado na fila"))

	# Update Novo Associado status to 'Novo Contato' (restarting the flow)
	frappe.db.set_value("Novo Associado", fila_item.associado, "status", "Novo Contato")

	# Remove from Fila de Espera
	frappe.delete_doc("Fila de Espera", fila_id)

	return "Ok"


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
