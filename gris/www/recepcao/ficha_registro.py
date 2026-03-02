import frappe
from frappe import _
from frappe.utils import add_days, cint, format_date, format_datetime, get_fullname, getdate, strip_html

from gris.api.portal_access import enrich_context

no_cache = 1


def get_context(context):
	# Ensure user is logged in (or handle permissions as needed)
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login"
		raise frappe.Redirect

	context.active_link = "/recepcao"
	enrich_context(context, "/recepcao/ficha_registro")

	name = frappe.form_dict.get("name")

	if not name:
		context.not_found = True
		context.missing_reason = "Parâmetro 'name' não informado."
		return context

	try:
		# Fetch Novo Associado
		doc = frappe.get_doc("Novo Associado", name)
	except frappe.DoesNotExistError:
		context.not_found = True
		context.missing_reason = "Novo Associado não encontrado."
		return context

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

	context.doc = doc
	context.title = doc.nome_completo

	# Fetch Responsibles via Responsavel Vinculo
	vinculos = frappe.get_all(
		"Responsavel Vinculo", filters={"beneficiario_novo_associado": name}, fields=["*"]
	)

	responsaveis = []
	context.guarda_unilateral = cint(vinculos[0].guarda_unilateral) if vinculos else 0
	for v in vinculos:
		if v.responsavel:
			resp_doc = frappe.get_doc("Responsavel", v.responsavel)
			responsaveis.append({"vinculo": v, "doc": resp_doc})

	responsaveis.sort(key=lambda x: (x["doc"].nome_completo or ""))
	context.responsaveis = responsaveis

	# Flow steps for infographic
	flow_steps = [
		{"field": "visita_agendada", "label": "Visita Agendada"},
		{"field": "primeira_visita_realizada", "label": "Primeira Visita"},
		{"field": "dados_para_registro_enviados", "label": "Dados Enviados"},
		{"field": "registro_criado_no_paxtu", "label": "Registro Paxtu"},
		{"field": "registro_provisorio_pago", "label": "Prov. Pago"},
		{"field": "registro_provisorio_efetivado", "label": "Prov. Efetivado"},
		{"field": "pesquisa_de_novos_associados_respondida", "label": "Pesquisa Respondida"},
		{"field": "ficha_medica_preenchida", "label": "Ficha Médica"},
		{"field": "id_escoteiros_criado", "label": "ID Criado"},
		{"field": "registro_definitivo_pago", "label": "Def. Pago"},
		{"field": "registro_definitivo_efetivado", "label": "Def. Efetivado"},
		{"field": "reuniao_de_acolhida_realizada", "label": "Acolhida"},
	]

	# Filter steps based on logic
	final_steps = []
	dados_enviados = bool(doc.get("dados_para_registro_enviados"))

	if not dados_enviados:
		final_steps = flow_steps[:4]
	elif doc.get("tipo_de_registro") == "Definitivo":
		final_steps = [
			s
			for s in flow_steps
			if s["field"] not in ["registro_provisorio_pago", "registro_provisorio_efetivado"]
		]
	else:
		final_steps = flow_steps

	# Process steps state
	steps_data = []

	# Initial date calculation base
	# Try to find a visit date
	visit_date = None
	visit_rec = frappe.get_all(
		"Agenda de Visitas",
		filters={"jovem": doc.name},
		fields=["data_da_visita"],
		order_by="data_da_visita desc",
		limit=1,
	)
	if visit_rec:
		visit_date = visit_rec[0].data_da_visita

	current_calc_date = visit_date
	today = getdate()

	for step in final_steps:
		is_done = bool(doc.get(step["field"]))
		step_info = {"label": step["label"], "done": is_done, "field": step["field"]}

		# Calculate dates for pending steps
		if current_calc_date:
			config_field_name = field_interval_map.get(step["field"])
			if config_field_name:
				days_val = config.get(config_field_name) or 0
				try:
					days_int = int(days_val)
					current_calc_date = add_days(current_calc_date, days_int)
					# If not completed, show the estimated date
					if not is_done:
						step_info["estimated_date"] = format_date(current_calc_date)
						# Check if overdue
						if current_calc_date < today:
							step_info["is_overdue"] = True
				except (ValueError, TypeError):
					pass

		steps_data.append(step_info)

	context.flow_steps = steps_data

	# Comentários internos (usando Comment)
	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Novo Associado",
			"reference_name": name,
			"comment_type": "Comment",
		},
		fields=["name", "content", "owner", "creation"],
		order_by="creation desc",
		limit=50,
	)

	context.comments = [
		{
			"name": c.name,
			"content_text": strip_html((c.content or "").replace("</p>", "\n").replace("<br>", "\n")),
			"owner": c.owner,
			"owner_fullname": get_fullname(c.owner),
			"creation": format_datetime(c.creation, "dd/MM/yyyy HH:mm"),
		}
		for c in comments
	]
	context.comments_count = len(comments)
	context.can_add_comments = doc.has_permission("write")
	context.current_user = frappe.session.user

	return context
