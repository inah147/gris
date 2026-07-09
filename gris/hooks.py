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
app_include_js = "/assets/gris/js/pwa-init.js"

# include js, css files in header of web template
web_include_js = "/assets/gris/js/pwa-init.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "gris/public/scss/website"

# PWA: Use custom base template with PWA meta tags
base_template = "templates/base.html"

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
jinja = {
	"methods": [
		"gris.utils.phone_countries.get_phone_countries",
	],
}

# Installation
# ------------

# before_install = "gris.install.before_install"
after_install = "gris.install.after_install"

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

permission_query_conditions = {
	"Board": "gris.gris.doctype.board.board_permissions.board_permission_query_conditions",
	"Gestao de Tarefas": "gris.gris.doctype.board.board_permissions.gestao_de_tarefas_permission_query_conditions",
}

has_permission = {
	"Board": "gris.gris.doctype.board.board_permissions.board_has_permission",
	"Gestao de Tarefas": "gris.gris.doctype.board.board_permissions.gestao_de_tarefas_has_permission",
}

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Cobranca Infinitepay": {
		"on_update": [
			"gris.festas.doctype.convite_festa.convite_festa.on_cobranca_atualizada",
		],
	},
	"User": {
		"after_insert": [
			"gris.gestao_de_tarefas.user_board.criar_board_pessoal",
		],
	},
	"Projeto": {
		"on_update": [
			"gris.gestao_de_tarefas.board_sync.sync_projeto_envolvidos",
		],
	},
	"Festa": {
		"after_insert": [
			"gris.api.festas.avaliacao.criar_avaliacao_festa_automatica",
		],
		"on_update": [
			"gris.gestao_de_tarefas.board_sync_festa.sync_from_festa",
		],
	},
	"Area da Festa": {
		"after_insert": [
			"gris.gestao_de_tarefas.board_sync_festa.sync_from_area",
		],
		"on_update": [
			"gris.gestao_de_tarefas.board_sync_festa.sync_from_area",
		],
	},
	"Barraca da Festa": {
		"after_insert": [
			"gris.gestao_de_tarefas.board_sync_festa.sync_from_barraca",
		],
		"on_update": [
			"gris.gestao_de_tarefas.board_sync_festa.sync_from_barraca",
		],
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"cron": {
		"0 3 * * *": ["gris.gris.doctype.gestao_de_tarefas.gestao_de_tarefas.validar_tarefas_atrasadas"],
		"0 5 * * *": ["gris.api.users.user_manager.manage_associate_users"],
		"0 9 * * *": [
			"gris.gestao_de_projetos.doctype.projeto.projeto.enviar_lembretes_whatsapp_aprovacao_projetos",
			"gris.api.associados_notificacoes.enviar_lembrete_atualizacao_associados",
			"gris.api.associados_vencimento_notificacoes.enviar_lembretes_vencimento_registro_associados",
		],
	},
	# "all": [
	# 	"gris.tasks.all"
	# ],
	"daily": [
		"gris.api.financeiro.monthly_payments.update_status_monthly_payment",
		"gris.api.new_members.waiting_list.update_waiting_list_branch",
		"gris.api.calendario.sync_feriados.sync_feriados",
		"gris.api.backup.google_shared_drive.enqueue_daily_backup",
		"gris.api.google_workspace.access_manager.enqueue_daily_global_access_sync",
		"gris.api.google_workspace.access_manager.enqueue_daily_restricted_access_cleanup",
		"gris.api.google_workspace.access_manager.enqueue_daily_inactive_access_cleanup",
		"gris.api.recepcao_notificacoes.enviar_lembretes_visita",
		"gris.festas.doctype.festa.festa.marcar_festas_realizadas",
		"gris.festas.doctype.opcao_convite_festa.opcao_convite_festa.atualizar_lotes_opcoes_convite",
	],
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
override_whitelisted_methods = {
	"frappe.core.doctype.user.user.update_password": "gris.api.auth.update_password",
	# "frappe.desk.doctype.event.event.get_events": "gris.event.get_events"
}
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
before_request = ["gris.api.auth.enforce_no_desk_redirect"]
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
					"Editor de projetos",
					"Equipe de Metodos",
					"Gestor Contribuição Mensal",
					"Gestor de Adultos",
					"Gestor de Associados",
					"Gestor Financeiro",
					"Gestor de Metodos",
					"Visualizador Associados",
					"Visualizador de projetos",
					"Visualizador Contribuição Mensal",
					"Visualizador Financeiro",
					"Gestor da UEL",
					"Acesso ao Desk",
					"Visualizador Calendario",
					"Gestor Calendario",
					"Editor Calendario",
					"Recepcao",
					"Responsavel",
					"Gestor de festas",
					"Visualizador de festas",
					"Portaria",
				],
			]
		],
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
	{
		"dt": "Email Template",
	},
	{
		"dt": "Mapeamento de perguntas e respostas da entrevista",
	},
	{
		"dt": "ODS Projeto",
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

update_website_context = [
	"gris.api.gestao_de_tarefas.minhas_tarefas.context_inject",
]
