import datetime
import hashlib
import json
import os
import time

import frappe
from frappe import _
from frappe.utils import get_bench_path, now_datetime
from frappe.utils.background_jobs import enqueue
from frappe.utils.backups import new_backup
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SETTINGS_DOCTYPE = "Configuracoes Backup Google Drive"
RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}
MAX_RETRIES = 5
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def enqueue_daily_backup():
	settings = _get_settings()
	if not settings.enable_backup:
		return

	enqueue(
		"gris.api.backup.google_shared_drive.run_daily_backup",
		queue="long",
		timeout=2400,
		job_name=f"{frappe.local.site}:shared-drive-daily-backup",
	)


@frappe.whitelist()
def enqueue_backup_now():
	enqueue(
		"gris.api.backup.google_shared_drive.run_daily_backup",
		queue="long",
		timeout=2400,
	)
	frappe.msgprint(_("Backup agendado na fila longa."))


@frappe.whitelist()
def diagnose_destination_folder():
	settings = _get_settings()
	_validate_settings(settings)

	drive = _get_google_drive_service()
	folder = _execute_with_retry(
		lambda: (
			drive.files()
			.get(
				fileId=settings.backup_folder_id,
				fields="id,name,driveId,mimeType",
				supportsAllDrives=True,
			)
			.execute()
		)
	)

	return {
		"backup_folder_id": settings.backup_folder_id,
		"configured_shared_drive_id": settings.shared_drive_id,
		"detected_shared_drive_id": folder.get("driveId"),
		"folder_name": folder.get("name"),
		"mime_type": folder.get("mimeType"),
	}


def run_daily_backup():
	settings = _get_settings()
	if not settings.enable_backup:
		return

	logger = frappe.logger("shared_drive_backup")
	try:
		_validate_settings(settings)

		drive = _get_google_drive_service()
		_validate_destination_folder(drive, settings)
		snapshot_folder = _create_snapshot_folder(drive, settings)

		backup_paths = _generate_backups(settings)
		uploaded_files = []
		for backup_path in backup_paths:
			if not backup_path:
				continue
			uploaded = _upload_file_to_shared_drive(
				drive=drive,
				settings=settings,
				backup_path=backup_path,
				parent_folder_id=snapshot_folder["id"],
			)
			uploaded_files.append(uploaded)

		deleted_count = _apply_retention_policy(drive, settings)

		frappe.db.set_single_value(
			SETTINGS_DOCTYPE,
			{
				"last_backup_on": now_datetime(),
				"last_error": "",
			},
		)
		frappe.db.commit()

		logger.info(
			"Backup concluido no Shared Drive. site=%s snapshot=%s uploaded=%s deleted=%s",
			frappe.local.site,
			snapshot_folder["name"],
			len(uploaded_files),
			deleted_count,
		)
		_send_notification(
			settings,
			success=True,
			message=_(
				"Backup concluido com sucesso. Snapshot: {0}. Arquivos enviados: {1}. Snapshots removidos por retencao: {2}."
			).format(snapshot_folder["name"], len(uploaded_files), deleted_count),
		)
	except Exception:
		error_message = frappe.get_traceback()
		frappe.log_error(error_message, "Shared Drive Backup Failure")
		frappe.db.set_single_value(
			SETTINGS_DOCTYPE,
			{"last_error": error_message[-5000:]},
		)
		frappe.db.commit()
		_send_notification(
			settings,
			success=False,
			message=_("Falha no backup para Shared Drive. Verifique Error Log para detalhes."),
		)
		raise


def _get_settings():
	return frappe.get_single(SETTINGS_DOCTYPE)


def _validate_settings(settings):
	if not settings.backup_folder_id:
		raise frappe.ValidationError(_("Informe o Folder ID de destino no Shared Drive."))

	if not settings.retention_days or settings.retention_days < 1:
		raise frappe.ValidationError(_("Retention Days deve ser maior que zero."))

	if not settings.get_password("service_account_json", raise_exception=False):
		raise frappe.ValidationError(_("Informe a chave JSON da Service Account."))


def _get_google_drive_service():
	settings = _get_settings()
	service_account_json = settings.get_password("service_account_json", raise_exception=False)

	try:
		service_account_info = json.loads(service_account_json)
	except Exception as exc:
		raise frappe.ValidationError(
			_("JSON da Service Account invalido. Verifique o conteudo informado.")
		) from exc

	required_keys = ["client_email", "private_key", "token_uri"]
	missing = [key for key in required_keys if not service_account_info.get(key)]
	if missing:
		raise frappe.ValidationError(
			_("Chave JSON da Service Account incompleta. Campos ausentes: {0}").format(", ".join(missing))
		)

	credentials = service_account.Credentials.from_service_account_info(
		service_account_info,
		scopes=DRIVE_SCOPES,
	)

	return build("drive", "v3", credentials=credentials, static_discovery=False)


def _validate_destination_folder(drive, settings):
	folder = _execute_with_retry(
		lambda: (
			drive.files()
			.get(
				fileId=settings.backup_folder_id,
				fields="id,name,mimeType,driveId",
				supportsAllDrives=True,
			)
			.execute()
		)
	)

	if folder.get("mimeType") != "application/vnd.google-apps.folder":
		raise frappe.ValidationError(_("O ID informado nao corresponde a uma pasta no Google Drive."))

	if settings.shared_drive_id and folder.get("driveId") != settings.shared_drive_id:
		raise frappe.ValidationError(
			_("A pasta informada nao pertence ao Shared Drive configurado em Shared Drive ID.")
		)


def _generate_backups(settings):
	ignore_files = not (settings.include_public_files or settings.include_private_files)
	backup = new_backup(ignore_files=ignore_files, force=True)

	paths = [backup.backup_path_db, backup.backup_path_conf]
	if settings.include_public_files:
		paths.append(backup.backup_path_files)
	if settings.include_private_files:
		paths.append(backup.backup_path_private_files)

	return [path for path in paths if path]


def _create_snapshot_folder(drive, settings):
	timestamp = frappe.utils.now_datetime().strftime("%Y-%m-%dT%H-%M-%SZ")
	snapshot_name = f"{frappe.local.site}-backup-{timestamp}"

	return _execute_with_retry(
		lambda: (
			drive.files()
			.create(
				body={
					"name": snapshot_name,
					"mimeType": "application/vnd.google-apps.folder",
					"parents": [settings.backup_folder_id],
					"description": f"Snapshot de backup Frappe ({frappe.local.site})",
				},
				fields="id,name,createdTime",
				supportsAllDrives=True,
			)
			.execute()
		)
	)


def _upload_file_to_shared_drive(drive, settings, backup_path, parent_folder_id):
	absolute_path = _to_absolute_path(backup_path)
	file_name = os.path.basename(backup_path)

	def _perform_upload():
		media = MediaFileUpload(absolute_path, mimetype="application/octet-stream", resumable=True)
		return (
			drive.files()
			.create(
				body={
					"name": file_name,
					"parents": [parent_folder_id],
					"description": f"Frappe backup - {frappe.local.site}",
				},
				media_body=media,
				fields="id,name,createdTime,size,md5Checksum",
				supportsAllDrives=True,
			)
			.execute()
		)

	uploaded = _execute_with_retry(_perform_upload)
	_validate_uploaded_checksum(absolute_path, uploaded.get("md5Checksum"), file_name)
	return uploaded


def _apply_retention_policy(drive, settings):
	cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=settings.retention_days)
	page_token = None
	deleted = 0

	while True:
		params = {
			"q": (
				f"'{settings.backup_folder_id}' in parents and trashed = false "
				"and mimeType = 'application/vnd.google-apps.folder'"
			),
			"fields": "nextPageToken, files(id,name,createdTime,mimeType)",
			"supportsAllDrives": True,
			"includeItemsFromAllDrives": True,
			"pageSize": 1000,
		}

		if settings.shared_drive_id:
			params.update({"corpora": "drive", "driveId": settings.shared_drive_id})

		if page_token:
			params["pageToken"] = page_token

		response = _execute_with_retry(lambda: drive.files().list(**params).execute())
		for file_info in response.get("files", []):
			if not _is_snapshot_folder(file_info.get("name", "")):
				continue

			created_time = _parse_google_datetime(file_info.get("createdTime"))
			if not created_time or created_time >= cutoff:
				continue

			_execute_with_retry(
				lambda fid=file_info["id"]: drive.files().delete(fileId=fid, supportsAllDrives=True).execute()
			)
			deleted += 1

		page_token = response.get("nextPageToken")
		if not page_token:
			break

	return deleted


def _is_snapshot_folder(folder_name):
	if not folder_name:
		return False

	return folder_name.startswith(f"{frappe.local.site}-backup-")


def _parse_google_datetime(value):
	if not value:
		return None

	try:
		return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
	except ValueError:
		return None


def _to_absolute_path(file_path):
	if not file_path:
		raise frappe.ValidationError(_("Caminho de backup invalido."))

	if os.path.isabs(file_path):
		absolute_path = file_path
	else:
		absolute_path = os.path.join(get_bench_sites_path(), file_path.lstrip("/"))

	if not os.path.exists(absolute_path):
		raise frappe.ValidationError(_("Arquivo de backup nao encontrado: {0}").format(file_path))

	return absolute_path


def get_bench_sites_path():
	return os.path.join(get_bench_path(), "sites")


def _validate_uploaded_checksum(local_path, remote_md5, file_name):
	if not remote_md5:
		return

	hash_md5 = hashlib.md5()  # nosec B324
	with open(local_path, "rb") as file_handle:
		for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
			hash_md5.update(chunk)

	if hash_md5.hexdigest() != remote_md5:
		raise frappe.ValidationError(_("Checksum divergente apos upload do arquivo: {0}").format(file_name))


def _execute_with_retry(operation):
	for attempt in range(MAX_RETRIES):
		try:
			return operation()
		except HttpError as exc:
			status_code = getattr(exc, "status_code", None) or getattr(exc.resp, "status", None)
			if status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES - 1:
				raise

			time.sleep(2**attempt)


def _send_notification(settings, success, message):
	recipients = []
	if settings.notification_email:
		recipients = [settings.notification_email]

	if not recipients:
		return

	if success and not settings.notify_on_success:
		return

	subject = _("[Backup] Shared Drive - Sucesso") if success else _("[Backup] Shared Drive - Falha")

	frappe.sendmail(recipients=recipients, subject=subject, message=message, delayed=False)
