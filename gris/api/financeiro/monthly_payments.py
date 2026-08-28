import datetime

import frappe

from gris.utils.job_logger import definir_resumo, metrica, obter_logger

REQUIRED_MANAGER_ROLE = "Gestor Contribuição Mensal"


def _assert_manager_role():
	roles = frappe.get_roles(frappe.session.user)
	if REQUIRED_MANAGER_ROLE not in roles:
		raise frappe.PermissionError("Requer acesso Gestor Contribuição Mensal para esta ação.")


def _assert_doc_permission(doctype: str, docname: str, perm_type: str = "write"):
	# Frappe has_permission params: doctype, ptype="read|write|submit|...", doc=doc_obj_or_name
	# Em algumas versões aceita docname/doc; garantimos doc carregado para avaliação fiel
	doc = frappe.get_doc(doctype, docname)
	if not frappe.has_permission(doctype, ptype=perm_type, doc=doc):
		raise frappe.PermissionError(f"Sem permissão {perm_type} em {doctype} {docname}")


def _first_day_of_month(date: datetime.date | None = None) -> datetime.date:
	date = date or datetime.date.today()
	return datetime.date(date.year, date.month, 1)


@frappe.whitelist()
def generate_monthly_payments():
	"""Create 'Em Aberto' payment records for all active beneficiary associates for current month.
	Idempotent per month.
	"""
	logger = obter_logger("pagamento_contribuicao_mensal")
	month_ref = _first_day_of_month()
	month_ref_str = month_ref.strftime("%Y-%m-%d")

	associates = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo", "categoria": "Beneficiário"},
		fields=["name", "valor_contribuicao"],
	)
	if not associates:
		logger.warning("Nenhum associado ativo beneficiario encontrado — nada a gerar.")
		definir_resumo(f"Nenhum associado beneficiário ativo para {month_ref_str}.")
		return 0

	logger.info(f"{len(associates)} associado(s) beneficiario(s) ativo(s) em {month_ref_str}.")

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
		logger.info(f"Contribuicao criada para {a.name} (R$ {a.valor_contribuicao or 0}).")

	metrica("criados", created, incrementar=False)
	metrica("ja_existentes", len(existing_set), incrementar=False)
	logger.info(
		f"Geracao mensal concluida para {month_ref_str}: {created} criada(s), "
		f"{len(existing_set)} ja existiam."
	)
	definir_resumo(
		f"{created} contribuição(ões) criada(s) para {month_ref_str} ({len(existing_set)} já existiam)."
	)
	return created


@frappe.whitelist()
def update_contribution_value(associate_id: str, new_value: float):
	"""Update Associate.valor_contribuicao."""
	_assert_manager_role()
	if not associate_id:
		raise frappe.ValidationError("Parameter 'associate_id' is required")
	try:
		new_value_f = float(new_value)
	except (TypeError, ValueError):
		raise frappe.ValidationError("Invalid value")
	if new_value_f < 0:
		raise frappe.ValidationError("Value cannot be negative")

	doc = frappe.get_doc("Associado", associate_id)
	_assert_doc_permission("Associado", associate_id, perm_type="write")
	doc.valor_contribuicao = new_value_f
	doc.save(ignore_permissions=False)
	return {"ok": True, "value": new_value_f}


@frappe.whitelist()
def mark_payment_as_paid(payment_id: str):
	"""Mark payment record as 'Pago'."""
	_assert_manager_role()
	if not payment_id:
		raise frappe.ValidationError("Parameter 'payment_id' is required")
	doc = frappe.get_doc("Pagamento Contribuicao Mensal", payment_id)
	_assert_doc_permission("Pagamento Contribuicao Mensal", payment_id, perm_type="write")
	if doc.status == "Pago":
		return {"ok": True, "status": doc.status}
	doc.status = "Pago"
	doc.save(ignore_permissions=False)
	return {"ok": True, "status": "Pago"}


@frappe.whitelist()
def activate_billing_status(associate_id: str):
	"""Mark associate's status_cobranca as 'Ativo'.

	Returns JSON { ok: True, previous: <old_status>, current: 'Ativo' }
	"""
	_assert_manager_role()
	if not associate_id:
		raise frappe.ValidationError("Parameter 'associate_id' is required")
	assoc = frappe.get_doc("Associado", associate_id)
	_assert_doc_permission("Associado", associate_id, perm_type="write")
	prev = assoc.get("status_cobranca")
	if prev == "Ativo":
		return {"ok": True, "previous": prev, "current": prev}
	assoc.status_cobranca = "Ativo"
	assoc.save(ignore_permissions=False)
	return {"ok": True, "previous": prev, "current": "Ativo"}


@frappe.whitelist()
def deactivate_billing_status(associate_id: str):
	"""Mark associate's status_cobranca as 'Inativo'.

	Returns JSON { ok: True, previous: <old_status>, current: 'Inativo' }
	"""
	_assert_manager_role()
	if not associate_id:
		raise frappe.ValidationError("Parameter 'associate_id' is required")
	assoc = frappe.get_doc("Associado", associate_id)
	_assert_doc_permission("Associado", associate_id, perm_type="write")
	prev = assoc.get("status_cobranca")
	if prev == "Inativo":
		return {"ok": True, "previous": prev, "current": prev}
	assoc.status_cobranca = "Inativo"
	assoc.save(ignore_permissions=False)
	return {"ok": True, "previous": prev, "current": "Inativo"}


@frappe.whitelist()
def update_billing_contacts(associate_id: str, email: str | None = None, phone: str | None = None):
	"""Update billing contact fields (email_cobranca, telefone_cobranca).

	Returns { ok: True, email: <value>, phone: <value> }
	"""
	_assert_manager_role()
	if not associate_id:
		raise frappe.ValidationError("Parameter 'associate_id' is required")
	assoc = frappe.get_doc("Associado", associate_id)
	_assert_doc_permission("Associado", associate_id, perm_type="write")
	# Basic sanitation (strip). Further validation (email format) could be added.
	if email is not None:
		assoc.email_cobranca = (email or "").strip() or None
	if phone is not None:
		assoc.telefone_cobranca = (phone or "").strip() or None
	assoc.save(ignore_permissions=False)
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
	logger = obter_logger("pagamento_contribuicao_mensal")

	# 1. Fetch configured due day (default 10 if missing / invalid)
	try:
		config = frappe.get_single("Configuracoes Contribuicao Mensal")
		due_day = int(getattr(config, "dia_vencimento", 10) or 10)
	except Exception:
		logger.warning("Nao foi possivel ler o dia de vencimento configurado; usando o padrao (10).")
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

	logger.info(f"Vencimento considerado para o mes: {adjusted_due.isoformat()}.")

	# 5. If still before or on adjusted due date, exit
	if today <= adjusted_due:
		logger.info("Ainda dentro do prazo — nenhum pagamento marcado como atrasado.")
		definir_resumo(f"Nada a fazer: o vencimento ({adjusted_due.isoformat()}) ainda não passou.")
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
			logger.warning(f"Mes de referencia invalido no pagamento {row.get('name')}; ignorado.")
			metrica("referencias_invalidas")
			continue

	if not current_month_open:
		logger.info("Nenhuma contribuicao em aberto do mes corrente apos o vencimento.")
		definir_resumo("Nenhuma contribuição em aberto para marcar como atrasada.")
		return

	logger.info(f"{len(current_month_open)} contribuicao(oes) em aberto a avaliar.")

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
			logger.info(
				f"Contribuicao {row['name']} ({row.get('associado')}) marcada como atrasada; "
				f"valor ajustado para R$ {new_value}."
			)
		except Exception:
			logger.exception(f"Falha ao marcar como atrasada a contribuicao {row.get('name')}.")
			metrica("falhas")
			continue

	metrica("marcados_como_atrasado", updated, incrementar=False)
	metrica("avaliados", len(current_month_open), incrementar=False)
	definir_resumo(
		f"{updated} contribuição(ões) marcada(s) como atrasada(s) (vencimento em {adjusted_due.isoformat()})."
	)
