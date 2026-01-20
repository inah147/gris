from datetime import datetime

import frappe
import requests


def sync_feriados():
	settings = frappe.get_single("Configuracoes de Feriados")
	api_key = settings.feriadosapi_key
	ibge_code = settings.codigo_municipio_ibge

	if not api_key or not ibge_code:
		# Don't throw error, just return if not configured
		return

	year = datetime.now().year
	url = f"https://www.feriadosapi.com/api/v1/feriados/cidade/{ibge_code}?ano={year}"
	headers = {"Authorization": f"Bearer {api_key}"}

	try:
		response = requests.get(url, headers=headers)
		response.raise_for_status()
		data = response.json()

		feriados = data.get("feriados", [])

		for f in feriados:
			f_id = f.get("id")
			if not f_id:
				continue

			# Check if exists
			if frappe.db.exists("Feriados", f_id):
				doc = frappe.get_doc("Feriados", f_id)

				# Check for changes
				has_changes = False

				# Convert API date dd/mm/yyyy to yyyy-mm-dd
				api_date_str = f.get("data")
				# API format is dd/mm/yyyy
				api_date_obj = datetime.strptime(api_date_str, "%d/%m/%Y").date()

				if doc.nome != f.get("nome"):
					doc.nome = f.get("nome")
					has_changes = True

				# doc.data is usually a datetime.date object.
				if doc.data != api_date_obj:
					doc.data = api_date_obj
					has_changes = True

				if doc.tipo != f.get("tipo"):
					doc.tipo = f.get("tipo")
					has_changes = True

				if doc.descricao != f.get("descricao"):
					doc.descricao = f.get("descricao")
					has_changes = True

				if has_changes:
					doc.save()
			else:
				# Create new
				api_date_str = f.get("data")
				api_date_obj = datetime.strptime(api_date_str, "%d/%m/%Y").date()

				new_holiday = frappe.get_doc(
					{
						"doctype": "Feriados",
						"id": f_id,
						"nome": f.get("nome"),
						"data": api_date_obj,
						"tipo": f.get("tipo"),
						"descricao": f.get("descricao"),
					}
				)
				new_holiday.insert()

		frappe.db.commit()

	except Exception as e:
		frappe.log_error(title="Feriados Sync Error", message=f"{e!s}\n\n{frappe.get_traceback()}")
