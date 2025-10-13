app_name = "gris"
app_title = "Gris"
app_publisher = "Grupo Escoteiro Professora Inah de Mello - 47/SP"
app_description = "App base para gestão complementar de Grupos Escoteiros"
app_email = "tecnologia@gepim.com.br"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "gris",
# 		"logo": "/assets/gris/logo.png",
# 		"title": "Gris",
# 		"route": "/gris",
# 		"has_permission": "gris.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/gris/css/gris.css"
# app_include_js = "/assets/gris/js/gris.js"

# include js, css files in header of web template
# web_include_css = "/assets/gris/css/gris.css"
# web_include_js = "/assets/gris/js/gris.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "gris/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "gris/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
home_page = "/inicio"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "gris.utils.jinja_methods",
# 	"filters": "gris.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "gris.install.before_install"
# after_install = "gris.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "gris.uninstall.before_uninstall"
# after_uninstall = "gris.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "gris.utils.before_app_install"
# after_app_install = "gris.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "gris.utils.before_app_uninstall"
# after_app_uninstall = "gris.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "gris.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"Cron": {"0 5 * * *": ["gris.api.users.user_manager.manage_associate_users"]},
	# "all": [
	# 	"gris.tasks.all"
	# ],
	"daily": ["gris.api.financeiro.monthly_payments.update_status_monthly_payment"],
	# "hourly": [
	# 	"gris.tasks.hourly"
	# ],
	# "weekly": [
	# 	"gris.tasks.weekly"
	# ],
	"monthly": [
		"gris.api.financeiro.monthly_payments.generate_monthly_payments",
		"gris.api.financeiro.conta_fixa.generate_monthly_fixed_payments",
	],
}

# Testing
# -------

# before_tests = "gris.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "gris.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "gris.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["gris.utils.before_request"]
# after_request = ["gris.utils.after_request"]

# Job Events
# ----------
# before_job = ["gris.utils.before_job"]
# after_job = ["gris.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"gris.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }


# Fixtures
# --------

fixtures = [
	{
		"dt": "Role Profile",
	},
	{
		"dt": "Role",
		"filters": [
			[
				"name",
				"in",
				[
					"Editor de Parecer",
					"Gestor Contribuição Mensal",
					"Gestor de Adultos",
					"Gestor de Associados",
					"Gestor Financeiro",
					"Visualizador Associados",
					"Visualizador Contribuição Mensal",
					"Visualizador Financeiro",
					"Gestor da UEL",
					"Acesso ao Desk",
				],
			]
		],
	},
	{
		"dt": "Carteira",
	},
	{
		"dt": "Instituicao Financeira",
	},
	{
		"dt": "Centro de Custo",
	},
	{
		"dt": "Categoria de Transacao",
	},
	{
		"dt": "Unidade Organizacional",
	},
]


# Contexto global para o site (sidebar centralizada)
# website_context = {
# 	"associados_subitems": [
# 		{"label": "Visão Geral", "href": "/associados"},
# 		{"label": "Lista de Associados", "href": "/app/associado"},
# 		{"label": "Novo Associado", "href": "/app/associado/new"},
# 		{"label": "Relatório Ativos", "href": "/app/query-report/Associados Ativos"},
# 	]
# }
