import re

import frappe
from frappe.utils import add_days, cint, getdate, now, today

from gris.api.portal_access import enrich_context
from gris.api.recepcao_notificacoes import notificar_nova_manifestacao_no_grupo_recepcao

no_cache = 1


def _get_responsavel_name(user):
	if not user or user == "Guest":
		return None

	responsavel_name = frappe.db.get_value("Responsavel", {"email": user}, "name")
	if responsavel_name:
		return responsavel_name

	# Fallback para contas com login id@escoteiros associadas a um registro no doctype Associado
	associado_name = frappe.db.get_value("Associado", {"id_escoteiros": user}, "name")
	if not associado_name:
		return None

	associado_cpf_hash = frappe.db.get_value("Associado", associado_name, "cpf")
	if associado_cpf_hash and frappe.db.exists("Responsavel", associado_cpf_hash):
		return associado_cpf_hash

	# Último fallback: tentar via vínculo já existente do associado
	return frappe.db.get_value(
		"Responsavel Vinculo", {"beneficiario_associado": associado_name}, "responsavel"
	)


def _get_sections_by_ramos(ramos):
	valid_ramos = {ramo for ramo in (ramos or []) if ramo}
	if not valid_ramos:
		return set()

	rows = frappe.get_all(
		"Associado",
		filters={"ramo": ["in", list(valid_ramos)], "secao": ["is", "set"]},
		fields=["secao", "ramo"],
		distinct=True,
	)

	sections = {row.secao for row in rows if row.secao}
	sections.update(valid_ramos)
	return sections


def _is_date_available_for_ramo(ramo, date_value):
	if not ramo or not date_value:
		return False

	start_date = getdate(today())
	end_date = add_days(start_date, 60)
	target_date = getdate(date_value)

	if target_date < start_date or target_date > end_date or target_date.weekday() != 5:
		return False

	target_sections = _get_sections_by_ramos({ramo})
	if not target_sections:
		return True

	activities = frappe.get_all(
		"Calendario",
		filters={"inicio": ["<=", target_date], "termino": [">=", target_date]},
		fields=["secao", "abertura_geral"],
	)

	for act in activities:
		if cint(act.abertura_geral):
			continue
		if act.secao and act.secao in target_sections:
			return False

	return True


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/responsavel/beneficiarios"
		raise frappe.Redirect

	user = frappe.session.user
	responsavel_name = _get_responsavel_name(user)

	if not responsavel_name:
		context.beneficiarios_registrados = []
		context.beneficiarios_integracao = []
		return context

	# Get links
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": responsavel_name},
		fields=["beneficiario_associado", "beneficiario_novo_associado"],
	)

	associado_names = [v.beneficiario_associado for v in vinculos if v.beneficiario_associado]
	novo_associado_names = [v.beneficiario_novo_associado for v in vinculos if v.beneficiario_novo_associado]

	# Fetch Configuration
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

	# Fetch Associados
	beneficiarios_registrados = []
	if associado_names:
		beneficiarios_registrados = frappe.get_all(
			"Associado",
			filters={"name": ["in", associado_names]},
			fields=["name", "nome_completo", "registro", "status", "validade_registro", "ramo"],
		)

		for b in beneficiarios_registrados:
			if b.validade_registro:
				b.validade_registro = frappe.format_value(b.validade_registro, {"fieldtype": "Date"})
			b.status_class = _status_badge_class(b.status)

	# Fetch Novo Associados
	beneficiarios_integracao = []
	show_schedule_button = False

	if novo_associado_names:
		fields_to_fetch = [
			"name",
			"nome_completo",
			"ramo",
			"status",
			"tipo_de_registro",
			"visita_agendada",
			"primeira_visita_realizada",
			*field_interval_map.keys(),
		]

		beneficiarios_integracao = frappe.get_all(
			"Novo Associado", filters={"name": ["in", novo_associado_names]}, fields=fields_to_fetch
		)

		# Fetch all visits to map base dates
		visits_map = {}
		all_visits = frappe.get_all(
			"Agenda de Visitas",
			filters={"jovem": ["in", novo_associado_names]},
			fields=["jovem", "data_da_visita"],
			order_by="data_da_visita desc",
		)
		for v in all_visits:
			if v.jovem not in visits_map:
				visits_map[v.jovem] = v.data_da_visita

		steps_def = [
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

		for b in beneficiarios_integracao:
			if not b.visita_agendada:
				show_schedule_button = True

			b.steps = []
			is_definitivo = b.tipo_de_registro == "Definitivo"
			stop_adding = False

			current_calc_date = visits_map.get(b.name)

			for step in steps_def:
				if stop_adding:
					break

				if step.get("conditional") and is_definitivo:
					continue

				is_completed = bool(b.get(step["field"]))
				step_data = {"label": step["label"], "completed": is_completed, "field": step["field"]}

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
								step_data["estimated_date"] = frappe.utils.format_date(current_calc_date)
								if current_calc_date < getdate():
									step_data["is_overdue"] = True
						except (ValueError, TypeError):
							pass

				b.steps.append(step_data)

				if step["field"] == "dados_para_registro_enviados" and not is_completed:
					stop_adding = True

	# Check for existing scheduled visit
	visit_info = None
	if novo_associado_names:
		# Check if any beneficiary is in 'Visita Agendada' status
		has_scheduled_status = any(b.status == "Visita Agendada" for b in beneficiarios_integracao)

		if has_scheduled_status:
			agenda = frappe.get_all(
				"Agenda de Visitas",
				filters={"jovem": ["in", novo_associado_names], "data_da_visita": [">=", today()]},
				fields=["name", "data_da_visita"],
				order_by="data_da_visita asc",
				limit=1,
			)
			if agenda:
				visit_info = agenda[0]
				visit_info.formatted_date = frappe.format_value(
					visit_info.data_da_visita, {"fieldtype": "Date"}
				)

	# CPF do responsável para validação client-side (não exibido, apenas para comparação)
	responsavel_cpf = frappe.db.get_value("Responsavel", responsavel_name, "cpf") or ""

	context.visit_info = visit_info
	context.beneficiarios_registrados = beneficiarios_registrados
	context.beneficiarios_integracao = beneficiarios_integracao
	context.show_schedule_button = show_schedule_button and not visit_info
	context.responsavel_cpf = responsavel_cpf

	context.sidebar_title = "Painel do Responsável"
	context.active_link = "/responsavel/beneficiarios"
	enrich_context(context, "/responsavel/beneficiarios")

	return context


@frappe.whitelist()
def get_available_visit_dates():
	user = frappe.session.user
	responsavel_name = _get_responsavel_name(user)
	if not responsavel_name:
		return []

	# Get beneficiaries in integration
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": responsavel_name},
		fields=["beneficiario_novo_associado"],
	)
	novo_associado_names = [v.beneficiario_novo_associado for v in vinculos if v.beneficiario_novo_associado]

	if not novo_associado_names:
		return []

	beneficiaries = frappe.get_all(
		"Novo Associado",
		filters={"name": ["in", novo_associado_names], "visita_agendada": 0},
		fields=["ramo"],
	)
	target_ramos = {row.ramo for row in beneficiaries if row.ramo}
	target_sections = _get_sections_by_ramos(target_ramos)

	start_date = getdate(today())
	end_date = add_days(start_date, 60)

	# Generate Saturdays
	saturdays = []
	current = start_date
	while current <= end_date:
		if current.weekday() == 5:  # Saturday
			saturdays.append(current)
		current = add_days(current, 1)

	if not saturdays:
		return []

	# Check calendar for activities
	# We want days with NO activity.
	# Fetch all activities in range
	activities = frappe.get_all(
		"Calendario",
		filters={"inicio": ["<=", end_date], "termino": [">=", start_date]},
		fields=["inicio", "termino", "secao", "abertura_geral"],
	)

	blocked_dates = set()
	for act in activities:
		if cint(act.abertura_geral):
			continue

		if not target_sections:
			continue

		if not act.secao or act.secao not in target_sections:
			continue

		# Check which saturdays fall within this activity
		act_start = getdate(act.inicio)
		act_end = getdate(act.termino)

		for sat in saturdays:
			if act_start <= sat <= act_end:
				blocked_dates.add(sat)

	available_dates = [
		{
			"value": sat.strftime("%Y-%m-%d"),
			"label": frappe.format_value(sat, {"fieldtype": "Date"}),
		}
		for sat in saturdays
		if sat not in blocked_dates
	]

	return available_dates


@frappe.whitelist()
def schedule_visit(date):
	user = frappe.session.user
	responsavel_name = _get_responsavel_name(user)
	if not responsavel_name:
		frappe.throw("Responsável não encontrado.")

	# Get beneficiaries in integration who need visit
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": responsavel_name},
		fields=["beneficiario_novo_associado"],
	)
	novo_associado_names = [v.beneficiario_novo_associado for v in vinculos if v.beneficiario_novo_associado]

	if not novo_associado_names:
		frappe.throw("Nenhum beneficiário em integração encontrado.")

	beneficiaries = frappe.get_all(
		"Novo Associado",
		filters={"name": ["in", novo_associado_names], "visita_agendada": 0},
		fields=["name", "ramo"],
	)

	if not beneficiaries:
		frappe.throw("Todos os beneficiários já possuem visita agendada.")

	for b in beneficiaries:
		if not _is_date_available_for_ramo(b.ramo, date):
			frappe.throw("A data selecionada não está disponível para o ramo do beneficiário.")

	# Create Agenda de Visitas for each
	for b in beneficiaries:
		doc = frappe.get_doc(
			{
				"doctype": "Agenda de Visitas",
				"jovem": b.name,
				"data_da_visita": date,
				"ramo": b.ramo,
				"visita_confirmada": 0,
			}
		)
		doc.insert(ignore_permissions=True)

		# Update Novo Associado
		frappe.db.set_value("Novo Associado", b.name, {"visita_agendada": 1, "status": "Visita Agendada"})

	return "Visita agendada com sucesso."


@frappe.whitelist()
def cancel_visit():
	user = frappe.session.user
	responsavel_name = _get_responsavel_name(user)
	if not responsavel_name:
		frappe.throw("Responsável não encontrado.")

	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": responsavel_name},
		fields=["beneficiario_novo_associado"],
	)
	novo_associado_names = [v.beneficiario_novo_associado for v in vinculos if v.beneficiario_novo_associado]

	if not novo_associado_names:
		return

	# Find visits
	visits = frappe.get_all(
		"Agenda de Visitas",
		filters={"jovem": ["in", novo_associado_names], "data_da_visita": [">=", today()]},
	)

	for v in visits:
		frappe.delete_doc("Agenda de Visitas", v.name, ignore_permissions=True)

	# Reset flag on Novo Associado
	for name in novo_associado_names:
		frappe.db.set_value("Novo Associado", name, "visita_agendada", 0)

	return "Agendamento cancelado."


@frappe.whitelist()
def reschedule_visit(date):
	cancel_visit()
	return schedule_visit(date)


def _status_badge_class(status):
	status = (status or "").lower()
	if status in {"válido", "valido"}:
		return "g-badge--success"
	if status == "vencido":
		return "g-badge--warning"
	return "g-badge--secondary"


@frappe.whitelist()
def adicionar_beneficiario(nome_jovem, cpf_jovem, data_nascimento_jovem):
	"""Adiciona um novo beneficiário (jovem) vinculado ao responsável logado.

	Cria Novo Associado com status 'Conversa Inicial', registra auditoria
	em Resposta Manifestacao de Interesse e cria o vínculo.
	"""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Acesso negado.", frappe.PermissionError)

	if "Responsavel" not in frappe.get_roles(user):
		frappe.throw("Você não tem permissão para esta operação.", frappe.PermissionError)

	responsavel_name = _get_responsavel_name(user)
	if not responsavel_name:
		frappe.throw("Responsável não encontrado para o usuário logado.")

	# Validar campos obrigatórios
	nome_jovem = (nome_jovem or "").strip()
	cpf_jovem = (cpf_jovem or "").strip()
	data_nascimento_jovem = (data_nascimento_jovem or "").strip()

	if not nome_jovem or not cpf_jovem or not data_nascimento_jovem:
		frappe.throw("Todos os campos são obrigatórios: nome, CPF e data de nascimento.")

	# Validar formato do nome (somente letras, espaços e acentos)
	if not re.match(r"^[A-Za-zÀ-ÿ\s]+$", nome_jovem):
		frappe.throw("Nome do jovem deve conter apenas letras e espaços.")

	# Normalizar CPF (remover formatação)
	cpf_limpo = re.sub(r"\D", "", cpf_jovem)
	if len(cpf_limpo) != 11:
		frappe.throw("CPF do jovem deve conter 11 dígitos.")

	# Validar data de nascimento (deve ser anterior a hoje)
	try:
		data_nasc = getdate(data_nascimento_jovem)
	except Exception:
		frappe.throw("Data de nascimento inválida.")

	if data_nasc >= getdate(today()):
		frappe.throw("Data de nascimento deve ser anterior a hoje.")

	# Buscar dados do responsável
	responsavel_doc = frappe.get_doc("Responsavel", responsavel_name)

	# CPF do jovem não pode ser igual ao do responsável
	cpf_responsavel_limpo = re.sub(r"\D", "", responsavel_doc.cpf or "")
	if cpf_limpo == cpf_responsavel_limpo:
		frappe.throw("O CPF do jovem não pode ser o mesmo do responsável.")

	# Verificar se já existe Novo Associado com o mesmo CPF
	existing_novo_associado = frappe.db.exists("Novo Associado", {"cpf": cpf_jovem})
	if existing_novo_associado:
		frappe.throw(
			"Já existe um jovem cadastrado com este CPF. Verifique os dados ou entre em contato com o grupo."
		)

	savepoint_name = f"add_beneficiario_{frappe.generate_hash(length=8)}"
	frappe.db.savepoint(savepoint_name)

	try:
		# 1. Registrar auditoria em Resposta Manifestacao de Interesse
		frappe.get_doc(
			{
				"doctype": "Resposta Manifestacao de Interesse",
				"nome_do_responsavel": responsavel_doc.nome_completo,
				"email_do_responsavel": responsavel_doc.email,
				"celular_do_responsavel": responsavel_doc.celular,
				"cpf_do_responsavel": responsavel_doc.cpf,
				"nome_do_jovem": nome_jovem,
				"data_de_nascimento_do_jovem": data_nascimento_jovem,
				"cpf_do_jovem": cpf_jovem,
				"data_e_horario_de_resposta": now(),
				"dados_confirmados": 1,
				"aceite_lgpd": 1,
			}
		).insert(ignore_permissions=True)

		# 2. Criar Novo Associado com status "Conversa Inicial"
		novo_associado_doc = frappe.get_doc(
			{
				"doctype": "Novo Associado",
				"nome_completo": nome_jovem,
				"data_de_nascimento": data_nascimento_jovem,
				"cpf": cpf_jovem,
				"status": "Conversa Inicial",
			}
		)
		novo_associado_doc.insert(ignore_permissions=True)

		# 3. Criar Responsavel Vinculo
		frappe.get_doc(
			{
				"doctype": "Responsavel Vinculo",
				"responsavel": responsavel_name,
				"beneficiario_novo_associado": novo_associado_doc.name,
			}
		).insert(ignore_permissions=True)

		notificar_nova_manifestacao_no_grupo_recepcao(
			nome_jovem=nome_jovem,
			nome_responsavel=responsavel_doc.nome_completo or responsavel_name,
			data_nascimento_jovem=data_nascimento_jovem,
			contexto="adicionar_beneficiario",
		)

		return {"ok": True, "message": "Beneficiário adicionado com sucesso!"}

	except Exception:
		frappe.db.rollback(save_point=savepoint_name)
		frappe.log_error("Erro ao adicionar beneficiário")
		frappe.throw("Ocorreu um erro ao adicionar o beneficiário. Tente novamente.")
