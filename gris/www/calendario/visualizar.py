import base64
import json
import mimetypes
import unicodedata
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import format_date, getdate, today
from frappe.utils.pdf import get_pdf

from gris.api.portal_access import enrich_context

MONTH_OPTIONS = [
	{"value": "", "label": "Todos os meses"},
	{"value": "01", "label": "Janeiro"},
	{"value": "02", "label": "Fevereiro"},
	{"value": "03", "label": "Março"},
	{"value": "04", "label": "Abril"},
	{"value": "05", "label": "Maio"},
	{"value": "06", "label": "Junho"},
	{"value": "07", "label": "Julho"},
	{"value": "08", "label": "Agosto"},
	{"value": "09", "label": "Setembro"},
	{"value": "10", "label": "Outubro"},
	{"value": "11", "label": "Novembro"},
	{"value": "12", "label": "Dezembro"},
]

SECTION_COLOR_BY_RAMO = {
	"diretoria": "var(--chart-1)",
	"filhotes": "var(--chart-4)",
	"lobinho": "var(--warning)",
	"escoteiro": "var(--success)",
	"senior": "var(--chart-6)",
	"pioneiro": "var(--destructive)",
}

HOLIDAY_TYPE_BADGE = {
	"Nacional": "default",
	"Estadual": "secondary",
	"Municipal": "outline",
	"Ponto Facultativo": "secondary",
}


def _normalize_text(value):
	if not value:
		return ""
	return "".join(
		char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn"
	).lower()


def _get_selected_year():
	try:
		return int(frappe.form_dict.year)
	except (ValueError, TypeError):
		return getdate(today()).year


def _get_selected_month():
	raw_month = frappe.form_dict.month
	if raw_month in {None, ""}:
		return ""
	try:
		month = int(raw_month)
	except (TypeError, ValueError):
		return ""
	if 1 <= month <= 12:
		return f"{month:02d}"
	return ""


def _get_available_years(selected_year):
	years_data = frappe.db.sql(
		"""
		SELECT DISTINCT YEAR(inicio) as year FROM `tabCalendario`
		UNION
		SELECT DISTINCT YEAR(termino) as year FROM `tabCalendario`
		ORDER BY year DESC
	""",
		as_dict=True,
	)
	available_years = sorted({int(row.year) for row in years_data if row.year}, reverse=True)
	if selected_year not in available_years:
		available_years.append(selected_year)
		available_years.sort(reverse=True)
	return available_years


def _get_section_sorting_data():
	associados = frappe.get_all("Associado", fields=["secao", "ramo"], distinct=True)
	section_ramo_map = {row.secao: row.ramo for row in associados if row.secao}
	ramo_order = ["Diretoria", "Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"]

	def sort_key(section_name):
		if section_name == "Diretoria":
			return (0, section_name)

		ramo = section_ramo_map.get(section_name)
		if ramo in ramo_order:
			return (ramo_order.index(ramo), section_name)

		return (len(ramo_order), section_name)

	return section_ramo_map, sort_key


def _get_section_color(section_name, section_ramo_map):
	ramo = "Diretoria" if section_name == "Diretoria" else section_ramo_map.get(section_name)
	return SECTION_COLOR_BY_RAMO.get(_normalize_text(ramo), "var(--primary)")


def _is_all_day_event(start_dt, end_dt):
	start_time = getattr(start_dt, "time", lambda: None)()
	end_time = getattr(end_dt, "time", lambda: None)()
	if not start_time or not end_time:
		return True
	return start_time.strftime("%H:%M:%S") == "00:00:00" and end_time.strftime("%H:%M:%S") == "00:00:00"


def _build_calendar_payload(year, selected_month):
	start_date = f"{year}-01-01"
	end_date = f"{year}-12-31"

	events = frappe.get_all(
		"Calendario",
		filters={"inicio": ["<=", f"{end_date} 23:59:59"], "termino": [">=", f"{start_date} 00:00:00"]},
		fields=["name", "atividade", "inicio", "termino", "secao", "local", "nivel", "sem_atividade"],
		order_by="inicio asc",
	)

	section_ramo_map, sort_key = _get_section_sorting_data()
	sections = sorted({(event.secao or "Diretoria") for event in events} or {"Diretoria"}, key=sort_key)
	section_categories = [
		{
			"name": section,
			"label": section,
			"color": _get_section_color(section, section_ramo_map),
		}
		for section in sections
	]
	section_color_map = {item["name"]: item["color"] for item in section_categories}

	calendar_events = []
	for event in events:
		section = event.secao or "Diretoria"
		calendar_events.append(
			{
				"id": event.name,
				"title": event.atividade or "Atividade",
				"start": event.inicio.isoformat() if event.inicio else None,
				"end": event.termino.isoformat() if event.termino else None,
				"all_day": _is_all_day_event(event.inicio, event.termino),
				"category": section,
				"color": section_color_map.get(section, "var(--primary)"),
				"data": {
					"atividade": event.atividade or "Atividade",
					"inicio": format_date(event.inicio) if event.inicio else "-",
					"termino": format_date(event.termino) if event.termino else "-",
					"hora_inicio": event.inicio.strftime("%H:%M") if event.inicio else "",
					"hora_termino": event.termino.strftime("%H:%M") if event.termino else "",
					"secao": section,
					"local": event.local or "-",
					"nivel": event.nivel or "-",
					"sem_atividade": 1 if event.sem_atividade else 0,
				},
			}
		)

	feriados = frappe.get_all(
		"Feriados",
		filters={"data": ["between", [start_date, end_date]]},
		fields=["nome", "data", "tipo", "descricao"],
		order_by="data asc",
	)
	weekday_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
	holiday_items = [
		{
			"name": holiday.nome,
			"date_iso": holiday.data.strftime("%Y-%m-%d"),
			"date_label": format_date(holiday.data),
			"month": holiday.data.strftime("%m"),
			"weekday": weekday_labels[holiday.data.weekday()],
			"type": holiday.tipo or "Geral",
			"description": holiday.descricao or "Sem descrição disponível.",
			"badge_variant": HOLIDAY_TYPE_BADGE.get(holiday.tipo, "outline"),
		}
		for holiday in feriados
	]

	today_date = getdate(today())
	if selected_month:
		anchor_date = date(year, int(selected_month), 1)
	else:
		anchor_date = today_date if today_date.year == year else date(year, 1, 1)

	if selected_month:
		month_number = int(selected_month)
		next_month = date(
			year + (1 if month_number == 12 else 0), 1 if month_number == 12 else month_number + 1, 1
		)
		last_day = (next_month - timedelta(days=1)).day
		list_range_start = f"{year}-{selected_month}-01"
		list_range_end = f"{year}-{selected_month}-{last_day:02d}"
	else:
		list_range_start = f"{year}-01-01"
		list_range_end = f"{year}-12-31"

	return {
		"sections": sections,
		"calendar_categories": section_categories,
		"calendar_events": calendar_events,
		"holiday_items": holiday_items,
		"calendar_initial_date": anchor_date.strftime("%Y-%m-%d"),
		"calendar_list_range_start": list_range_start,
		"calendar_list_range_end": list_range_end,
	}


def get_context(context):
	context.no_cache = 1

	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Visualizador Calendario", "Gestor Calendario", "System Manager"]):
		frappe.throw(_("Você não tem permissão para acessar esta página."), frappe.PermissionError)

	year = _get_selected_year()
	selected_month = _get_selected_month()
	payload = _build_calendar_payload(year, selected_month)

	context.year = year
	context.selected_month = selected_month
	context.available_years = _get_available_years(year)
	context.year_items = [{"value": str(value), "label": str(value)} for value in context.available_years]
	context.month_items = MONTH_OPTIONS
	context.selected_sections = []
	context.sections = payload["sections"]
	context.section_items = [{"value": section, "label": section} for section in context.sections]
	context.calendar_categories = payload["calendar_categories"]
	context.calendar_events = payload["calendar_events"]
	context.has_calendar_events = bool(context.calendar_events)
	context.calendar_initial_date = payload["calendar_initial_date"]
	context.calendar_initial_mode = "list"
	context.calendar_list_range_start = payload["calendar_list_range_start"]
	context.calendar_list_range_end = payload["calendar_list_range_end"]
	context.holiday_items = payload["holiday_items"]
	context.can_simulate = "Gestor Calendario" in roles or "System Manager" in roles
	context.active_link = "/calendario/visualizar"

	enrich_context(context, "/calendario/visualizar")


@frappe.whitelist()
def export_calendar(year=None, month=None, show_empty_days=1, sections=None):
	roles = frappe.get_roles(frappe.session.user)
	if not any(role in roles for role in ["Visualizador Calendario", "Gestor Calendario", "System Manager"]):
		frappe.throw(_("Você não tem permissão para acessar esta funcionalidade."), frappe.PermissionError)

	if not year:
		year = getdate(today()).year
	else:
		year = int(year)

	if sections and isinstance(sections, str):
		try:
			sections = json.loads(sections)
		except Exception:
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
			# Caminho devolvido pelo file_manager do Frappe para um File do site.
			with open(file_path, "rb") as f:  # nosemgrep
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

	for item in grouped_events.values():
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
	# Template interno da app, montado com frappe.get_app_path logo acima.
	with open(template_path) as f:  # nosemgrep
		template_content = f.read()

	# `template_content` é o HTML interno da app lido logo acima.
	html_content = frappe.render_template(  # nosemgrep
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
