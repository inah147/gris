from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import frappe
from frappe.utils import cint
from googleapiclient.errors import HttpError

from gris.api.google_workspace.access_manager import _execute_with_retry, _get_google_drive_service

SETTINGS_DOCTYPE = "Configuracoes de Projetos"
PROJECT_DOCTYPE = "Projeto"
FOLDER_MIMETYPE = "application/vnd.google-apps.folder"
MAX_CREATE_ATTEMPTS = 3

_FOLDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def _logger():
	return frappe.logger("google_workspace_project_drive", allow_site=True, file_count=10)


def is_valid_drive_folder_link(value: str | None) -> bool:
	text = (value or "").strip()
	if not text:
		return False

	parsed = urlparse(text)
	if parsed.scheme != "https":
		return False
	if parsed.netloc.lower() != "drive.google.com":
		return False

	return bool(extract_drive_folder_id(text))


def extract_drive_folder_id(value: str | None) -> str:
	text = (value or "").strip()
	if not text:
		return ""

	parsed = urlparse(text)
	path_parts = [part for part in (parsed.path or "").split("/") if part]
	folder_id = ""

	if "folders" in path_parts:
		folders_index = path_parts.index("folders")
		if folders_index + 1 < len(path_parts):
			folder_id = path_parts[folders_index + 1]
	elif path_parts[:2] == ["drive", "folders"] and len(path_parts) >= 3:
		folder_id = path_parts[2]

	if not folder_id:
		query_values = parse_qs(parsed.query or "")
		folder_id = (query_values.get("id") or [""])[0]

	folder_id = folder_id.strip()
	if not _FOLDER_ID_PATTERN.fullmatch(folder_id):
		return ""
	return folder_id


def build_drive_folder_link(folder_id: str) -> str:
	return f"https://drive.google.com/drive/folders/{folder_id}"


def create_project_folder_async(projeto_name: str, attempt: int = 1) -> dict[str, str | int]:
	if not projeto_name or not frappe.db.exists(PROJECT_DOCTYPE, projeto_name):
		return {"status": "project_not_found"}

	settings = _get_project_settings()
	if not _is_feature_enabled(settings):
		return {"status": "disabled"}

	parent_folder_id = (settings.pasta_projetos_id or "").strip()
	drive_id = (settings.drive_compartilhado_projetos or "").strip()
	if not parent_folder_id or not drive_id:
		_logger().warning(
			"[PROJECT DRIVE] missing settings projeto=%s parent=%s drive=%s",
			projeto_name,
			bool(parent_folder_id),
			bool(drive_id),
		)
		return {"status": "missing_settings"}

	doc = frappe.get_doc(PROJECT_DOCTYPE, projeto_name)
	current_link = (doc.get("link_pasta_google_drive") or "").strip()
	if current_link and extract_drive_folder_id(current_link):
		return {"status": "already_linked"}

	folder_name = (doc.get("nome_do_projeto") or "").strip() or projeto_name

	try:
		drive = _get_google_drive_service()
		existing_folder = _find_existing_project_folder(
			drive=drive,
			settings=settings,
			parent_folder_id=parent_folder_id,
			folder_name=folder_name,
		)
		folder_id = (existing_folder or {}).get("id") or ""
		if not folder_id:
			created_folder = _create_project_folder(
				drive=drive,
				parent_folder_id=parent_folder_id,
				folder_name=folder_name,
				projeto_name=projeto_name,
			)
			folder_id = (created_folder or {}).get("id") or ""

		if not folder_id:
			raise frappe.ValidationError("Nao foi possivel determinar o ID da pasta do projeto.")

		_update_project_drive_link(projeto_name, build_drive_folder_link(folder_id))
		return {"status": "ok", "folder_id": folder_id, "attempt": attempt}
	except Exception:
		tb = frappe.get_traceback()
		frappe.log_error(tb, f"create_project_folder_async:{projeto_name}")
		_logger().error("[PROJECT DRIVE] create failed projeto=%s attempt=%s\n%s", projeto_name, attempt, tb)
		_schedule_create_retry_if_needed(projeto_name, attempt)
		return {"status": "error", "attempt": attempt}


def cleanup_project_folder_if_empty_async(projeto_name: str) -> dict[str, str]:
	if not projeto_name or not frappe.db.exists(PROJECT_DOCTYPE, projeto_name):
		return {"status": "project_not_found"}

	settings = _get_project_settings()
	if not _is_feature_enabled(settings):
		return {"status": "disabled"}

	parent_folder_id = (settings.pasta_projetos_id or "").strip()
	drive_id = (settings.drive_compartilhado_projetos or "").strip()
	if not parent_folder_id or not drive_id:
		return {"status": "missing_settings"}

	doc = frappe.get_doc(PROJECT_DOCTYPE, projeto_name)
	link = (doc.get("link_pasta_google_drive") or "").strip()
	if not link:
		return {"status": "no_link"}

	folder_id = extract_drive_folder_id(link)
	if not folder_id:
		_logger().warning("[PROJECT DRIVE] invalid folder link projeto=%s link=%s", projeto_name, link)
		return {"status": "invalid_link"}

	try:
		drive = _get_google_drive_service()

		if not _folder_belongs_to_projects_root(drive, folder_id, parent_folder_id):
			_logger().warning(
				"[PROJECT DRIVE] cleanup skipped (out of projects root) projeto=%s folder=%s",
				projeto_name,
				folder_id,
			)
			return {"status": "out_of_scope"}

		if not _is_folder_empty(drive, settings, folder_id):
			return {"status": "not_empty"}

		delete_result = _delete_folder_idempotent(drive, folder_id)
		if delete_result in {"deleted", "already_missing"}:
			_update_project_drive_link(projeto_name, "")

		return {"status": delete_result}
	except Exception:
		tb = frappe.get_traceback()
		frappe.log_error(tb, f"cleanup_project_folder_if_empty_async:{projeto_name}")
		_logger().error("[PROJECT DRIVE] cleanup failed projeto=%s\n%s", projeto_name, tb)
		return {"status": "error"}


def _schedule_create_retry_if_needed(projeto_name: str, attempt: int) -> None:
	if attempt >= MAX_CREATE_ATTEMPTS:
		return
	if not frappe.db.exists(PROJECT_DOCTYPE, projeto_name):
		return

	next_attempt = attempt + 1
	frappe.enqueue(
		"gris.api.google_workspace.project_drive.create_project_folder_async",
		queue="long",
		timeout=300,
		job_name=f"{frappe.local.site}:project-drive-create:{projeto_name}:{next_attempt}",
		projeto_name=projeto_name,
		attempt=next_attempt,
	)


def _create_project_folder(drive, parent_folder_id: str, folder_name: str, projeto_name: str) -> dict:
	return _execute_with_retry(
		lambda: (
			drive.files()
			.create(
				body={
					"name": folder_name,
					"mimeType": FOLDER_MIMETYPE,
					"parents": [parent_folder_id],
					"description": f"Pasta do projeto {projeto_name}",
				},
				fields="id,name,createdTime",
				supportsAllDrives=True,
			)
			.execute()
		)
	)


def _find_existing_project_folder(drive, settings, parent_folder_id: str, folder_name: str) -> dict | None:
	escaped_name = _escape_drive_query_value(folder_name)
	query = (
		f"'{parent_folder_id}' in parents and trashed = false and "
		f"mimeType = '{FOLDER_MIMETYPE}' and name = '{escaped_name}'"
	)
	params = {
		"q": query,
		"fields": "files(id,name,createdTime)",
		"pageSize": 1,
		"supportsAllDrives": True,
		"includeItemsFromAllDrives": True,
	}
	params.update(_get_drive_scope_params(settings))

	response = _execute_with_retry(lambda: drive.files().list(**params).execute())
	files = response.get("files") or []
	return files[0] if files else None


def _is_folder_empty(drive, settings, folder_id: str) -> bool:
	query = f"'{folder_id}' in parents and trashed = false"
	params = {
		"q": query,
		"fields": "files(id,name,mimeType)",
		"pageSize": 1,
		"supportsAllDrives": True,
		"includeItemsFromAllDrives": True,
	}
	params.update(_get_drive_scope_params(settings))

	response = _execute_with_retry(lambda: drive.files().list(**params).execute())
	return not bool(response.get("files") or [])


def _folder_belongs_to_projects_root(drive, folder_id: str, parent_folder_id: str) -> bool:
	try:
		metadata = _execute_with_retry(
			lambda: (
				drive.files()
				.get(fileId=folder_id, fields="id,parents,trashed", supportsAllDrives=True)
				.execute()
			)
		)
	except HttpError as exc:
		if _get_http_status_code(exc) == 404:
			return True
		return False

	parents = metadata.get("parents") or []
	return parent_folder_id in parents


def _delete_folder_idempotent(drive, folder_id: str) -> str:
	try:
		_execute_with_retry(lambda: drive.files().delete(fileId=folder_id, supportsAllDrives=True).execute())
		return "deleted"
	except HttpError as exc:
		if _get_http_status_code(exc) == 404:
			return "already_missing"
		return "failed"
	except Exception:
		return "failed"


def _update_project_drive_link(projeto_name: str, link: str) -> None:
	frappe.db.set_value(PROJECT_DOCTYPE, projeto_name, "link_pasta_google_drive", link, update_modified=True)
	# Commit explícito: a pasta já existe no Drive. Se o job falhar depois daqui, o
	# link não pode se perder — senão a próxima execução cria uma pasta duplicada.
	frappe.db.commit()  # nosemgrep


def _get_project_settings():
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return None
	return frappe.get_single(SETTINGS_DOCTYPE)


def _is_feature_enabled(settings) -> bool:
	return bool(settings and cint(settings.habilitar_pastas_projetos_drive))


def _escape_drive_query_value(value: str) -> str:
	return (value or "").replace("\\", "\\\\").replace("'", "\\'")


def _get_drive_scope_params(settings) -> dict[str, str]:
	drive_id = (settings.drive_compartilhado_projetos or "").strip()
	if not drive_id:
		return {}
	return {"corpora": "drive", "driveId": drive_id}


def _get_http_status_code(exc: HttpError) -> int | None:
	return getattr(getattr(exc, "resp", None), "status", None)
