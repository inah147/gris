from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import frappe
from frappe.utils import cint, formatdate, getdate
from googleapiclient.errors import HttpError

from gris.api.google_workspace.access_manager import _execute_with_retry, _get_google_drive_service

SETTINGS_DOCTYPE = "Configuracoes de Festas"
FESTA_DOCTYPE = "Festa"
FOLDER_MIMETYPE = "application/vnd.google-apps.folder"
MAX_CREATE_ATTEMPTS = 3
RETRYABLE_HTTP_STATUS_CODES = {403, 429, 500, 502, 503, 504}

_FOLDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def _logger():
	return frappe.logger("google_workspace_festa_drive", allow_site=True, file_count=10)


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


def build_festa_folder_name(nome_festa: str, data) -> str:
	nome = (nome_festa or "").strip()
	data_str = ""
	if data:
		try:
			data_str = formatdate(getdate(data), "dd-MM-yyyy")
		except Exception:
			data_str = ""
	if data_str:
		return f"{nome} - {data_str}"
	return nome


def create_festa_folder_async(festa_name: str, attempt: int = 1) -> dict[str, str | int]:
	if not festa_name or not frappe.db.exists(FESTA_DOCTYPE, festa_name):
		return {"status": "festa_not_found"}

	settings = _get_festa_settings()
	if not _is_feature_enabled(settings):
		return {"status": "disabled"}

	parent_folder_id = extract_drive_folder_id(settings.pasta_festas_id) or (
		settings.pasta_festas_id or ""
	).strip()
	drive_id = (settings.drive_compartilhado_festas or "").strip()
	if not parent_folder_id or not drive_id:
		_logger().warning(
			"[FESTA DRIVE] missing settings festa=%s parent=%s drive=%s",
			festa_name,
			bool(parent_folder_id),
			bool(drive_id),
		)
		return {"status": "missing_settings"}

	doc = frappe.get_doc(FESTA_DOCTYPE, festa_name)
	current_link = (doc.get("link_drive") or "").strip()
	if current_link and extract_drive_folder_id(current_link):
		return {"status": "already_linked"}

	folder_name = build_festa_folder_name(doc.get("nome_festa") or festa_name, doc.get("data"))

	try:
		drive = _get_google_drive_service()
		_validate_parent_folder_configuration(
			drive=drive,
			parent_folder_id=parent_folder_id,
			drive_id=drive_id,
		)
		existing_folder = _find_existing_festa_folder(
			drive=drive,
			settings=settings,
			parent_folder_id=parent_folder_id,
			folder_name=folder_name,
		)
		folder_id = (existing_folder or {}).get("id") or ""
		if not folder_id:
			created_folder = _create_festa_folder(
				drive=drive,
				parent_folder_id=parent_folder_id,
				folder_name=folder_name,
				festa_name=festa_name,
			)
			folder_id = (created_folder or {}).get("id") or ""

		if not folder_id:
			raise frappe.ValidationError("Nao foi possivel determinar o ID da pasta da festa.")

		_update_festa_drive_link(festa_name, build_drive_folder_link(folder_id))
		return {"status": "ok", "folder_id": folder_id, "attempt": attempt}
	except frappe.ValidationError as exc:
		_logger().warning(
			"[FESTA DRIVE] invalid settings festa=%s detail=%s",
			festa_name,
			str(exc),
		)
		return {"status": "invalid_settings", "attempt": attempt}
	except Exception as exc:
		tb = frappe.get_traceback()
		frappe.log_error(tb, f"create_festa_folder_async:{festa_name}")
		_logger().error("[FESTA DRIVE] create failed festa=%s attempt=%s\n%s", festa_name, attempt, tb)
		if _should_retry_create_failure(exc):
			_schedule_create_retry_if_needed(festa_name, attempt)
		return {"status": _map_create_failure_status(exc), "attempt": attempt}


def _schedule_create_retry_if_needed(festa_name: str, attempt: int) -> None:
	if attempt >= MAX_CREATE_ATTEMPTS:
		return
	if not frappe.db.exists(FESTA_DOCTYPE, festa_name):
		return

	next_attempt = attempt + 1
	frappe.enqueue(
		"gris.api.google_workspace.festa_drive.create_festa_folder_async",
		queue="long",
		timeout=300,
		job_name=f"{frappe.local.site}:festa-drive-create:{festa_name}:{next_attempt}",
		festa_name=festa_name,
		attempt=next_attempt,
	)


def _create_festa_folder(drive, parent_folder_id: str, folder_name: str, festa_name: str) -> dict:
	return _execute_with_retry(
		lambda: (
			drive.files()
			.create(
				body={
					"name": folder_name,
					"mimeType": FOLDER_MIMETYPE,
					"parents": [parent_folder_id],
					"description": f"Pasta da festa {festa_name}",
				},
				fields="id,name,createdTime",
				supportsAllDrives=True,
			)
			.execute()
		)
	)


def _validate_parent_folder_configuration(drive, parent_folder_id: str, drive_id: str) -> None:
	try:
		metadata = _execute_with_retry(
			lambda: (
				drive.files()
				.get(
					fileId=parent_folder_id,
					fields="id,name,mimeType,trashed,driveId",
					supportsAllDrives=True,
				)
				.execute()
			)
		)
	except HttpError as exc:
		if _get_http_status_code(exc) == 404:
			raise frappe.ValidationError(
				"Pasta de festas nao encontrada no Google Drive. Revise o campo ID da pasta de festas."
			) from exc
		raise

	if metadata.get("mimeType") != FOLDER_MIMETYPE:
		raise frappe.ValidationError("ID da pasta de festas invalido: o item informado nao e uma pasta.")

	if metadata.get("trashed"):
		raise frappe.ValidationError("ID da pasta de festas invalido: a pasta configurada esta na lixeira.")

	folder_drive_id = (metadata.get("driveId") or "").strip()
	if drive_id and folder_drive_id and folder_drive_id != drive_id:
		raise frappe.ValidationError(
			"A pasta configurada nao pertence ao drive compartilhado das festas selecionado."
		)


def _find_existing_festa_folder(drive, settings, parent_folder_id: str, folder_name: str) -> dict | None:
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


def _update_festa_drive_link(festa_name: str, link: str) -> None:
	frappe.db.set_value(FESTA_DOCTYPE, festa_name, "link_drive", link, update_modified=True)
	frappe.db.commit()


def _get_festa_settings():
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return None
	return frappe.get_single(SETTINGS_DOCTYPE)


def _is_feature_enabled(settings) -> bool:
	return bool(settings and cint(settings.habilitar_pastas_festas_drive))


def _escape_drive_query_value(value: str) -> str:
	return (value or "").replace("\\", "\\\\").replace("'", "\\'")


def _get_drive_scope_params(settings) -> dict[str, str]:
	drive_id = (settings.drive_compartilhado_festas or "").strip()
	if not drive_id:
		return {}
	return {"corpora": "drive", "driveId": drive_id}


def _map_create_failure_status(exc: Exception) -> str:
	if isinstance(exc, frappe.ValidationError):
		return "invalid_settings"
	if isinstance(exc, HttpError) and _get_http_status_code(exc) == 404:
		return "invalid_parent_folder"
	return "error"


def _should_retry_create_failure(exc: Exception) -> bool:
	if isinstance(exc, frappe.ValidationError):
		return False
	if isinstance(exc, HttpError):
		return _get_http_status_code(exc) in RETRYABLE_HTTP_STATUS_CODES
	return True


def _get_http_status_code(exc: HttpError) -> int | None:
	return getattr(getattr(exc, "resp", None), "status", None)
