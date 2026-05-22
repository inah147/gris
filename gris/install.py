import frappe


def after_install():
	# Define o template de boas vindas padrão no System Settings
	frappe.db.set_value("System Settings", "System Settings", "welcome_email_template", "Boas Vindas Gris")
	_garantir_role_portaria()


def _garantir_role_portaria():
	"""Cria a role Portaria (usada por operadores da página /festas/portaria)."""
	if frappe.db.exists("Role", "Portaria"):
		return
	role = frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": "Portaria",
			"desk_access": 0,
			"home_page": "/festas/portaria",
		}
	)
	role.insert(ignore_permissions=True)
