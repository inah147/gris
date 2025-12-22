import unicodedata
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import format_date, getdate, today

from gris.api.portal_access import enrich_context


def get_context(context):
	try:
		year = int(frappe.form_dict.year)
	except (ValueError, TypeError):
		year = getdate(today()).year

	context.year = year

	# Get available years with activities
	years_data = frappe.db.sql(
		"""
		SELECT DISTINCT YEAR(inicio) as year FROM `tabCalendario Simulado`
		UNION
		SELECT DISTINCT YEAR(termino) as year FROM `tabCalendario Simulado`
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

	# Fetch all calendar events for the year
	# We fetch a bit more to cover year boundaries if needed, but strict year filter is fine for "dias do ano"
	start_date = f"{year}-01-01"
	end_date = f"{year}-12-31"

	# Fetch events that overlap with the year
	events = frappe.get_all(
		"Calendario Simulado",
		filters={"inicio": ["<=", f"{year}-12-31 23:59:59"], "termino": [">=", f"{year}-01-01 00:00:00"]},
		fields=["name", "atividade", "inicio", "termino", "secao", "local"],
		order_by="inicio asc",
	)

	context.has_data = bool(events)

	# Check against official calendar
	official_events = frappe.get_all(
		"Calendario",
		filters={"inicio": ["<=", f"{year}-12-31 23:59:59"], "termino": [">=", f"{year}-01-01 00:00:00"]},
		fields=["atividade", "inicio", "termino", "secao"],
	)

	official_signatures = set()
	for oe in official_events:
		sig = (oe.atividade, str(oe.inicio), str(oe.termino), oe.secao)
		official_signatures.add(sig)

	non_official_events = []
	for event in events:
		sig = (event.atividade, str(event.inicio), str(event.termino), event.secao)
		if sig in official_signatures:
			event.is_official = True
		else:
			event.is_official = False
			non_official_events.append(event)

	# Group non-official events by (atividade, inicio, termino)
	grouped_events_map = {}
	for event in non_official_events:
		start_date = getdate(event.inicio)
		end_date = getdate(event.termino)
		key = (event.atividade, start_date, end_date)

		if key not in grouped_events_map:
			grouped_events_map[key] = set()

		grouped_events_map[key].add(event.secao)

	grouped_non_official_events = []
	for (atividade, start, end), secoes in grouped_events_map.items():
		grouped_non_official_events.append(
			{
				"atividade": atividade,
				"inicio": format_date(start),
				"termino": format_date(end),
				"inicio_obj": start,  # for sorting
				"secoes": ", ".join(sorted(list(secoes))),
			}
		)

	# Sort by start date
	grouped_non_official_events.sort(key=lambda x: x["inicio_obj"])

	context.non_official_events = grouped_non_official_events

	if not context.has_data:
		# Fetch available years from real Calendar to populate the dropdown
		source_years_data = frappe.db.sql(
			"""
			SELECT DISTINCT YEAR(inicio) as year FROM `tabCalendario`
			ORDER BY year DESC
		""",
			as_dict=True,
		)
		context.source_years = [y.year for y in source_years_data]

	sections = set()
	events_by_date_section = {}

	# Group events by section for lane processing
	events_by_section = {}
	for event in events:
		section = event.secao if event.secao else "Diretoria"
		sections.add(section)
		if section not in events_by_section:
			events_by_section[section] = []
		events_by_section[section].append(event)

	# Process lanes and clusters per section
	for section, section_events in events_by_section.items():
		# Sort by start date
		section_events.sort(key=lambda x: x.inicio)

		# Assign lanes (packing algorithm)
		lanes = []  # stores end_date of the last event in this lane
		for event in section_events:
			event_start = getdate(event.inicio)
			event_end = getdate(event.termino)

			assigned_lane = -1
			for i, lane_end in enumerate(lanes):
				if lane_end < event_start:
					lanes[i] = event_end
					assigned_lane = i
					break

			if assigned_lane == -1:
				assigned_lane = len(lanes)
				lanes.append(event_end)

			event.lane_index = assigned_lane

		# Identify clusters to determine max width
		clusters = []
		if section_events:
			current_cluster = [section_events[0]]
			cluster_end = getdate(section_events[0].termino)

			for event in section_events[1:]:
				evt_start = getdate(event.inicio)
				evt_end = getdate(event.termino)

				if evt_start <= cluster_end:
					current_cluster.append(event)
					cluster_end = max(cluster_end, evt_end)
				else:
					clusters.append(current_cluster)
					current_cluster = [event]
					cluster_end = evt_end
			clusters.append(current_cluster)

		# Assign total_lanes based on cluster max
		for cluster in clusters:
			max_lane = 0
			for event in cluster:
				max_lane = max(max_lane, event.lane_index)

			cluster_width_count = max_lane + 1
			for event in cluster:
				event.total_lanes = cluster_width_count

	# Populate daily map
	for event in events:
		section = event.secao if event.secao else "Diretoria"
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
			# Ensure lane info is carried over
			event_display["lane_index"] = getattr(event, "lane_index", 0)
			event_display["total_lanes"] = getattr(event, "total_lanes", 1)

			events_by_date_section[key].append(event_display)
			current += timedelta(days=1)

	# Fetch Section -> Ramo mapping for sorting
	associados = frappe.get_all("Associado", fields=["secao", "ramo"], distinct=True)
	section_ramo_map = {d.secao: d.ramo for d in associados if d.secao}

	# Get all available sections for the dropdown
	all_sections = sorted(list(set([d.secao for d in associados if d.secao] + ["Diretoria"])))
	context.all_sections = all_sections

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
		}

		has_activity = False
		for section in sorted_sections:
			key = (date_str, section)
			evts = events_by_date_section.get(key, [])

			# Sort events by lane index to ensure correct order
			# And fill gaps with None for spacers
			if evts:
				evts.sort(key=lambda x: x.get("lane_index", 0))
				# Get the maximum total_lanes from all events in this day to be safe
				max_lanes = max(e.get("total_lanes", 1) for e in evts)

				# Create a list of size max_lanes filled with None
				display_slots = [None] * max_lanes

				for evt in evts:
					idx = evt.get("lane_index", 0)
					if idx < max_lanes:
						display_slots[idx] = evt

				row["activities"][section] = display_slots
				has_activity = True
			else:
				row["activities"][section] = []

		row["has_activity"] = has_activity
		calendar_rows.append(row)
		current_date += timedelta(days=1)

	context.calendar_rows = calendar_rows

	# Sidebar and context enrichment
	context.active_link = "/calendario/visualizar"
	enrich_context(context, "/calendario/visualizar")
