import base64
import json
import mimetypes
import unicodedata
from datetime import date, datetime, timedelta

import frappe
from frappe import _
from frappe.utils import format_date, getdate, today
from frappe.utils.pdf import get_pdf

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


@frappe.whitelist()
def export_calendar(year=None, month=None, show_empty_days=1, sections=None):
	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Visualizador Calendario", "Gestor Calendario", "System Manager"]):
		frappe.throw("Você não tem permissão para acessar esta funcionalidade.", frappe.PermissionError)

	if not year:
		year = getdate(today()).year
	else:
		year = int(year)

	if sections and isinstance(sections, str):
		try:
			sections = json.loads(sections)
		except:
			sections = []

	show_empty_days = int(show_empty_days)

	# Fetch UEL Info
	uel_name = "Grupo Escoteiro"
	uel_type = ""
	uel_logo = None
	try:
		uel_settings = frappe.get_single("Definicao da UEL")
		uel_name = uel_settings.nome_da_uel or uel_name
		uel_type = uel_settings.tipo_uel or "Grupo Escoteiro"
		if uel_settings.logo:
			file_path = frappe.utils.file_manager.get_file_path(uel_settings.logo)
			mime_type = mimetypes.guess_type(file_path)[0] or "image/png"
			with open(file_path, "rb") as f:
				encoded_string = base64.b64encode(f.read()).decode()
				uel_logo = f"data:{mime_type};base64,{encoded_string}"
	except Exception:
		pass

	# Fetch Section -> Ramo mapping and Class Generation
	associados = frappe.get_all("Associado", fields=["secao", "ramo"], distinct=True)
	section_ramo_map = {d.secao: d.ramo for d in associados if d.secao}

	# Generate unique list of all sections from filtered events for mapping usage (or just all possible sections)
	# Scanning all "Calendario" entries might be safer to ensure coverage
	all_sections = frappe.get_all("Calendario", fields=["secao"], distinct=True)
	unique_sections = set([d.secao for d in all_sections if d.secao] + ["Diretoria"])

	section_classes = {}
	for section in unique_sections:
		ramo = section_ramo_map.get(section, "default")
		normalized = "".join(
			c for c in unicodedata.normalize("NFD", ramo) if unicodedata.category(c) != "Mn"
		).lower()
		section_classes[section] = normalized

	# Data Fetching
	start_date = f"{year}-01-01"
	end_date = f"{year}-12-31"

	months_pt = [
		"",
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
	filters_text_parts = []

	if month:
		import calendar

		last_day = calendar.monthrange(year, int(month))[1]
		start_date = f"{year}-{int(month):02d}-01"
		end_date = f"{year}-{int(month):02d}-{last_day}"
		if int(month) < len(months_pt):
			filters_text_parts.append(f"Mês: {months_pt[int(month)]}")

	if sections:
		filters_text_parts.append(f"Seções: {', '.join(sections)}")

	filters_text = " | ".join(filters_text_parts)

	calendar_filters = {"inicio": ["<=", f"{end_date} 23:59:59"], "termino": [">=", f"{start_date} 00:00:00"]}

	db_events = frappe.get_all(
		"Calendario",
		filters=calendar_filters,
		fields=["name", "atividade", "inicio", "termino", "secao", "local", "nivel", "sem_atividade"],
		order_by="inicio asc",
	)

	current_date = getdate(start_date)
	end_date_obj = getdate(end_date)

	weekdays = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

	# Group events by Activity Identity
	# Identity: (Activity Name, Start, End, Location, Level)
	grouped_events = {}

	for event in db_events:
		key = (
			event.atividade,
			event.inicio,
			event.termino,
			event.local or "",
			event.nivel or "",
			event.sem_atividade,
		)

		if key not in grouped_events:
			grouped_events[key] = {"data": event, "sections": set(), "sort_key": event.inicio}

		section = event.secao or "Diretoria"
		grouped_events[key]["sections"].add(section)

	# Filter and Build List
	filtered_events = []
	busy_dates = set()

	for key, item in grouped_events.items():
		event_sections = item["sections"]
		display_sections = event_sections

		# Apply Section Filter
		if sections:
			filtered_sections_set = set(sections)
			if event_sections.isdisjoint(filtered_sections_set):
				continue
			display_sections = event_sections.intersection(filtered_sections_set)

		event = item["data"]

		# Mark Busy Dates
		s_date = getdate(event.inicio)
		e_date = getdate(event.termino)

		# Only mark days within the selected view range
		curr = max(s_date, current_date)
		fin = min(e_date, end_date_obj)

		while curr <= fin:
			busy_dates.add(curr)
			curr += timedelta(days=1)

		# Format Item
		s_fmt = format_date(event.inicio)
		e_fmt = format_date(event.termino)

		wd_start = weekdays[getdate(event.inicio).weekday()]
		wd_end = weekdays[getdate(event.termino).weekday()]

		filtered_events.append(
			{
				"sort_date": event.inicio,
				"start_date": s_fmt,
				"end_date": e_fmt,
				"wd_start": wd_start,
				"wd_end": wd_end,
				"sections": sorted(list(display_sections)),
				"atividade": event.atividade,
				"sem_atividade": event.sem_atividade,
				"local": event.local or "",
				"nivel": event.nivel or "",
			}
		)

	# Sort final list
	filtered_events.sort(key=lambda x: x["sort_date"])

	pdf_events = filtered_events

	# Render Template
	template_path = frappe.get_app_path("gris", "templates/pages/calendar_pdf.html")
	with open(template_path) as f:
		template_content = f.read()

	html_content = frappe.render_template(
		template_content,
		{
			"uel_name": uel_name,
			"uel_type": uel_type,
			"uel_logo": uel_logo,
			"year": year,
			"filters_text": filters_text,
			"events": pdf_events,
			"section_classes": section_classes,
			"generated_at": format_date(today()),
		},
	)

	pdf_content = get_pdf(html_content)

	frappe.local.response.filename = f"Calendario_{year}.pdf"
	frappe.local.response.filecontent = pdf_content
	frappe.local.response.type = "pdf"
