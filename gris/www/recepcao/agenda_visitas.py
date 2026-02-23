import unicodedata
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, format_date, getdate, today

from gris.api.portal_access import enrich_context, user_has_access


def get_context(context):
	# Disable cache to always show fresh data
	context.no_cache = 1

	# Permission check
	if not user_has_access("/recepcao"):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	try:
		year = int(frappe.form_dict.year)
	except (ValueError, TypeError):
		year = getdate(today()).year

	context.year = year

	# Available years (based on visits or calendar)
	years_data = frappe.db.sql(
		"""
		SELECT DISTINCT YEAR(data_da_visita) as year FROM `tabAgenda de Visitas`
		UNION
		SELECT DISTINCT YEAR(inicio) as year FROM `tabCalendario`
		ORDER BY year DESC
	""",
		as_dict=True,
	)

	available_years = sorted(list(set([int(y.year) for y in years_data if y.year])), reverse=True)

	if year not in available_years:
		available_years.append(year)
		available_years.sort(reverse=True)

	context.available_years = available_years

	# Fixed sections for this view
	sorted_sections = ["Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"]
	context.sections = sorted_sections

	# Calculate date range: Nov 1st (Year-1) to Feb 28/29 (Year+1)
	start_date = date(year - 1, 11, 1)

	# If viewing current year, limit start date to 2 months ago
	current_today = getdate(today())
	if year == current_today.year:
		limit_date = getdate(add_days(current_today, -60))
		if limit_date > start_date:
			start_date = limit_date

	# End date is last day of Feb next year.
	# We get March 1st and subtract 1 day.
	end_date = date(year + 1, 3, 1) - timedelta(days=1)

	# Fetch Visits
	visits = frappe.get_all(
		"Agenda de Visitas",
		filters={"data_da_visita": ["between", [start_date, end_date]]},
		fields=[
			"name",
			"jovem",
			"jovem.nome_completo as nome_da_crianca",
			"jovem.data_de_nascimento as data_de_nascimento",
			"data_da_visita",
			"ramo",
			"visita_confirmada",
		],
	)

	# Fetch Calendar Events (Unavailability)
	calendar_events = frappe.get_all(
		"Calendario",
		filters={"inicio": ["<=", end_date], "termino": [">=", start_date]},
		fields=["name", "atividade", "inicio", "termino", "secao"],
	)

	events_by_date_section = {}

	# Process Visits
	for visit in visits:
		if not visit.ramo or visit.ramo not in sorted_sections:
			continue

		visit_date = getdate(visit.data_da_visita)
		date_str = visit_date.strftime("%Y-%m-%d")
		key = (date_str, visit.ramo)

		if key not in events_by_date_section:
			events_by_date_section[key] = []

		# Calculate Age
		age_str = ""
		if visit.data_de_nascimento:
			dob = getdate(visit.data_de_nascimento)
			# Simple age calc
			years = visit_date.year - dob.year - ((visit_date.month, visit_date.day) < (dob.month, dob.day))
			months = (visit_date.year - dob.year) * 12 + visit_date.month - dob.month
			months = months % 12
			age_str = f"{years}a {months}m"

		events_by_date_section[key].append(
			{
				"type": "visit",
				"title": visit.nome_da_crianca,
				"subtitle": age_str,
				"id": visit.name,
				"jovem": visit.jovem,
				"confirmed": visit.visita_confirmada,
				"is_start": True,  # Visits are single day usually
				"is_end": True,
			}
		)

	# Process Calendar Events (as unavailable)
	for event in calendar_events:
		section = event.secao
		if not section:
			# If no section, maybe applies to all? For now, ignore or map to Diretoria (which isn't in our list)
			# If the user wants to see unavailability for specific ramos, we check if section is in our list.
			# If section is "Diretoria" or something else, maybe it doesn't block visits?
			# Let's assume if section is in our list, it blocks.
			continue

		if section not in sorted_sections:
			continue

		event_start = getdate(event.inicio)
		event_end = getdate(event.termino)

		current = max(event_start, start_date)
		end = min(event_end, end_date)

		while current <= end:
			date_str = current.strftime("%Y-%m-%d")
			key = (date_str, section)
			if key not in events_by_date_section:
				events_by_date_section[key] = []

			events_by_date_section[key].append(
				{
					"type": "unavailable",
					"title": "Indisponível",  # Or event.atividade
					"subtitle": event.atividade,
					"id": event.name,
					"is_start": current == event_start,
					"is_end": current == event_end,
				}
			)
			current += timedelta(days=1)

	# Build Calendar Rows
	calendar_rows = []
	current_date = start_date
	end_date_obj = end_date

	months = {
		1: "Jan",
		2: "Fev",
		3: "Mar",
		4: "Abr",
		5: "Mai",
		6: "Jun",
		7: "Jul",
		8: "Ago",
		9: "Set",
		10: "Out",
		11: "Nov",
		12: "Dez",
	}
	months_full = {
		1: "Janeiro",
		2: "Fevereiro",
		3: "Março",
		4: "Abril",
		5: "Maio",
		6: "Junho",
		7: "Julho",
		8: "Agosto",
		9: "Setembro",
		10: "Outubro",
		11: "Novembro",
		12: "Dezembro",
	}
	weekdays = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

	last_month = None
	while current_date <= end_date_obj:
		date_str = current_date.strftime("%Y-%m-%d")

		is_new_month = False
		if last_month != current_date.month:
			is_new_month = True
			last_month = current_date.month

		row = {
			"date_str": date_str,
			"date_obj": current_date,
			"day": current_date.day,
			"month": months[current_date.month],
			"month_full": months_full[current_date.month],
			"month_num": f"{current_date.month:02d}",
			"weekday": weekdays[current_date.weekday()],
			"is_weekend": current_date.weekday() >= 5,
			"is_new_month": is_new_month,
			"activities": {},
		}

		has_activity = False
		for section in sorted_sections:
			key = (date_str, section)
			evts = events_by_date_section.get(key, [])
			row["activities"][section] = evts
			if evts:
				has_activity = True

		row["has_activity"] = has_activity
		calendar_rows.append(row)
		current_date += timedelta(days=1)

	context.calendar_rows = calendar_rows

	# Sidebar setup
	context.active_link = "/recepcao/agenda_visitas"
	enrich_context(context, "/recepcao")

	return context


@frappe.whitelist()
def confirm_visit(visit_name):
	frappe.db.set_value("Agenda de Visitas", visit_name, "visita_confirmada", 1)


@frappe.whitelist()
def unconfirm_visit(visit_name):
	frappe.db.set_value("Agenda de Visitas", visit_name, "visita_confirmada", 0)


@frappe.whitelist()
def cancel_visit(visit_name):
	# Get visit to find the associate
	visit = frappe.get_doc("Agenda de Visitas", visit_name)
	associate_name = visit.jovem

	# Delete the visit
	frappe.delete_doc("Agenda de Visitas", visit_name)

	# Update associate status
	if associate_name:
		frappe.db.set_value("Novo Associado", associate_name, "visita_agendada", 0)


@frappe.whitelist()
def reschedule_visit(visit_name, new_date):
	frappe.db.set_value("Agenda de Visitas", visit_name, "data_da_visita", new_date)


def _get_available_dates(ramo):
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

	# Check calendar for activities that would BLOCK the visit
	# We check for activities of the specific Ramo or Global (no section)
	activities = frappe.get_all(
		"Calendario",
		filters={
			"inicio": ["<=", end_date],
			"termino": [">=", start_date],
		},
		fields=["inicio", "termino", "secao"],
	)

	blocked_dates = set()
	for act in activities:
		# If activity is for another section, it doesn't block us
		if act.secao and act.secao != ramo:
			continue

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
def get_available_dates_for_ramo(ramo):
	return _get_available_dates(ramo)


@frappe.whitelist()
def get_available_visit_dates_for_reschedule(visit_name):
	visit = frappe.get_doc("Agenda de Visitas", visit_name)
	if not visit:
		return []

	ramo = visit.ramo
	if not ramo:
		# Fallback if ramo is missing on visit, try to get from Jovem
		jovem_ramo = frappe.db.get_value("Novo Associado", visit.jovem, "ramo")
		ramo = jovem_ramo

	if not ramo:
		return []

	return _get_available_dates(ramo)


@frappe.whitelist()
def get_associates_for_scheduling():
	return frappe.get_all(
		"Novo Associado",
		filters={"visita_agendada": 0, "status": ["!=", "Desistência"]},
		fields=["name", "nome_completo", "ramo", "data_de_nascimento"],
	)


@frappe.whitelist()
def schedule_visit(associate, date):
	if not user_has_access("/recepcao"):
		frappe.throw("Sem permissão", frappe.PermissionError)

	# Get associate details for Ramo
	associate_doc = frappe.get_doc("Novo Associado", associate)

	# Create Visit
	visit = frappe.get_doc(
		{
			"doctype": "Agenda de Visitas",
			"jovem": associate,
			"data_da_visita": date,
			"ramo": associate_doc.ramo,
			"visita_confirmada": 0,
		}
	)
	visit.insert()

	# Update Associate
	associate_doc.visita_agendada = 1
	associate_doc.status = "Visita Agendada"
	associate_doc.save()

	return visit.name
