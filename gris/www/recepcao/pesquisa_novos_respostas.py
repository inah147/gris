import frappe

from gris.api.portal_access import enrich_context


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.throw("Não autorizado", frappe.PermissionError)

	# Check permissions
	if "Recepcao" not in frappe.get_roles():
		frappe.throw("Acesso negado", frappe.PermissionError)

	context.sidebar_title = "Recepção"
	context.active_link = "/recepcao"
	enrich_context(context, "/recepcao")


@frappe.whitelist()
def get_surveys():
	if "Recepcao" not in frappe.get_roles():
		frappe.throw("Acesso negado")

	surveys = frappe.get_all(
		"Pesqusa de Novos Associados",
		fields=["name", "responsavel", "creation", "nps_recepcao", "data_resposta"],
		order_by="data_resposta desc",
	)

	for s in surveys:
		s.creation_formatted = frappe.utils.format_date(s.data_resposta or s.creation)
		# Fetch responsavel name if possible, or just use the ID if it's the name
		# Usually 'responsavel' field stores the name (ID) of the Responsavel doc.
		# Let's try to get the full name from the Responsavel doc
		resp_name = frappe.db.get_value("Responsavel", s.responsavel, "nome_completo")
		s.responsavel_nome = resp_name or s.responsavel

	return surveys


@frappe.whitelist()
def get_survey_details(survey_name):
	if "Recepcao" not in frappe.get_roles():
		frappe.throw("Acesso negado")

	survey_doc = frappe.get_doc("Pesqusa de Novos Associados", survey_name)
	survey = survey_doc.as_dict()

	# Add responsavel name
	survey["responsavel_nome"] = (
		frappe.db.get_value("Responsavel", survey_doc.responsavel, "nome_completo") or survey_doc.responsavel
	)

	# Get beneficiaries linked to this Responsavel
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": survey_doc.responsavel},
		fields=["beneficiario_novo_associado", "beneficiario_associado"],
	)

	beneficiarios = []
	for v in vinculos:
		if v.beneficiario_novo_associado:
			b = frappe.db.get_value(
				"Novo Associado", v.beneficiario_novo_associado, ["name", "nome_completo"], as_dict=True
			)
			if b:
				b.tipo = "Novo Associado"
				beneficiarios.append(b)
		if v.beneficiario_associado:
			b = frappe.db.get_value(
				"Associado", v.beneficiario_associado, ["name", "nome_completo"], as_dict=True
			)
			if b:
				b.tipo = "Associado"
				beneficiarios.append(b)

	return {"survey": survey, "beneficiarios": beneficiarios}


@frappe.whitelist()
def get_nps_chart_data(period="monthly"):
	if "Recepcao" not in frappe.get_roles():
		frappe.throw("Acesso negado")

	surveys = frappe.get_all(
		"Pesqusa de Novos Associados",
		fields=["nps_recepcao", "data_resposta", "creation"],
		order_by="data_resposta asc",
	)

	from collections import defaultdict

	from frappe.utils import add_months, format_date, getdate, nowdate

	data_by_period = defaultdict(lambda: {"promoters": 0, "detractors": 0, "total": 0})
	start_date = getdate(add_months(nowdate(), -6))

	for s in surveys:
		date = getdate(s.data_resposta or s.creation)
		if date < start_date:
			continue

		nps = int(s.nps_recepcao or 0)

		if period == "weekly":
			# Year-Week format
			key = f"{date.year}-{date.isocalendar()[1]:02d}"
			label = f"Semana {date.isocalendar()[1]}/{date.year}"
		else:
			# Year-Month format
			key = f"{date.year}-{date.month:02d}"
			label = format_date(date, "MM-yyyy")

		data_by_period[key]["total"] += 1
		if nps >= 9:
			data_by_period[key]["promoters"] += 1
		elif nps <= 6:
			data_by_period[key]["detractors"] += 1

		data_by_period[key]["label"] = label
		data_by_period[key]["sort_key"] = key

	# Calculate NPS
	chart_labels = []
	chart_values = []

	sorted_keys = sorted(data_by_period.keys())

	for key in sorted_keys:
		item = data_by_period[key]
		if item["total"] > 0:
			nps_score = ((item["promoters"] - item["detractors"]) / item["total"]) * 100
		else:
			nps_score = 0

		chart_labels.append(item["label"])
		chart_values.append(round(nps_score, 2))

	return {"labels": chart_labels, "datasets": [{"name": "NPS", "values": chart_values}]}
