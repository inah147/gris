import frappe


def after_install():
	# Define o template de boas vindas padrão no System Settings
	frappe.db.set_single_value("System Settings", "welcome_email_template", "Boas Vindas Gris")
	_garantir_role_portaria()
	_garantir_role_desenvolvedor()
	_garantir_role_acompanhamento_sugestoes()


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


def _garantir_role_desenvolvedor():
	"""Cria a role Desenvolvedor (quem tria e executa em /sugestoes/acompanhamento).

	Só quem tem esta role pode ser alocado como responsável por uma
	"Sugestao ou Problema" e mover cards no quadro.
	"""
	if frappe.db.exists("Role", "Desenvolvedor"):
		return
	role = frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": "Desenvolvedor",
			"desk_access": 0,
			"home_page": "/sugestoes/acompanhamento",
		}
	)
	role.insert(ignore_permissions=True)


def _garantir_role_acompanhamento_sugestoes():
	"""Cria a role Acompanhamento de Sugestoes (quem enxerga /sugestoes/acompanhamento).

	Submeter uma solicitação é liberado a qualquer usuário autenticado; ver o
	quadro exige esta role. Não usamos a role "All" do Frappe porque ela inclui
	Website User — no GRIS, os responsáveis — e exporia o quadro interno a eles.
	"""
	if frappe.db.exists("Role", "Acompanhamento de Sugestoes"):
		return
	role = frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": "Acompanhamento de Sugestoes",
			"desk_access": 0,
			"home_page": "/sugestoes/acompanhamento",
		}
	)
	role.insert(ignore_permissions=True)
