"""Configuração de DocTypes nativos do Frappe (System/Website Settings, Email, Google, Social Login)."""

import frappe

from .credentials import get
from .safe_insert import safe_insert, set_single


def seed_system_settings(creds: dict):
	"""System Settings: localização, formato, segurança."""
	values = {
		"country": get(creds, "site", "default_country", default="Brazil"),
		"time_zone": get(creds, "site", "time_zone", default="America/Sao_Paulo"),
		"language": get(creds, "site", "language", default="pt-BR"),
		"date_format": get(creds, "site", "date_format", default="dd/mm/yyyy"),
		"number_format": get(creds, "site", "number_format", default="#.###,##"),
		"currency": get(creds, "site", "currency", default="BRL"),
	}
	# language pode causar erro se não estiver instalado — pular se vier vazio
	values = {k: v for k, v in values.items() if v}
	# set_single_value evita validações de campos que exijam currency/etc carregados
	for k, v in values.items():
		try:
			frappe.db.set_single_value("System Settings", k, v)
		except Exception as e:
			print(f"  ⚠️  System Settings.{k} = {v!r}: {e}")
	print("  → System Settings atualizado")


def seed_website_settings(creds: dict):
	"""Website Settings: home, copyright, footer."""
	web = get(creds, "site", "website", default={}) or {}
	values = {
		"home_page": web.get("home_page") or "index",
		"title_prefix": web.get("title_prefix") or "GRIS",
		"copyright": web.get("copyright") or "Grupo Escoteiro Professora Inah de Mello",
	}
	for k, v in values.items():
		try:
			frappe.db.set_single_value("Website Settings", k, v)
		except Exception as e:
			print(f"  ⚠️  Website Settings.{k}: {e}")
	print("  → Website Settings atualizado")


def seed_email_account(creds: dict):
	"""Email Account principal de saída (idempotente por email_id)."""
	cfg = get(creds, "frappe", "email_account", default={}) or {}
	email_id = cfg.get("email_id")
	if not email_id:
		print("  → (Email Account pulado: email_id vazio)")
		return

	if frappe.db.exists("Email Account", {"email_id": email_id}):
		print(f"  → Email Account '{email_id}' já existe")
		return

	doc_dict = {
		"doctype": "Email Account",
		"email_id": email_id,
		"email_account_name": cfg.get("email_account_name") or "Gris Notificacoes",
		"smtp_server": cfg.get("smtp_server") or "smtp.gmail.com",
		"smtp_port": str(cfg.get("smtp_port") or "587"),
		"use_tls": int(cfg.get("use_tls", 1)),
		"enable_outgoing": int(cfg.get("enable_outgoing", 1)),
		"default_outgoing": int(cfg.get("default_outgoing", 1)),
	}
	# password: só inclui se preenchido — caso contrário Frappe pode validar SMTP
	if cfg.get("password"):
		doc_dict["password"] = cfg["password"]
	# em ambiente de seed sem SMTP real, evitar tentar conectar
	doc_dict["awaiting_password"] = 0
	doc_dict["no_smtp_authentication"] = 1 if not cfg.get("password") else 0

	try:
		safe_insert(doc_dict)
		print(f"  → Email Account '{email_id}' criada")
	except Exception as e:
		print(f"  ⚠️  Email Account: {e}")


def seed_google_settings(creds: dict):
	"""Google Settings (Single): client_id, client_secret (Password), api_key."""
	cfg = get(creds, "frappe", "google_settings", default={}) or {}
	if not cfg:
		return
	set_single(
		"Google Settings",
		{
			"enable": int(cfg.get("enable", 0)),
			"client_id": cfg.get("client_id") or "",
			"client_secret": cfg.get("client_secret") or "",
			"api_key": cfg.get("api_key") or "",
			"app_id": cfg.get("app_id") or "",
		},
	)
	print("  → Google Settings atualizado")


def seed_google_drive(creds: dict):
	"""Google Drive (Single): backup config."""
	cfg = get(creds, "frappe", "google_drive", default={}) or {}
	if not cfg:
		return
	try:
		set_single(
			"Google Drive",
			{
				"enable": int(cfg.get("enable", 0)),
				"backup_folder_name": cfg.get("backup_folder_name") or "GrisBackup",
				"frequency": cfg.get("frequency") or "Weekly",
				"email": cfg.get("email") or "",
			},
		)
		print("  → Google Drive atualizado")
	except Exception as e:
		print(f"  ⚠️  Google Drive: {e}")


def seed_social_login_keys(creds: dict):
	"""Social Login Keys: provedores configurados."""
	keys = get(creds, "frappe", "social_login_keys", default=[]) or []
	for cfg in keys:
		provider_name = cfg.get("provider_name")
		if not provider_name:
			continue
		# Pular provedores desabilitados sem credenciais reais — evitam validação de URLs
		if not cfg.get("enable_social_login") and not cfg.get("client_secret"):
			print(f"  → Social Login Key '{provider_name}' pulado (não habilitado, sem segredo)")
			continue
		if frappe.db.exists("Social Login Key", provider_name):
			# atualiza
			doc = frappe.get_doc("Social Login Key", provider_name)
			doc.client_id = cfg.get("client_id") or doc.client_id
			if cfg.get("client_secret"):
				doc.client_secret = cfg["client_secret"]
			doc.enable_social_login = int(cfg.get("enable_social_login", 0))
			doc.sign_ups = cfg.get("sign_ups") or doc.sign_ups
			doc.save(ignore_permissions=True)
			print(f"  → Social Login Key '{provider_name}' atualizado")
		else:
			try:
				safe_insert(
					{
						"doctype": "Social Login Key",
						"provider_name": provider_name,
						"social_login_provider": cfg.get("social_login_provider") or "Custom",
						"enable_social_login": int(cfg.get("enable_social_login", 0)),
						"client_id": cfg.get("client_id") or "",
						"client_secret": cfg.get("client_secret") or "",
						"sign_ups": cfg.get("sign_ups") or "Allow",
					}
				)
				print(f"  → Social Login Key '{provider_name}' criado")
			except Exception as e:
				print(f"  ⚠️  Social Login Key '{provider_name}': {e}")


def seed_frappe_setup(creds: dict, _n: dict | None = None):
	"""Orquestra todas as configs nativas do Frappe."""
	print("[frappe_setup]")
	seed_system_settings(creds)
	seed_website_settings(creds)
	seed_email_account(creds)
	seed_google_settings(creds)
	seed_google_drive(creds)
	seed_social_login_keys(creds)
