from datetime import datetime

import frappe
import requests

from gris.utils.job_logger import definir_resumo, metrica, obter_logger


def sync_feriados():
	"""Job diario: sincroniza os feriados do municipio com a Feriados API."""
	logger = obter_logger("sync_feriados")

	settings = frappe.get_single("Configuracoes de Feriados")
	api_key = settings.feriadosapi_key
	ibge_code = settings.codigo_municipio_ibge

	if not api_key or not ibge_code:
		# Don't throw error, just return if not configured
		logger.warning(
			"Sincronizacao de feriados ignorada: falta a chave da API ou o codigo do municipio "
			"em Configuracoes de Feriados."
		)
		definir_resumo("Integração de feriados não configurada — nada foi sincronizado.")
		return

	year = datetime.now().year
	url = f"https://www.feriadosapi.com/api/v1/feriados/cidade/{ibge_code}?ano={year}"
	headers = {"Authorization": f"Bearer {api_key}"}

	criados = 0
	atualizados = 0
	sem_alteracao = 0
	ignorados = 0

	try:
		logger.info(f"Consultando feriados de {year} para o municipio {ibge_code}.")
		response = requests.get(url, headers=headers)
		response.raise_for_status()
		data = response.json()

		feriados = data.get("feriados", [])
		logger.info(f"A API devolveu {len(feriados)} feriado(s).")

		for f in feriados:
			f_id = f.get("id")
			if not f_id:
				logger.warning(f"Feriado sem id devolvido pela API, ignorado: {f.get('nome') or f}.")
				ignorados += 1
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
					atualizados += 1
					logger.info(f"Feriado atualizado: {doc.nome} ({doc.data}).")
				else:
					sem_alteracao += 1
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
				criados += 1
				logger.info(f"Feriado criado: {new_holiday.nome} ({new_holiday.data}).")

		frappe.db.commit()

		metrica("criados", criados, incrementar=False)
		metrica("atualizados", atualizados, incrementar=False)
		metrica("sem_alteracao", sem_alteracao, incrementar=False)
		metrica("ignorados", ignorados, incrementar=False)
		definir_resumo(
			f"{criados} feriado(s) criado(s), {atualizados} atualizado(s) e "
			f"{sem_alteracao} sem alteração para {year}."
		)

	except Exception as e:
		logger.exception(f"Falha ao sincronizar os feriados de {year}: {e!s}")
		definir_resumo(f"A sincronização de feriados de {year} falhou.")
		frappe.log_error(title="Feriados Sync Error", message=f"{e!s}\n\n{frappe.get_traceback()}")
