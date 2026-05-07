"""Carregamento de credenciais do .credentials YAML do app gris."""

from pathlib import Path

import frappe
import yaml


def load_credentials() -> dict:
	"""
	Carrega o arquivo .credentials do app gris.

	Se .credentials não existir, cai pro .credentials.example com aviso —
	útil em CI/dev sem secrets configurados, onde valores stub bastam.
	"""
	app_path = Path(frappe.get_app_path("gris")).parent  # apps/gris/
	creds_file = app_path / ".credentials"
	example_file = app_path / ".credentials.example"

	if creds_file.exists():
		source = creds_file
	elif example_file.exists():
		print(f"⚠️  {creds_file} não encontrado, usando {example_file} (stubs)")
		source = example_file
	else:
		print("⚠️  Nem .credentials nem .credentials.example encontrados, usando dict vazio")
		return {}

	with open(source, encoding="utf-8") as f:
		data = yaml.safe_load(f) or {}

	return data


def get(creds: dict, *path, default=None):
	"""
	Acessa caminho aninhado em dict de credenciais com default seguro.

	Ex.: get(creds, "frappe", "google_settings", "client_id", default="")
	"""
	cur = creds
	for key in path:
		if not isinstance(cur, dict) or key not in cur:
			return default
		cur = cur[key]
	return cur if cur is not None else default
