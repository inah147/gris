import frappe
from frappe.utils import today

ALLOWED_UPDATE_FIELDS = {
	"guardiao_legal_responsavel_1",
	"guardiao_legal_responsavel_2",
	"anos_afastamento",
	"eleito",
	"tipo_guarda",
	"area",
	"pais_divorciados",
}


def _ensure_logged_in():
	if frappe.session.user == "Guest":
		frappe.throw("Session expired. Please login again.", frappe.PermissionError)


def _can_edit(doc):
	# Only users with role 'Gestor de Associados' can edit (avoid frappe.has_role for compatibility)
	try:
		return "Gestor de Associados" in frappe.get_roles()
	except Exception:  # pragma: no cover
		return False


@frappe.whitelist(methods=["POST"])  # type: ignore[misc]
def update_member(name: str, changes: str):
	"""Update allowed fields of an Associado from a JSON of changes."""
	_ensure_logged_in()
	try:
		doc = frappe.get_doc("Associado", name)
	except frappe.DoesNotExistError:
		frappe.throw("Member not found", frappe.DoesNotExistError)

	can_edit = _can_edit(doc)

	try:
		data = frappe.parse_json(changes) if isinstance(changes, str) else changes
	except Exception:  # pragma: no cover
		frappe.throw("Invalid JSON in 'changes'")

	if not isinstance(data, dict):
		frappe.throw("Invalid changes format")

	applied = {}
	for field, val in data.items():
		if field not in ALLOWED_UPDATE_FIELDS:
			continue
		if not can_edit:
			# skip silently if user can't edit
			continue
		meta = frappe.get_meta("Associado")
		df = meta.get_field(field)
		if not df:
			continue
		if df.fieldtype == "Check":
			if isinstance(val, str):
				val_l = val.lower()
				val = 1 if val_l in {"1", "true", "on", "yes", "sim"} else 0
			else:
				val = 1 if val else 0
		doc.set(field, val)
		applied[field] = val

	if applied:
		try:
			doc.save()  # respect user permissions
			frappe.db.commit()
		except frappe.PermissionError:
			return {"success": False, "message": "Permission denied saving document", "applied": {}}

	return {"success": True, "applied": applied, "can_edit": can_edit}


@frappe.whitelist(methods=["POST"])  # type: ignore[misc]
def set_member_leave(name: str):
	"""Set leave date (afastamento) inserting today in the first history row without a desligamento date."""
	_ensure_logged_in()
	try:
		doc = frappe.get_doc("Associado", name)
	except frappe.DoesNotExistError:
		frappe.throw("Member not found", frappe.DoesNotExistError)

	if not _can_edit(doc):
		frappe.throw("No permission to edit", frappe.PermissionError)

	applied_date = None
	for row in doc.get("historico_no_grupo") or []:
		if not row.get("data_de_desligamento"):
			row.data_de_desligamento = today()
			applied_date = row.data_de_desligamento
			break

	if not applied_date:
		return {"success": False, "message": "No open history row to set leave."}

	try:
		doc.save()  # respect permissions
		frappe.db.commit()
	except frappe.PermissionError:
		return {"success": False, "message": "Permission denied saving leave"}
	return {"success": True, "desligamento": applied_date}


@frappe.whitelist()  # type: ignore[misc]
def get_member_history(name: str):
	"""Get history records for a member."""
	_ensure_logged_in()
	try:
		doc = frappe.get_doc("Associado", name)
	except frappe.DoesNotExistError:
		frappe.throw("Member not found", frappe.DoesNotExistError)

	if not _can_edit(doc):
		frappe.throw("No permission to view", frappe.PermissionError)

	history = []
	for row in doc.get("historico_no_grupo") or []:
		history.append(
			{
				"ingresso": row.data_de_ingresso,
				"desligamento": row.data_de_desligamento,
			}
		)

	return {"success": True, "history": history}


@frappe.whitelist()  # type: ignore[misc]
def update_member_history(name: str, history: str):
	"""Update history records for a member."""
	_ensure_logged_in()
	try:
		doc = frappe.get_doc("Associado", name)
	except frappe.DoesNotExistError:
		frappe.throw("Member not found", frappe.DoesNotExistError)

	if not _can_edit(doc):
		frappe.throw("No permission to edit", frappe.PermissionError)

	import json

	history_data = json.loads(history)

	# Clear existing history
	doc.historico_no_grupo = []

	# Add new history records
	for item in history_data:
		if not item.get("ingresso"):
			return {"success": False, "message": "All records must have ingresso date"}

		doc.append(
			"historico_no_grupo",
			{
				"data_de_ingresso": item.get("ingresso"),
				"data_de_desligamento": item.get("desligamento") or None,
			},
		)

	try:
		doc.save()
		frappe.db.commit()
	except frappe.PermissionError:
		return {"success": False, "message": "Permission denied saving history"}
	except Exception as e:
		return {"success": False, "message": str(e)}

	return {"success": True}
