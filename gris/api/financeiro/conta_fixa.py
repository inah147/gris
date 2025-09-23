from __future__ import annotations

from datetime import date

import frappe
from frappe import _


def generate_monthly_fixed_payments():
	"""Create a monthly payment entry (Pagamento Conta Fixa) for each active fixed account.

	Runs ideally on the first day of the month (scheduled). The function is idempotent:
	If a payment record for the (account, current_month) already exists it will not create another.

	Rules:
	- Include every active continuous account (despesa_temporaria = 0 and ativa = 1)
	- Include every active temporary account (despesa_temporaria = 1 and ativa = 1) whose
	  data_inicio is on or before the first day of the current month and whose data_termino
	  is on or after the first day of the current month.
	"""
	# Current month first day
	today = date.today()
	month_start = today.replace(day=1)

	# We'll store YYYY-MM as a filterable string; Pagamento Conta Fixa has field mes_referencia (Date)
	# We insert with mes_referencia = month_start

	# Continuous active accounts
	continuous = frappe.get_all(
		"Conta Fixa",
		filters={
			"ativa": 1,
			"despesa_temporaria": 0,
		},
		fields=["name"],
	)

	# Temporary accounts active in this month
	# Condition: ativa=1 AND despesa_temporaria=1 AND data_inicio <= month_start AND data_termino >= month_start
	temporary = frappe.get_all(
		"Conta Fixa",
		filters={
			"ativa": 1,
			"despesa_temporaria": 1,
			"data_inicio": ("<=", month_start),
			"data_termino": (">=", month_start),
		},
		fields=["name"],
	)

	accounts = [r["name"] for r in continuous] + [r["name"] for r in temporary]
	if not accounts:
		return 0

	created = 0
	for acc in accounts:
		# Idempotency check
		exists = frappe.db.exists(
			"Pagamento Conta Fixa",
			{"conta": acc, "mes_referencia": month_start},
		)
		if exists:
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Pagamento Conta Fixa",
				"conta": acc,
				"mes_referencia": month_start,
				"status": "Em Aberto",
			}
		)
		doc.insert(ignore_permissions=True)
		created += 1
	if created:
		frappe.db.commit()
	return created


@frappe.whitelist()
def update_conta_fixa(
	name: str,
	descricao: str | None = None,
	valor: float | None = None,
	dia_vencimento: int | None = None,
	ativa: int | None = None,
	despesa_temporaria: int | None = None,
	data_inicio: str | None = None,
	data_termino: str | None = None,
):
	if frappe.session.user == "Guest":
		frappe.throw(_("Não autenticado"))
	# Permissão de role
	if "Gestor Financeiro" not in frappe.get_roles():
		frappe.throw(_("Sem permissão para editar"), frappe.PermissionError)
	doc = frappe.get_doc("Conta Fixa", name)
	changed = False
	if descricao is not None:
		doc.descricao = descricao
		changed = True
	if valor is not None:
		try:
			doc.valor = float(valor)
			changed = True
		except ValueError:
			frappe.throw(_("Valor inválido"))
	if dia_vencimento is not None:
		doc.dia_vencimento = int(dia_vencimento)
		changed = True
	if ativa is not None:
		doc.ativa = 1 if int(ativa) else 0
		changed = True
	if despesa_temporaria is not None:
		doc.despesa_temporaria = 1 if int(despesa_temporaria) else 0
		changed = True
	if data_inicio is not None:
		doc.data_inicio = data_inicio or None
		changed = True
	if data_termino is not None:
		doc.data_termino = data_termino or None
		changed = True

	# Valida datas obrigatórias se temporária
	if doc.despesa_temporaria:
		if not doc.data_inicio or not doc.data_termino:
			frappe.throw(_("Para despesa temporária, 'data_inicio' e 'data_termino' são obrigatórias"))
		# Comparação simples (strings ISO YYYY-MM-DD ordenam lexicograficamente)
		if str(doc.data_inicio) > str(doc.data_termino):
			frappe.throw(_("'data_inicio' não pode ser maior que 'data_termino'"))
	if changed:
		doc.save(ignore_permissions=False)
		frappe.db.commit()
	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def get_pagamentos_conta(conta: str, limit: int = 12):
	"""Retorna histórico (até 'limit' meses) de pagamentos da Conta Fixa.

	Args:
		conta: name da Conta Fixa
		limit: número máximo de registros (default 12)

	Returns: lista de dicts {mes_referencia, status}
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Não autenticado"))
	# Permitir leitura para qualquer usuário que já acessa a página (mesmo sem perm de editar)
	res = frappe.get_all(
		"Pagamento Conta Fixa",
		filters={"conta": conta},
		fields=["name", "mes_referencia", "status"],
		order_by="mes_referencia DESC",
		limit=limit,
	)
	# Formata data para YYYY-MM (ou DD/MM/YYYY se preferir completo)
	for r in res:
		if r.get("mes_referencia"):
			r["mes_format"] = r.mes_referencia.strftime("%Y-%m")
	return res


@frappe.whitelist()
def marcar_pagamento_pago(pagamento: str):
	"""Marca um registro de Pagamento Conta Fixa como Pago.

	Somente para role Gestor Financeiro.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Não autenticado"))
	if "Gestor Financeiro" not in frappe.get_roles():
		frappe.throw(_("Sem permissão"), frappe.PermissionError)
	doc = frappe.get_doc("Pagamento Conta Fixa", pagamento)
	if doc.status == "Pago":
		return {"ok": True, "status": doc.status}
	doc.status = "Pago"
	doc.save(ignore_permissions=False)
	frappe.db.commit()
	return {"ok": True, "status": doc.status}


@frappe.whitelist()
def create_conta_fixa(
	descricao: str,
	valor: float,
	dia_vencimento: int,
	ativa: int = 1,
	despesa_temporaria: int = 0,
	data_inicio: str | None = None,
	data_termino: str | None = None,
):
	"""Cria uma nova Conta Fixa.

	Requer role Gestor Financeiro.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Não autenticado"))
	if "Gestor Financeiro" not in frappe.get_roles():
		frappe.throw(_("Sem permissão"), frappe.PermissionError)
	if not descricao:
		frappe.throw(_("Descrição é obrigatória"))
	try:
		valor_f = float(valor)
	except ValueError:
		frappe.throw(_("Valor inválido"))
	dia = int(dia_vencimento)
	if dia < 1 or dia > 31:
		frappe.throw(_("Dia de vencimento inválido"))
	temp = 1 if int(despesa_temporaria) else 0
	if temp:
		if not data_inicio or not data_termino:
			frappe.throw(_("Para despesa temporária, datas de início e término são obrigatórias"))
		if str(data_inicio) > str(data_termino):
			frappe.throw(_("Data de início não pode ser maior que data de término"))
	doc = frappe.get_doc(
		{
			"doctype": "Conta Fixa",
			"descricao": descricao,
			"valor": valor_f,
			"dia_vencimento": dia,
			"ativa": 1 if int(ativa) else 0,
			"despesa_temporaria": temp,
			"data_inicio": data_inicio if temp else None,
			"data_termino": data_termino if temp else None,
		}
	)
	doc.insert(ignore_permissions=False)
	frappe.db.commit()
	return {"ok": True, "name": doc.name}
