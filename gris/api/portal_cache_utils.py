import frappe


def get_uel_cached(ttl: int = 300) -> dict:
	cache = frappe.cache()
	key = "uel_cached_v1"
	data = cache.get_value(key)
	if data:
		return data
	try:
		uel = frappe.get_doc("Definicao da UEL")
		data = {
			"logo": getattr(uel, "logo", None),
			"tipo_uel": getattr(uel, "tipo_uel", ""),
			"nome_da_uel": getattr(uel, "nome_da_uel", ""),
			"numeral": getattr(uel, "numeral", ""),
			"regiao": getattr(uel, "regiao", ""),
			"documentos": [
				{
					"publico": getattr(d, "publico", False),
					"nome_do_documento": getattr(d, "nome_do_documento", "Documento"),
					"arquivo": getattr(d, "arquivo", None),
				}
				for d in (getattr(uel, "documentos", []) or [])
			],
		}
	except Exception:
		data = {}
	cache.set_value(key, data, expires_in_sec=ttl)
	return data


def get_transparency_years_cached(ttl: int = 300):
	"""Public list of available transparency years (cached)."""
	cache = frappe.cache()
	key = "transparency_years_v1"
	years = cache.get_value(key)
	if years:
		return years
	try:
		rows = frappe.get_all(
			"Transparencia",
			fields=["ano_referencia"],
			distinct=True,
			order_by="ano_referencia desc",
			ignore_permissions=True,
		)
		years = [r.ano_referencia for r in rows if r.ano_referencia]
	except Exception:
		years = []
	cache.set_value(key, years, expires_in_sec=ttl)
	return years
