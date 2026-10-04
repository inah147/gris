import datetime

import frappe
from frappe import _

from gris.api.financeiro.contribuicoes import (
	calcular_vencimento,
	get_datas_de_ingresso,
	get_parametros,
	resolver_inicio_do_pagamento,
)
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
		fields=["name", "valor_contribuicao", "tipo_registro", "inicio_do_pagamento"],
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

	# Carência: quem ainda não chegou ao início do pagamento não ganha registro do mês.
	parametros = get_parametros()
	ingressos = get_datas_de_ingresso([a.name for a in associates])

	created = 0
	em_carencia = 0
	for a in associates:
		if a.name in existing_set:
			continue
		inicio = resolver_inicio_do_pagamento(
			{
				"inicio_do_pagamento": a.inicio_do_pagamento,
				"tipo_registro": a.tipo_registro,
				"data_de_ingresso": ingressos.get(a.name),
			},
			parametros,
		)
		if inicio and inicio > month_ref:
			em_carencia += 1
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
	metrica("em_carencia", em_carencia, incrementar=False)
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


STATUS_VALIDOS = ("Pago", "Em Aberto", "Atrasado")


@frappe.whitelist()
def definir_pagamento(
	associado: str,
	mes_de_referencia: str | datetime.date,
	status: str | None = None,
	valor: float | None = None,
	atrasou: bool | int | None = None,
	transacao_extrato: str | None = None,
):
	"""Cria ou atualiza o Pagamento Contribuicao Mensal de um mês, e devolve o registro.

	Usado tanto pela tela (trocar status, vincular a transação certa) quanto pelo
	MCP: sempre que o mês ainda não tem registro gerado ("Não gerado" na tela),
	esta é a porta para criar um direto, sem esperar o scheduler mensal.
	"""
	_assert_manager_role()
	if not associado:
		raise frappe.ValidationError("Parameter 'associado' is required")

	mes = frappe.utils.getdate(mes_de_referencia).replace(day=1)

	if status is not None and status not in STATUS_VALIDOS:
		frappe.throw(_("Status inválido: {0}. Use um de {1}.").format(status, ", ".join(STATUS_VALIDOS)))
	if transacao_extrato and not frappe.db.exists("Transacao Extrato Geral", transacao_extrato):
		frappe.throw(_("Transação '{0}' não encontrada.").format(transacao_extrato))

	existentes = frappe.get_all(
		"Pagamento Contribuicao Mensal",
		filters={"associado": associado, "mes_de_referencia": mes},
		limit=1,
	)
	if existentes:
		doc = frappe.get_doc("Pagamento Contribuicao Mensal", existentes[0].name)
		_assert_doc_permission("Pagamento Contribuicao Mensal", doc.name, perm_type="write")
	else:
		_assert_doc_permission("Associado", associado, perm_type="read")
		doc = frappe.new_doc("Pagamento Contribuicao Mensal")
		doc.associado = associado
		doc.mes_de_referencia = mes
		doc.status = "Em Aberto"
		doc.valor = frappe.db.get_value("Associado", associado, "valor_contribuicao") or 0

	if status is not None:
		doc.status = status
	if valor is not None:
		valor_f = float(valor)
		if valor_f < 0:
			frappe.throw(_("O valor não pode ser negativo."))
		doc.valor = valor_f
	if atrasou is not None:
		doc.atrasou = 1 if frappe.utils.cint(atrasou) else 0
	if transacao_extrato is not None:
		doc.transacao_extrato = transacao_extrato or None

	if doc.is_new():
		doc.insert(ignore_permissions=False)
	else:
		doc.save(ignore_permissions=False)

	return {
		"ok": True,
		"name": doc.name,
		"status": doc.status,
		"valor": doc.valor,
		"atrasou": bool(doc.atrasou),
		"transacao_extrato": doc.transacao_extrato,
	}


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


@frappe.whitelist()
def update_status_monthly_payment() -> None:
	atualizar_status_pagamentos()


def atualizar_status_pagamentos(hoje: datetime.date | None = None) -> int:
	"""Marca como "Atrasado" todo mês "Em Aberto" cujo vencimento já passou.

	Alcança qualquer mês de referência, não só o corrente. Na transição soma o
	acréscimo de atraso ao valor (e o guarda em `acrescimo_atraso`) quando o mês
	está dentro de `acrescimo_automatico_desde`. Como só age em "Em Aberto", rodar
	de novo não soma duas vezes.
	"""
	logger = obter_logger("pagamento_contribuicao_mensal")
	hoje = hoje or datetime.date.today()
	parametros = get_parametros()
	desde = frappe.db.get_single_value(
		"Configuracoes Contribuicao Mensal", "acrescimo_automatico_desde", cache=False
	)
	desde = frappe.utils.getdate(desde) if desde else None
	# Singles guarda a data apagada como "", que o Frappe lê como 0001-01-01.
	if desde and desde.year < 2000:
		desde = None
	acrescimo = parametros.acrescimo_atraso

	em_aberto = frappe.get_all(
		"Pagamento Contribuicao Mensal",
		filters={"status": "Em Aberto", "mes_de_referencia": ["<=", hoje]},
		fields=["name", "associado", "mes_de_referencia", "valor"],
		limit_page_length=0,
	)

	atualizados = 0
	for row in em_aberto:
		try:
			mes = frappe.utils.getdate(row["mes_de_referencia"])
		except Exception:
			logger.warning(f"Mes de referencia invalido no pagamento {row.get('name')}; ignorado.")
			metrica("referencias_invalidas")
			continue
		vencimento = calcular_vencimento(mes, parametros.dia_vencimento)
		if hoje <= vencimento:
			continue
		try:
			pay_doc = frappe.get_doc("Pagamento Contribuicao Mensal", row["name"])
			if pay_doc.status != "Em Aberto":
				continue
			pay_doc.status = "Atrasado"
			pay_doc.atrasou = 1
			if desde and acrescimo > 0 and mes >= desde:
				pay_doc.acrescimo_atraso = acrescimo
				pay_doc.valor = round(float(pay_doc.valor or 0) + acrescimo, 2)
			pay_doc.save(ignore_permissions=True)  # triggers on_update
			atualizados += 1
			logger.info(f"Contribuicao {row['name']} ({row.get('associado')}) marcada como atrasada.")
		except Exception:
			logger.exception(f"Falha ao marcar como atrasada a contribuicao {row.get('name')}.")
			metrica("falhas")
			continue

	metrica("marcados_como_atrasado", atualizados, incrementar=False)
	metrica("avaliados", len(em_aberto), incrementar=False)
	definir_resumo(f"{atualizados} contribuição(ões) marcada(s) como atrasada(s) em {hoje.isoformat()}.")
	return atualizados
