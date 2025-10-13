import frappe

from gris.api.portal_cache_utils import get_uel_cached


@frappe.whitelist(allow_guest=True)
def debug_uel_data():
	"""API de debug para verificar dados da UEL."""
	data = get_uel_cached()

	# Informações sobre arquivos
	if data.get("logo"):
		files = frappe.get_all(
			"File",
			filters={"file_url": data["logo"]},
			fields=["name", "file_url", "is_private"],
			ignore_permissions=True,
		)
		data["_debug_logo_file"] = files[0] if files else "Não encontrado no DocType File"

	return data
