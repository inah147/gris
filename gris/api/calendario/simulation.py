import unicodedata

import frappe
from frappe.utils import getdate


def get_ramo_class(secao):
	ramo = frappe.db.get_value("Associado", {"secao": secao}, "ramo")
	if not ramo:
		return "ramo-default"

	normalized = "".join(
		c for c in unicodedata.normalize("NFD", ramo) if unicodedata.category(c) != "Mn"
	).lower()
	return f"ramo-{normalized}"


@frappe.whitelist()
def copy_calendar_data(source_year, target_year):
	source_year = int(source_year)
	target_year = int(target_year)
	year_diff = target_year - source_year

	events = frappe.get_all(
		"Calendario",
		filters={"inicio": ["between", [f"{source_year}-01-01", f"{source_year}-12-31"]]},
		fields=["atividade", "inicio", "termino", "secao", "local"],
	)

	if not events:
		return {"success": False, "message": "Nenhum evento encontrado no ano de origem."}

	count = 0
	for event in events:
		new_start = getdate(event.inicio)
		new_end = getdate(event.termino)

		try:
			new_start = new_start.replace(year=new_start.year + year_diff)
			new_end = new_end.replace(year=new_end.year + year_diff)
		except ValueError:
			# Handle leap year (Feb 29 -> Feb 28)
			if new_start.month == 2 and new_start.day == 29:
				new_start = new_start.replace(day=28, year=new_start.year + year_diff)
			if new_end.month == 2 and new_end.day == 29:
				new_end = new_end.replace(day=28, year=new_end.year + year_diff)

		doc = frappe.get_doc(
			{
				"doctype": "Calendario Simulado",
				"atividade": event.atividade,
				"inicio": new_start,
				"termino": new_end,
				"secao": event.secao,
				"local": event.local,
			}
		)
		doc.insert()
		count += 1

	return {"success": True, "message": f"{count} eventos copiados com sucesso para {target_year}."}


@frappe.whitelist()
def create_simulation_event(atividade, inicio, termino, secoes, local=None):
	if isinstance(secoes, str):
		secoes = frappe.parse_json(secoes)

	if not secoes:
		return {"success": False, "message": "Selecione pelo menos uma seção."}

	created_events = []
	for secao in secoes:
		doc = frappe.get_doc(
			{
				"doctype": "Calendario Simulado",
				"atividade": atividade,
				"inicio": inicio,
				"termino": termino,
				"secao": secao,
				"local": local,
			}
		)
		doc.insert()

		ramo_class = get_ramo_class(secao)

		created_events.append(
			{
				"name": doc.name,
				"atividade": doc.atividade,
				"inicio": str(doc.inicio),
				"termino": str(doc.termino),
				"secao": doc.secao,
				"local": doc.local,
				"ramo_class": ramo_class,
			}
		)

	return {
		"success": True,
		"message": f"{len(created_events)} eventos criados com sucesso.",
		"events": created_events,
	}


@frappe.whitelist()
def update_simulation_event(event_id, atividade, inicio, termino, secao, local=None):
	doc = frappe.get_doc("Calendario Simulado", event_id)
	doc.atividade = atividade
	doc.inicio = inicio
	doc.termino = termino
	doc.secao = secao
	doc.local = local
	doc.save()
	return {"success": True, "message": "Evento atualizado com sucesso."}


@frappe.whitelist()
def delete_simulation_event(event_id):
	frappe.delete_doc("Calendario Simulado", event_id)
	return {"success": True, "message": "Evento excluído com sucesso."}
