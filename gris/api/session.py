"""Session management for Gris portal.

Handles login redirects and session lifecycle events.
Part of the API layer for portal access control.
"""

import frappe


def redirect_to_inicio(login_manager):
	"""Redireciona usuários para /inicio após login.

	Args:
	    login_manager: Objeto de gerenciamento de login do Frappe

	Este hook é chamado no evento on_login.
	Redireciona todos os usuários para /inicio após o login bem-sucedido.
	"""
	# Define a página de destino após login
	if hasattr(frappe.local, "response"):
		frappe.local.response["home_page"] = "/inicio"
