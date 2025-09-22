import datetime

import frappe


def _first_day_of_month(date: datetime.date | None = None) -> datetime.date:
	date = date or datetime.date.today()
	return datetime.date(date.year, date.month, 1)


@frappe.whitelist()
def generate_monthly_payments():
	"""Create 'Em Aberto' payment records for all active beneficiary associates for current month.
	Idempotent per month.
	"""
	month_ref = _first_day_of_month()
	month_ref_str = month_ref.strftime("%Y-%m-%d")

	associates = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo", "categoria": "Beneficiário"},
		fields=["name", "valor_contribuicao"],
	)
	if not associates:
		return 0

	existing = frappe.get_all(
		"Pagamento Contribuicao Mensal",
		filters={"mes_de_referencia": month_ref_str},
		pluck="associado",
	)
	existing_set = set(existing)

	created = 0
	for a in associates:
		if a.name in existing_set:
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Pagamento Contribuicao Mensal",
				"associado": a.name,
				"status": "Em Aberto",
				"mes_de_referencia": month_ref_str,
				"valor": a.valor_contribuicao or 0,
			}
		)
		doc.insert()
		created += 1

	frappe.logger("pagamento_contribuicao_mensal").info(
		{
			"event": "generate_monthly_payments",
			"month_reference": month_ref_str,
			"created": created,
		}
	)
	return created


@frappe.whitelist()
def update_contribution_value(associate_id: str, new_value: float):
	"""Update Associate.valor_contribuicao."""
	if not associate_id:
		raise frappe.ValidationError("Parameter 'associate_id' is required")
	try:
		new_value_f = float(new_value)
	except (TypeError, ValueError):
		raise frappe.ValidationError("Invalid value")
	if new_value_f < 0:
		raise frappe.ValidationError("Value cannot be negative")

	doc = frappe.get_doc("Associado", associate_id)
	doc.valor_contribuicao = new_value_f
	doc.save(ignore_permissions=False)
	frappe.db.commit()
	return {"ok": True, "value": new_value_f}


@frappe.whitelist()
def mark_payment_as_paid(payment_id: str):
	"""Mark payment record as 'Pago'."""
	if not payment_id:
		raise frappe.ValidationError("Parameter 'payment_id' is required")
	doc = frappe.get_doc("Pagamento Contribuicao Mensal", payment_id)
	if doc.status == "Pago":
		return {"ok": True, "status": doc.status}
	doc.status = "Pago"
	doc.save(ignore_permissions=False)
	frappe.db.commit()
	return {"ok": True, "status": "Pago"}


@frappe.whitelist()
def activate_billing_status(associate_id: str):
	"""Mark associate's status_cobranca as 'Ativo'.

	Returns JSON { ok: True, previous: <old_status>, current: 'Ativo' }
	"""
	if not associate_id:
		raise frappe.ValidationError("Parameter 'associate_id' is required")
	assoc = frappe.get_doc("Associado", associate_id)
	prev = assoc.get("status_cobranca")
	if prev == "Ativo":
		return {"ok": True, "previous": prev, "current": prev}
	assoc.status_cobranca = "Ativo"
	assoc.save(ignore_permissions=False)
	frappe.db.commit()
	return {"ok": True, "previous": prev, "current": "Ativo"}


@frappe.whitelist()
def deactivate_billing_status(associate_id: str):
	"""Mark associate's status_cobranca as 'Inativo'.

	Returns JSON { ok: True, previous: <old_status>, current: 'Inativo' }
	"""
	if not associate_id:
		raise frappe.ValidationError("Parameter 'associate_id' is required")
	assoc = frappe.get_doc("Associado", associate_id)
	prev = assoc.get("status_cobranca")
	if prev == "Inativo":
		return {"ok": True, "previous": prev, "current": prev}
	assoc.status_cobranca = "Inativo"
	assoc.save(ignore_permissions=False)
	frappe.db.commit()
	return {"ok": True, "previous": prev, "current": "Inativo"}


@frappe.whitelist()
def update_billing_contacts(associate_id: str, email: str | None = None, phone: str | None = None):
	"""Update billing contact fields (email_cobranca, telefone_cobranca).

	Returns { ok: True, email: <value>, phone: <value> }
	"""
	if not associate_id:
		raise frappe.ValidationError("Parameter 'associate_id' is required")
	assoc = frappe.get_doc("Associado", associate_id)
	# Basic sanitation (strip). Further validation (email format) could be added.
	if email is not None:
		assoc.email_cobranca = (email or "").strip() or None
	if phone is not None:
		assoc.telefone_cobranca = (phone or "").strip() or None
	assoc.save(ignore_permissions=False)
	frappe.db.commit()
	return {"ok": True, "email": assoc.email_cobranca, "phone": assoc.telefone_cobranca}


def _is_holiday(date_obj: datetime.date) -> bool:
	fixed_holidays = {
		"01-01",  # New Year
		"21-04",  # Tiradentes
		"01-05",  # Labour Day
		"07-09",  # Independence
		"12-10",  # Aparecida
		"02-11",  # All Souls
		"15-11",  # Republic Proclamation
		"25-12",  # Christmas
	}

	return date_obj.strftime("%d-%m") in fixed_holidays


@frappe.whitelist()
def update_status_monthly_payment() -> None:
	# 1. Fetch configured due day (default 10 if missing / invalid)
	try:
		config = frappe.get_single("Configuracoes Contribuicao Mensal")
		due_day = int(getattr(config, "dia_vencimento", 10) or 10)
	except Exception:
		due_day = 10
	if due_day < 1 or due_day > 28:  # keep inside safe month window
		due_day = 10

	# 2. Build base due date for current month
	today = datetime.date.today()
	base_due_date = datetime.date(today.year, today.month, due_day)

	# 4. Adjust to next business day if weekend / holiday
	adjusted_due = base_due_date
	while adjusted_due.weekday() >= 5 or _is_holiday(adjusted_due):  # 5=Sat 6=Sun
		adjusted_due += datetime.timedelta(days=1)

	# 5. If still before or on adjusted due date, exit
	if today <= adjusted_due:
		return

	# 6. Query open payments possibly in current month window
	first_month_day = base_due_date.replace(day=1)
	next_month = (first_month_day.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
	open_payments = frappe.get_all(
		"Pagamento Contribuicao Mensal",
		filters={
			"status": "Em Aberto",
			"mes_de_referencia": ["<", next_month.strftime("%Y-%m-%d")],
		},
		fields=["name", "associado", "mes_de_referencia", "valor"],
	)

	# Filter strictly to current month
	current_month_open = []
	for row in open_payments:
		try:
			ref_raw = row.get("mes_de_referencia")
			if isinstance(ref_raw, str):
				ref_date = datetime.datetime.strptime(ref_raw, "%Y-%m-%d").date()
			else:
				ref_date = ref_raw
			if ref_date and ref_date.year == today.year and ref_date.month == today.month:
				current_month_open.append(row)
		except Exception:
			continue

	if not current_month_open:
		return

	# 7. Update each payment (status and increment value)
	updated = 0
	for row in current_month_open:
		try:
			new_value = (row.get("valor") or 0) + 10
			pay_doc = frappe.get_doc("Pagamento Contribuicao Mensal", row["name"])
			# Skip if already Atrasado (avoid double increment if function reruns)
			if pay_doc.status == "Atrasado":
				continue
			pay_doc.status = "Atrasado"
			pay_doc.valor = new_value
			pay_doc.save(ignore_permissions=True)  # triggers on_update
			updated += 1
		except Exception:
			continue

	frappe.db.commit()
	try:
		frappe.logger("pagamento_contribuicao_mensal").info(
			{
				"event": "update_status_monthly_payment",
				"updated": updated,
				"due_date": adjusted_due.isoformat(),
			}
		)
	except Exception:
		pass
