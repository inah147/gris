from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, format_date, getdate, today

from gris.api.portal_access import enrich_context, user_has_access

no_cache = 1


# Palette saturada para uso como `--cal-cat-color`: borda + texto. O componente
# de calendário deriva o fundo pastel automaticamente via `color-mix` em runtime.
SECTION_COLORS = {
	"Filhotes": "#E14B0E",  # laranja queimado
	"Lobinho": "#FCB81F",  # amarelo/amber escuro
	"Escoteiro": "#94C11F",  # verde escoteiro
	"Sênior": "#A9133D",  # azul profundo
	"Pioneiro": "#E30613",  # vermelho pioneiro
}
UNAVAILABLE_CATEGORY = "Indisponível"
UNAVAILABLE_COLOR = "#475569"  # cinza ardósia (neutro, separa das categorias ativas)


def _calc_age_str(visit_date, dob):
	if not dob:
		return ""
	dob = getdate(dob)
	years = visit_date.year - dob.year - ((visit_date.month, visit_date.day) < (dob.month, dob.day))
	months = (visit_date.year - dob.year) * 12 + visit_date.month - dob.month
	months = months % 12
	return f"{years}a {months}m"


def get_context(context):
	context.no_cache = 1

	if not user_has_access("/recepcao"):
		frappe.throw("Você não tem permissão para acessar esta página.", frappe.PermissionError)

	try:
		year = int(frappe.form_dict.year)
	except (ValueError, TypeError):
		year = getdate(today()).year

	context.year = year

	current_today = getdate(today())
	start_date = date(year - 1, 11, 1)
	if year == current_today.year:
		limit_date = getdate(add_days(current_today, -60))
		if limit_date > start_date:
			start_date = limit_date
	end_date = date(year + 1, 3, 1) - timedelta(days=1)

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

	calendar_events = frappe.get_all(
		"Calendario",
		filters={"inicio": ["<=", end_date], "termino": [">=", start_date]},
		fields=["name", "atividade", "inicio", "termino", "secao"],
	)

	events = []

	for visit in visits:
		if not visit.ramo or visit.ramo not in SECTION_COLORS:
			continue
		visit_date = getdate(visit.data_da_visita)
		confirmed = cint(visit.visita_confirmada)
		events.append(
			{
				"id": visit.name,
				"title": visit.nome_da_crianca or "Visita",
				"start": visit_date.isoformat(),
				"end": None,
				"all_day": True,
				"category": visit.ramo,
				"icon": "circle-check-big" if confirmed else None,
				"icon_color": "var(--success)" if confirmed else None,
				"data": {
					"type": "visit",
					"jovem": visit.jovem,
					"name": visit.nome_da_crianca,
					"age": _calc_age_str(visit_date, visit.data_de_nascimento),
					"confirmed": confirmed,
				},
			}
		)

	for event in calendar_events:
		section = event.secao
		if not section or section not in SECTION_COLORS:
			continue
		events.append(
			{
				"id": event.name,
				"title": event.atividade or "Indisponível",
				"start": getdate(event.inicio).isoformat(),
				"end": getdate(event.termino).isoformat(),
				"all_day": True,
				"category": UNAVAILABLE_CATEGORY,
				"data": {
					"type": "unavailable",
					"secao": section,
					"atividade": event.atividade,
				},
			}
		)

	categories = [{"name": name, "label": name, "color": color} for name, color in SECTION_COLORS.items()]
	categories.append(
		{"name": UNAVAILABLE_CATEGORY, "label": UNAVAILABLE_CATEGORY, "color": UNAVAILABLE_COLOR}
	)

	if year == current_today.year:
		initial_date = current_today.isoformat()
	else:
		initial_date = date(year, 1, 1).isoformat()

	context.events = events
	context.categories = categories
	context.initial_date = initial_date

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
	visit = frappe.get_doc("Agenda de Visitas", visit_name)
	associate_name = visit.jovem
	frappe.delete_doc("Agenda de Visitas", visit_name)
	if associate_name:
		frappe.db.set_value("Novo Associado", associate_name, "visita_agendada", 0)


@frappe.whitelist()
def reschedule_visit(visit_name, new_date):
	visit = frappe.get_doc("Agenda de Visitas", visit_name)
	if not _is_date_available_for_ramo(visit.ramo, new_date):
		frappe.throw(_("A data selecionada não está disponível para o ramo da visita."))

	frappe.db.set_value("Agenda de Visitas", visit_name, "data_da_visita", new_date)


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


def _get_available_dates(ramo):
	start_date = getdate(today())
	end_date = add_days(start_date, 60)

	saturdays = []
	current = start_date
	while current <= end_date:
		if current.weekday() == 5:
			saturdays.append(current)
		current = add_days(current, 1)

	if not saturdays:
		return []

	target_sections = _get_sections_by_ramos({ramo})

	activities = frappe.get_all(
		"Calendario",
		filters={
			"inicio": ["<=", end_date],
			"termino": [">=", start_date],
		},
		fields=["inicio", "termino", "secao", "abertura_geral"],
	)

	blocked_dates = set()
	for act in activities:
		if cint(act.abertura_geral):
			continue

		if not act.secao or act.secao not in target_sections:
			continue

		act_start = getdate(act.inicio)
		act_end = getdate(act.termino)

		for sat in saturdays:
			if act_start <= sat <= act_end:
				blocked_dates.add(sat)

	return [
		{
			"value": sat.strftime("%Y-%m-%d"),
			"label": format_date(sat),
		}
		for sat in saturdays
		if sat not in blocked_dates
	]


def _is_date_available_for_ramo(ramo, date_value):
	if not ramo or not date_value:
		return False

	target_date = getdate(date_value).strftime("%Y-%m-%d")
	available_dates = _get_available_dates(ramo)
	return any(item.get("value") == target_date for item in available_dates)


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

	associate_doc = frappe.get_doc("Novo Associado", associate)
	if not _is_date_available_for_ramo(associate_doc.ramo, date):
		frappe.throw(_("A data selecionada não está disponível para o ramo do associado."))

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

	associate_doc.visita_agendada = 1
	associate_doc.status = "Visita Agendada"
	associate_doc.save()

	return visit.name
