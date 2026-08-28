import frappe

from gris.api.portal_access import enrich_context, pode_conciliar
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

	# Mantém o destaque do menu em Contas
	context.active_link = "/financeiro/contas"

	# Enriquecer contexto (menus, barras mobile, etc.)
	enrich_context(context, "/financeiro/contas")

	# Flag de permissão para exibir/ocultar ações de upload/conciliação
	context.can_reconcile_intinitepay = pode_conciliar(
		"Transacao Infinitepay extrato",
		"Transacao Infinitepay vendas",
		"Transacao Infinitepay recebimento",
		"Transacao Extrato Geral",
	)

	# Opcional: disponibiliza no boot (para acesso fácil no JS global)
	try:
		if not hasattr(frappe, "boot") or not frappe.boot:
			frappe.local.boot = getattr(frappe.local, "boot", None) or frappe._dict()
		frappe.local.boot["can_reconcile_intinitepay"] = context.can_reconcile_intinitepay
	except Exception:
		pass

	return context
