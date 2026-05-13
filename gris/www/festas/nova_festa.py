from __future__ import annotations

import json

import frappe
from frappe.utils import get_time, getdate

from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1

ALLOWED_ROLES = {"Gestor de festas", "System Manager"}


def _ensure_gestor_access() -> None:
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & ALLOWED_ROLES):
		frappe.throw(
			"Você não tem permissão para cadastrar festas.", frappe.PermissionError
		)


def _select_items_associados() -> list[dict[str, str]]:
	registros = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo"},
		fields=["name", "nome_completo"],
		order_by="nome_completo asc",
	)
	return [
		{
			"label": (r.nome_completo or r.name),
			"value": r.name,
			"type": "item",
		}
		for r in registros
	]


def _select_items_responsaveis() -> list[dict[str, str]]:
	registros = frappe.get_all(
		"Responsavel",
		fields=["name", "nome_completo"],
		order_by="nome_completo asc",
	)
	return [
		{
			"label": (r.nome_completo or r.name),
			"value": r.name,
			"type": "item",
		}
		for r in registros
	]


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/festas/nova_festa"
		raise frappe.Redirect

	_ensure_gestor_access()

	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"

	context.active_link = "/festas/nova_festa"
	context.associados_items = _select_items_associados()
	context.responsaveis_items = _select_items_responsaveis()
	enrich_context(context, "/festas/nova_festa")
	return context


@frappe.whitelist()
def criar_festa(payload):
	_ensure_gestor_access()

	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except ValueError:
			frappe.throw("Dados invalidos.")

	if not isinstance(payload, dict):
		frappe.throw("Dados invalidos.")

	nome = (payload.get("nome_festa") or "").strip()
	if len(nome) < 3:
		frappe.throw("Informe um nome de festa com pelo menos 3 caracteres.")

	if frappe.db.exists("Festa", nome):
		frappe.throw(f"Ja existe uma festa com o nome '{nome}'.")

	data_raw = (payload.get("data") or "").strip()
	if not data_raw:
		frappe.throw("Informe a data da festa.")
	try:
		data_festa = getdate(data_raw)
	except Exception:
		frappe.throw("Data invalida.")

	horario_inicio_raw = (payload.get("horario_inicio") or "").strip() or None
	horario_termino_raw = (payload.get("horario_termino") or "").strip() or None
	horario_inicio = get_time(horario_inicio_raw) if horario_inicio_raw else None
	horario_termino = get_time(horario_termino_raw) if horario_termino_raw else None

	if horario_inicio and horario_termino and horario_termino <= horario_inicio:
		frappe.throw("O horario de termino deve ser posterior ao de inicio.")

	tipo_coord = (payload.get("tipo_coord_geral") or "").strip()
	if tipo_coord not in {"Responsavel", "Associado"}:
		frappe.throw("Selecione o tipo de coordenador.")

	coordenador = (payload.get("coordenador") or "").strip()
	if not coordenador:
		frappe.throw("Selecione o coordenador da festa.")

	doc = frappe.new_doc("Festa")
	doc.nome_festa = nome
	doc.data = data_festa
	doc.horario_inicio = horario_inicio
	doc.horario_termino = horario_termino
	doc.status = "Em andamento"
	doc.tipo_coord_geral = tipo_coord
	if tipo_coord == "Responsavel":
		if not frappe.db.exists("Responsavel", coordenador):
			frappe.throw("Responsavel selecionado nao existe.")
		doc.responsavel_coord_geral = coordenador
	else:
		if not frappe.db.exists("Associado", coordenador):
			frappe.throw("Associado selecionado nao existe.")
		doc.associado_coord_geral = coordenador

	doc.insert()

	return {"name": doc.name, "redirect": "/festas/todas_festas"}
