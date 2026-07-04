import frappe

from gris.api.financeiro.btg import get_btg_bank_statement_df

no_cache = 1


from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached


def get_context(context):
	# Bloqueia usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/inicio"
		raise frappe.Redirect

	# Logo e título lateral
	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/financeiro/contas"
	enrich_context(context, "/financeiro/contas")

	# Permissão para conciliação/upload
	context.can_reconcile_btg_empresas = frappe.has_permission(
		"Transacao BTG Empresas", ptype="create"
	) and frappe.has_permission("Transacao BTG Empresas", ptype="write")

	# Opcional: injeta no boot para JS
	try:
		if not hasattr(frappe, "boot") or not frappe.boot:
			frappe.local.boot = getattr(frappe.local, "boot", None) or frappe._dict()
		frappe.local.boot["can_reconcile_btg_empresas"] = context.can_reconcile_btg_empresas
	except Exception:
		pass

	return context


@frappe.whitelist()
def process_uploaded_btg_file(file_url):
	import hashlib
	import os

	def _resolve_path(file_url: str) -> str:
		if not file_url:
			frappe.log_error("file_url vazio", "BTG Empresas _resolve_path")
			return ""
		file_url = file_url.strip()
		frappe.log_error(f"file_url recebido: {file_url}", "BTG Empresas _resolve_path")
		if file_url.startswith("/private/files/"):
			return frappe.get_site_path(file_url.lstrip("/"))
		if file_url.startswith("/files/"):
			parts = file_url.split("/files/", 1)
			if len(parts) == 2:
				inner = parts[1]
				return frappe.get_site_path("public", "files", inner)
			else:
				frappe.log_error(f"file_url.split inesperado: {parts}", "BTG Empresas _resolve_path")
				frappe.throw(f"file_url inválido: {file_url}")
		return frappe.get_site_path("public", file_url.lstrip("/"))

	path = _resolve_path(file_url)
	if not (path and os.path.exists(path)):
		frappe.throw(f"Arquivo não encontrado: {path}", frappe.FileNotFoundError)

	df = get_btg_bank_statement_df(path)
	stats = {"total": len(df), "inserted": 0, "skipped_exist": 0, "failed": 0}
	errors = []

	for _, row in df.iterrows():
		try:
			# Gera um hash único para a transação
			tx_id = row.get("id")

			filters = {"id": tx_id}
			if filters and frappe.db.exists("Transacao BTG Empresas", filters):
				stats["skipped_exist"] += 1
			else:
				doc = frappe.get_doc(
					{
						"doctype": "Transacao BTG Empresas",
						"id": tx_id,
						"data_transacao": row.get("timestamp"),
						"descricao": row.get("description"),
						"valor": row.get("value"),
						"tipo": row.get("type"),
					}
				)
				doc.insert(ignore_permissions=False)
				stats["inserted"] += 1
		except Exception as e:
			stats["failed"] += 1
			errors.append(str(e))
			try:
				frappe.log_error(str(e), "Importação BTG Empresas")
			except Exception:
				pass

	return {
		"stats": stats,
		"errors": errors,
	}
