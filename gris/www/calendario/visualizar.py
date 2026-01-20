import unicodedata
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import format_date, getdate, today

from gris.api.portal_access import enrich_context


def get_context(context):
	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Visualizador Calendario", "Gestor Calendario", "System Manager"]):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	context.can_simulate = "Gestor Calendario" in roles or "System Manager" in roles

	try:
		year = int(frappe.form_dict.year)
	except (ValueError, TypeError):
		year = getdate(today()).year

	context.year = year

	# Get available years with activities
	years_data = frappe.db.sql(
		"""
		SELECT DISTINCT YEAR(inicio) as year FROM `tabCalendario`
		UNION
		SELECT DISTINCT YEAR(termino) as year FROM `tabCalendario`
		ORDER BY year DESC
	""",
		as_dict=True,
	)

	available_years = sorted(list(set([int(y.year) for y in years_data if y.year])), reverse=True)

	# Ensure current year is in the list if it's the default view, or if the user selected it
	if year not in available_years:
		available_years.append(year)
		available_years.sort(reverse=True)

	context.available_years = available_years

	# Fetch holidays for the year
	feriados = frappe.get_all(
		"Feriados",
		filters={"data": ["between", [f"{year}-01-01", f"{year}-12-31"]]},
		fields=["nome", "data", "tipo", "descricao"],
	)
	feriados_map = {getdate(f.data): f for f in feriados}

	# Fetch all calendar events for the year
	# We fetch a bit more to cover year boundaries if needed, but strict year filter is fine for "dias do ano"
	start_date = f"{year}-01-01"
	end_date = f"{year}-12-31"

	# Fetch events that overlap with the year
	events = frappe.get_all(
		"Calendario",
		filters={"inicio": ["<=", f"{year}-12-31 23:59:59"], "termino": [">=", f"{year}-01-01 00:00:00"]},
		fields=["name", "atividade", "inicio", "termino", "secao", "local", "nivel", "sem_atividade"],
		order_by="inicio asc",
	)

	sections = set()
	events_by_date_section = {}

	for event in events:
		section = event.secao if event.secao else "Diretoria"
		sections.add(section)

		event_start = getdate(event.inicio)
		event_end = getdate(event.termino)

		# Clamp dates to current year for display
		current = max(event_start, date(year, 1, 1))
		end = min(event_end, date(year, 12, 31))

		while current <= end:
			date_str = current.strftime("%Y-%m-%d")
			key = (date_str, section)
			if key not in events_by_date_section:
				events_by_date_section[key] = []

			# Create a copy for display logic
			event_display = event.copy()
			event_display["is_start"] = current == event_start
			event_display["is_end"] = current == event_end

			# Helper fields for template data attributes
			event_display["inicio_fmt"] = format_date(event.inicio)
			event_display["termino_fmt"] = format_date(event.termino)
			event_display["hora_inicio"] = event.inicio.strftime("%H:%M") if event.inicio else ""
			event_display["hora_termino"] = event.termino.strftime("%H:%M") if event.termino else ""

			events_by_date_section[key].append(event_display)
			current += timedelta(days=1)

	# Fetch Section -> Ramo mapping for sorting
	associados = frappe.get_all("Associado", fields=["secao", "ramo"], distinct=True)
	section_ramo_map = {d.secao: d.ramo for d in associados if d.secao}

	ramo_order = ["Diretoria", "Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"]

	def get_section_sort_key(section_name):
		if section_name == "Diretoria":
			return (0, section_name)

		ramo = section_ramo_map.get(section_name)
		if ramo in ramo_order:
			return (ramo_order.index(ramo), section_name)

		# If ramo not in order or not found, put at the end
		return (len(ramo_order), section_name)

	sorted_sections = sorted(list(sections), key=get_section_sort_key)

	if not sorted_sections:
		# If no events, at least show Diretoria? Or just empty.
		sorted_sections = ["Diretoria"]

	context.sections = sorted_sections

	# Generate CSS classes for sections based on Ramo
	context.section_classes = {}
	for section in sorted_sections:
		ramo = section_ramo_map.get(section, "default")
		# Normalize ramo to be a valid css class suffix
		normalized = "".join(
			c for c in unicodedata.normalize("NFD", ramo) if unicodedata.category(c) != "Mn"
		).lower()
		context.section_classes[section] = normalized

	calendar_rows = []
	current_date = date(year, 1, 1)
	end_date_obj = date(year, 12, 31)

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
			"holiday": feriados_map.get(current_date),
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

	# Sidebar and context enrichment
	context.active_link = "/calendario/visualizar"
	enrich_context(context, "/calendario/visualizar")
