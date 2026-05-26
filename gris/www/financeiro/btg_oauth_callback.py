# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Endpoint de callback OAuth2 do BTG.

O BTG redireciona o admin para esta página após o login/consentimento,
com o parâmetro `?code=...` na URL.
A página troca o código por tokens e salva em Configuracao BTG Empresas.

Registrar no BTG Developer Console como redirect_uri:
  https://<seu-site>/financeiro/btg_oauth_callback
"""

import frappe

no_cache = 1


def get_context(context):
	# Restrito a usuários autenticados com role System Manager
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = (
			"/login?redirect-to=/financeiro/btg_oauth_callback"
			+ ("?" + frappe.request.query_string.decode() if frappe.request.query_string else "")
		)
		raise frappe.Redirect

	if "System Manager" not in frappe.get_roles():
		frappe.throw("Apenas System Manager pode autorizar a integração BTG.", frappe.PermissionError)

	code = frappe.request.args.get("code", "")
	error = frappe.request.args.get("error", "")
	error_description = frappe.request.args.get("error_description", "")

	context.success = False
	context.error_message = ""
	context.scope = ""

	if error:
		context.error_message = f"BTG retornou erro: {error}"
		if error_description:
			context.error_message += f" — {error_description}"
		return

	if not code:
		context.error_message = "Parâmetro 'code' ausente na URL de callback. Inicie o fluxo novamente."
		return

	try:
		from gris.api.financeiro.btg_auth import trocar_codigo_por_token

		result = trocar_codigo_por_token(code)
		context.success = True
		context.scope = result.get("scope", "")
	except Exception as exc:
		context.error_message = str(exc)
		frappe.log_error(frappe.get_traceback(), "BTG OAuth Callback")
