import hashlib
import os

import frappe

from gris.api.financeiro.portao3 import get_portao3_bank_statement_df
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


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
	context.can_reconcile_portao3 = frappe.has_permission(
		"Transacao Portao 3", ptype="create"
	) and frappe.has_permission("Transacao Portao 3", ptype="write")

	# Opcional: injeta no boot para JS
	try:
		if not hasattr(frappe, "boot") or not frappe.boot:
			frappe.local.boot = getattr(frappe.local, "boot", None) or frappe._dict()
		frappe.local.boot["can_reconcile_portao3"] = context.can_reconcile_portao3
	except Exception:
		pass

	return context


@frappe.whitelist()
def process_uploaded_file_portao3(file_url):
	# Permissão: apenas usuários com permissão de criação/edição
	if not frappe.has_permission("Transacao Portao 3", ptype="create") or not frappe.has_permission(
		"Transacao Portao 3", ptype="write"
	):
		frappe.throw(
			"Sem permissão para conciliação: requer criar/editar em 'Transacao Portao 3'.",
			frappe.PermissionError,
		)

	def _resolve_path(file_url: str) -> str:
		if not file_url:
			return ""
		file_url = file_url.strip()
		if file_url.startswith("/private/files/"):
			return frappe.get_site_path(file_url.lstrip("/"))
		if file_url.startswith("/files/"):
			inner = file_url.split("/files/", 1)[1]
			return frappe.get_site_path("public", "files", inner)
		return frappe.get_site_path("public", file_url.lstrip("/"))

	path = _resolve_path(file_url)
	if not (path and os.path.exists(path)):
		frappe.throw(f"Arquivo não encontrado: {path}", frappe.FileNotFoundError)

	df = get_portao3_bank_statement_df(path)
	stats = {"total": len(df), "inserted": 0, "skipped_exist": 0, "failed": 0}
	errors = []

	for _, row in df.iterrows():
		try:
			tx_id_str = (
				f"{row.get('Date')}{row.get('Descrição')}{row.get('Valor')}{row.get('Entrada/Saída')}"
				f"{row.get('Carteira')}{row.get('Tipo')}{row.get('Tipo de transação')}"
			)
			tx_hash = hashlib.md5(tx_id_str.encode("utf-8")).hexdigest()
			tx_id = f"Portao3-{tx_hash}"

			filters = {"id": tx_id}
			if filters and frappe.db.exists("Transacao Portao 3", filters):
				stats["skipped_exist"] += 1
			else:
				doc = frappe.get_doc(
					{
						"doctype": "Transacao Portao 3",
						"id": tx_id,
						"timestamp": row.get("Date"),
						"data_transacao": row.get("Date").date(),
						"tipo": row.get("Tipo"),
						"valor": row.get("Valor"),
						"descricao": row.get("Descrição"),
						"carteira": row.get("Carteira"),
						"tipo_de_transacao": row.get("Tipo de transação"),
						"cartao_final": row.get("Cartão final"),
						"entrada_saida": row.get("Entrada/Saída"),
						"e2e": row.get("E2E"),
					}
				)
				doc.insert(ignore_permissions=False)
				stats["inserted"] += 1
		except Exception as e:
			stats["failed"] += 1
			errors.append(str(e))
			try:
				frappe.log_error(str(e), "Importação Portao 3")
			except Exception:
				pass

	return {
		"stats": stats,
		"errors": errors,
	}
