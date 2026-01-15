import hashlib
import json
import re

import frappe
from frappe.utils import add_days, format_date, getdate

from gris.api.portal_access import enrich_context

STEPS_DEF = [
	{"field": "visita_agendada", "label": "Visita Agendada"},
	{"field": "primeira_visita_realizada", "label": "Primeira Visita Realizada"},
	{"field": "dados_para_registro_enviados", "label": "Dados Enviados"},
	{"field": "registro_criado_no_paxtu", "label": "Registro no Paxtu"},
	{"field": "registro_provisorio_pago", "label": "Registro Provisório Pago", "conditional": True},
	{
		"field": "registro_provisorio_efetivado",
		"label": "Registro Provisório Efetivado",
		"conditional": True,
	},
	{"field": "pesquisa_de_novos_associados_respondida", "label": "Pesquisa Respondida"},
	{"field": "ficha_medica_preenchida", "label": "Ficha Médica"},
	{"field": "id_escoteiros_criado", "label": "ID Escoteiros Criado"},
	{"field": "registro_definitivo_pago", "label": "Registro Definitivo Pago"},
	{"field": "registro_definitivo_efetivado", "label": "Registro Definitivo Efetivado"},
	{"field": "reuniao_de_acolhida_realizada", "label": "Reunião de Acolhida"},
]


def get_context(context):
	context.active_link = "/recepcao"
	enrich_context(context, "/recepcao")

	# Statuses as requested by the user
	statuses = [
		"Novo Contato",
		"Conversa Inicial",
		"Visita Agendada",
		"Aguardar Dados",
		"Fazer Registro",
		"Acompanhamento",
	]

	# Fetch configuration for intervals
	try:
		config = frappe.get_doc("Configuracoes de Recepcao").as_dict()
	except (frappe.DoesNotExistError, ImportError):
		config = {}

	# Map Novo Associado fields to Config fields
	field_interval_map = {
		"dados_para_registro_enviados": "dados_para_registro_enviados",
		"registro_criado_no_paxtu": "registro_criado_no_paxtu",
		"registro_provisorio_pago": "registro_provisorio_pago",
		"registro_provisorio_efetivado": "registro_provisorio_efetivado",
		"pesquisa_de_novos_associados_respondida": "pesquisa_de_novos_associados_respondida",
		"ficha_medica_preenchida": "ficha_medica_preenchida",
		"id_escoteiros_criado": "id_escoteiros_criado",
		"registro_definitivo_pago": "registro_definitivo_pago",
		"registro_definitivo_efetivado": "registro_definitivo_efetivado",
		"reuniao_de_acolhida_realizada": "reuniao_de_acolhida_realizada",
	}

	# Fields to fetch for Novo Associado
	fields_to_fetch = [
		"name",
		"nome_completo",
		"status",
		"ramo",
		"owner",
		"responsavel_recepcao",
		"tipo_de_registro",
		"visita_agendada",
		"primeira_visita_realizada",
	] + list(field_interval_map.keys())

	novos_associados = frappe.get_all(
		"Novo Associado",
		fields=fields_to_fetch,
		order_by="modified desc",
	)

	# Bulk Data Fetching
	names = [na.name for na in novos_associados]

	# Fetch Visits
	visits_map = {}
	if names:
		all_visits = frappe.get_all(
			"Agenda de Visitas",
			filters={"jovem": ["in", names]},
			fields=["jovem", "data_da_visita", "visita_confirmada"],
			order_by="data_da_visita desc",
		)
		# Process visits to map by jovem (taking the latest one because of order_by)
		for v in all_visits:
			if v.jovem not in visits_map:
				visits_map[v.jovem] = v

	# Fetch Responsavel Vinculo
	responsavel_map = {}
	if names:
		links = frappe.get_all(
			"Responsavel Vinculo",
			filters={"beneficiario_novo_associado": ["in", names]},
			fields=["beneficiario_novo_associado", "responsavel"],
		)

		# Collect Responsavel IDs to fetch names
		resp_ids = set(l.responsavel for l in links)
		resp_names_map = {}
		if resp_ids:
			resps = frappe.get_all(
				"Responsavel", filters={"name": ["in", list(resp_ids)]}, fields=["name", "nome_completo"]
			)
			resp_names_map = {r.name: r.nome_completo for r in resps}

		for l in links:
			# Just taking the first one found
			if l.beneficiario_novo_associado not in responsavel_map:
				responsavel_map[l.beneficiario_novo_associado] = resp_names_map.get(l.responsavel)

	# Fetch User Names
	user_names_map = {}
	user_ids = set(n.responsavel_recepcao for n in novos_associados if n.responsavel_recepcao)
	if user_ids:
		users = frappe.get_all("User", filters={"name": ["in", list(user_ids)]}, fields=["name", "full_name"])
		user_names_map = {u.name: (u.full_name or u.name) for u in users}

	# Map for Ramo CSS classes
	ramo_map = {
		"Filhotes": "filhotes",
		"Lobinho": "lobinho",
		"Escoteiro": "escoteiro",
		"Sênior": "senior",
		"Pioneiro": "pioneiro",
	}

	# Steps definition for infographic
	steps_def = STEPS_DEF

	# Group by status
	kanban_data = {status: [] for status in statuses}

	today = getdate()

	for associado in novos_associados:
		status_key = associado.status

		if status_key in kanban_data:
			# Get visit info from map
			visit_rec = visits_map.get(associado.name)

			# Use visit date if available as base, regardless of confirmation status
			# This ensures we have a base date for calculations
			base_date = visit_rec.data_da_visita if visit_rec else None

			# Process steps
			associado.steps = []
			is_definitivo = associado.tipo_de_registro == "Definitivo"

			current_calc_date = base_date

			for step in steps_def:
				if step.get("conditional") and is_definitivo:
					continue

				val = associado.get(step["field"])
				is_completed = bool(val)
				step_data = {
					"label": step["label"],
					"completed": is_completed,
					"field": step["field"],
				}

				# Calculate dates for pending steps
				if current_calc_date:
					config_field_name = field_interval_map.get(step["field"])
					if config_field_name:
						days_val = config.get(config_field_name) or 0
						try:
							days_int = int(days_val)
							current_calc_date = add_days(current_calc_date, days_int)
							# If not completed, show the estimated date
							if not is_completed:
								step_data["estimated_date"] = format_date(current_calc_date)
								# Check if overdue
								if current_calc_date < today:
									step_data["is_overdue"] = True
						except (ValueError, TypeError):
							pass

				associado.steps.append(step_data)

			associado.steps_json = json.dumps(associado.steps, default=str)

			# Get Responsavel Recepcao name
			if associado.responsavel_recepcao:
				associado.recepcao_name = user_names_map.get(associado.responsavel_recepcao, "Não atribuído")
			else:
				associado.recepcao_name = "Não atribuído"

			# Get Responsavel pelo Associado
			associado.responsavel_associado = responsavel_map.get(associado.name)

			# Visit info
			associado.visita_confirmada = bool(visit_rec.visita_confirmada) if visit_rec else False
			associado.visita_data = (
				format_date(visit_rec.data_da_visita) if visit_rec and visit_rec.data_da_visita else None
			)

			# Set ramo class
			associado.ramo_class = ramo_map.get(associado.ramo, "default")

			kanban_data[status_key].append(associado)

	context.kanban_columns = statuses
	context.kanban_data = kanban_data

	# Fetch users with role 'Recepcao'
	recepcao_role_users = frappe.get_all("Has Role", filters={"role": "Recepcao"}, fields=["parent"])
	user_names_list = [r.parent for r in recepcao_role_users]

	if user_names_list:
		context.recepcao_users = frappe.get_all(
			"User",
			filters={"name": ["in", user_names_list], "enabled": 1},
			fields=["name", "full_name"],
			order_by="full_name asc",
		)
	else:
		context.recepcao_users = []

	return context


@frappe.whitelist()
def confirmar_registro_paxtu(novo_associado_name):
	if not novo_associado_name:
		frappe.throw("Novo Associado não especificado.")

	frappe.db.set_value(
		"Novo Associado",
		novo_associado_name,
		{"registro_criado_no_paxtu": 1, "status": "Acompanhamento"},
	)

	return "Registro confirmado com sucesso."


@frappe.whitelist()
def update_step_status(novo_associado_name, field, value):
	if not novo_associado_name:
		frappe.throw("Novo Associado não especificado.")

	# Validate field against allowed steps
	allowed_fields = [s["field"] for s in STEPS_DEF]

	if field not in allowed_fields:
		frappe.throw("Campo inválido.")

	doc = frappe.get_doc("Novo Associado", novo_associado_name)
	doc.set(field, int(value))

	doc.save()

	return "Status atualizado com sucesso."


@frappe.whitelist()
def finalizar_processo_recepcao(novo_associado_name):
	if not novo_associado_name:
		frappe.throw("Novo Associado não especificado.")

	na_doc = frappe.get_doc("Novo Associado", novo_associado_name)

	# Find Associado by hashed CPF (as name)
	if not na_doc.cpf:
		frappe.throw("Novo Associado sem CPF. Não é possível vincular ao Associado.")

	cpf_clean = re.sub(r"\D", "", na_doc.cpf)
	associado_name = hashlib.md5(cpf_clean.encode("utf-8")).hexdigest()

	if not frappe.db.exists("Associado", associado_name):
		frappe.throw(
			f"Associado com name/hash {associado_name} (CPF {na_doc.cpf}) não encontrado. Certifique-se de que o registro foi criado."
		)

	# Update Responsavel Vinculo
	links = frappe.get_all("Responsavel Vinculo", filters={"beneficiario_novo_associado": na_doc.name})
	responsavel_ids = []

	for link in links:
		link_doc = frappe.get_doc("Responsavel Vinculo", link.name)
		link_doc.beneficiario_novo_associado = None
		link_doc.beneficiario_associado = associado_name
		link_doc.save(ignore_permissions=True)
		if link_doc.responsavel:
			responsavel_ids.append(link_doc.responsavel)

	# Anonymize Responsavel
	fields_to_keep = [
		"o_que_gosta_de_fazer_no_dia_a_dia",
		"habilidades",
		"nome_completo",
		"informacoes_pessoais_section",  # Keep section breaks to avoid UI issues
		"hobbies_e_interesses_section",
		"informacoes_profissionais_e_academicas_section",
		"endereco_e_dados_de_contato_section",
	]

	# Get all fields of Responsavel
	meta = frappe.get_meta("Responsavel")
	fields_to_clear = []
	for field in meta.fields:
		if field.fieldname not in fields_to_keep and field.fieldtype not in [
			"Section Break",
			"Column Break",
			"Tab Break",
			"Table MultiSelect",
		]:
			fields_to_clear.append(field.fieldname)

	for resp_id in set(responsavel_ids):
		resp_doc = frappe.get_doc("Responsavel", resp_id)
		for field in fields_to_clear:
			# Clear value
			resp_doc.set(field, None)
		resp_doc.save(ignore_permissions=True)

	# Delete Agenda de Visitas records linked to this Novo Associado
	frappe.db.delete("Agenda de Visitas", {"jovem": na_doc.name})

	# Delete Novo Associado
	frappe.delete_doc("Novo Associado", na_doc.name, ignore_permissions=True)

	return "Recepção finalizada com sucesso."
