import frappe


def after_install():
	# Define o template de boas vindas padrão no System Settings
	frappe.db.set_value("System Settings", "System Settings", "welcome_email_template", "Boas Vindas Gris")
