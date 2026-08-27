import json
import time

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime
from frappe.utils.background_jobs import enqueue
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SETTINGS_DOCTYPE = "Configuracoes Google Workspace"
DEFAULT_DOMAIN = "escoteiros.org.br"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}
MAX_RETRIES = 5
VOLUNTEER_CATEGORIES = {"Dirigente", "Escotista", "Colaboradores", "Profissional Escoteiro"}
ADMIN_ROLES = {"System Manager", "Administrator"}


def _logger():
	return frappe.logger("google_workspace_access", allow_site=True, file_count=10)


def _is_integration_enabled(settings=None) -> bool:
	settings = settings or frappe.get_single(SETTINGS_DOCTYPE)
	return bool(settings.habilitar_integracao)


def _normalize_email(value: str | None) -> str:
	return (value or "").strip().lower()


def _get_domain(settings=None) -> str:
	settings = settings or frappe.get_single(SETTINGS_DOCTYPE)
	domain = (settings.dominio_institucional or DEFAULT_DOMAIN).strip().lower()
	if domain.startswith("@"):
		domain = domain[1:]
	return domain or DEFAULT_DOMAIN


def _is_institutional_email(email: str, settings=None) -> bool:
	domain = _get_domain(settings)
	return bool(email) and email.endswith(f"@{domain}")


def _is_active_associate(associate) -> bool:
	return (associate.status_no_grupo or "") == "Ativo"


def _is_volunteer_associate(associate) -> bool:
	return (associate.categoria or "") in VOLUNTEER_CATEGORIES


def _is_beneficiary_associate(associate) -> bool:
	return (associate.categoria or "") == "Beneficiário"


def _get_settings():
	return frappe.get_single(SETTINGS_DOCTYPE)


def _get_google_drive_service(settings=None):
	settings = settings or _get_settings()
	service_account_json = settings.get_password("service_account_json", raise_exception=False)
	if not service_account_json:
		raise frappe.ValidationError("Service Account JSON nao configurado.")

	try:
		service_account_info = json.loads(service_account_json)
	except Exception as exc:
		raise frappe.ValidationError("Service Account JSON invalido.") from exc

	required_keys = ["client_email", "private_key", "token_uri"]
	missing = [key for key in required_keys if not service_account_info.get(key)]
	if missing:
		raise frappe.ValidationError(
			"Service Account JSON incompleto. Campos ausentes: {}".format(", ".join(missing))
		)

	credentials = service_account.Credentials.from_service_account_info(
		service_account_info,
		scopes=DRIVE_SCOPES,
	)
	return build("drive", "v3", credentials=credentials, static_discovery=False)


def _execute_with_retry(operation):
	last_exc = None
	for attempt in range(1, MAX_RETRIES + 1):
		try:
			return operation()
		except HttpError as exc:
			status_code = getattr(getattr(exc, "resp", None), "status", None)
			if status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
				raise
			last_exc = exc
			time.sleep(2 ** (attempt - 1))
		continue
	if last_exc:
		raise last_exc


def _get_configured_drives(settings=None):
	settings = settings or _get_settings()
	return [row for row in (settings.drives_compartilhados or []) if row.ativo and row.drive_id]


def _get_global_drives(settings=None):
	return [row for row in _get_configured_drives(settings) if row.conceder_a_todos]


def _find_permissions_for_email(drive, drive_id: str, email: str) -> list[dict]:
	email = _normalize_email(email)
	permissions_for_email: list[dict] = []
	page_token = None

	while True:
		params = {
			"fileId": drive_id,
			"fields": "nextPageToken,permissions(id,emailAddress,role,type)",
			"supportsAllDrives": True,
		}
		if page_token:
			params["pageToken"] = page_token

		response = _execute_with_retry(lambda: drive.permissions().list(**params).execute())
		for permission in response.get("permissions", []):
			if _normalize_email(permission.get("emailAddress")) == email:
				permissions_for_email.append(
					{
						"id": permission.get("id"),
						"role": (permission.get("role") or "").strip().lower(),
					}
				)

		page_token = response.get("nextPageToken")
		if not page_token:
			break

	return [p for p in permissions_for_email if p.get("id")]


def _resolve_drive_default_role(drive_row, associate) -> str | None:
	if _is_beneficiary_associate(associate):
		return (drive_row.permissao_padrao_beneficiario or "").strip().lower()

	if _is_volunteer_associate(associate):
		return (drive_row.permissao_padrao_adulto_voluntario or "").strip().lower()

	return None


def grant_drive_access_if_missing(drive, email: str, drive_id: str, role: str = "reader"):
	email = _normalize_email(email)
	role = (role or "reader").strip().lower()
	if role not in {"reader", "writer"}:
		role = "reader"

	permissions = _find_permissions_for_email(drive, drive_id, email)
	if permissions:
		if all(permission.get("role") == role for permission in permissions):
			return "unchanged"

		for permission in permissions:
			permission_id = permission.get("id")
			if not permission_id or permission.get("role") == role:
				continue

			_execute_with_retry(
				lambda pid=permission_id: (
					drive.permissions()
					.update(
						fileId=drive_id,
						permissionId=pid,
						body={"role": role},
						supportsAllDrives=True,
					)
					.execute()
				)
			)
		return "updated"

	_execute_with_retry(
		lambda: (
			drive.permissions()
			.create(
				fileId=drive_id,
				body={"type": "user", "role": role, "emailAddress": email},
				sendNotificationEmail=False,
				supportsAllDrives=True,
			)
			.execute()
		)
	)
	return "created"


def revoke_drive_access_if_exists(drive, email: str, drive_id: str) -> int:
	email = _normalize_email(email)
	permissions = _find_permissions_for_email(drive, drive_id, email)
	if not permissions:
		return 0

	for permission in permissions:
		permission_id = permission.get("id")
		if not permission_id:
			continue

		_execute_with_retry(
			lambda pid=permission_id: (
				drive.permissions()
				.delete(fileId=drive_id, permissionId=pid, supportsAllDrives=True)
				.execute()
			)
		)
	return len(permissions)


def _sync_global_access_for_associate(associate_name: str):
	settings = _get_settings()
	if not _is_integration_enabled(settings):
		return

	if not frappe.db.exists("Associado", associate_name):
		return

	associate = frappe.get_doc("Associado", associate_name)
	if not _is_active_associate(associate):
		return

	email = _normalize_email(associate.id_escoteiros)
	if not _is_institutional_email(email, settings):
		_logger().info("[GLOBAL SYNC] skip associate=%s reason=invalid_email email=%s", associate_name, email)
		return

	global_drives = _get_global_drives(settings)
	if not global_drives:
		return

	drive = _get_google_drive_service(settings)

	for drive_row in global_drives:
		role = _resolve_drive_default_role(drive_row, associate)
		if role not in {"reader", "writer"}:
			continue

		grant_drive_access_if_missing(drive, email, drive_row.drive_id, role)


def sync_global_access_for_associate(associate_name: str):
	try:
		_sync_global_access_for_associate(associate_name)
		frappe.db.set_single_value(
			SETTINGS_DOCTYPE,
			{"ultimo_sync_em": now_datetime(), "ultimo_erro": ""},
		)
		frappe.db.commit()
	except Exception:
		tb = frappe.get_traceback()
		frappe.log_error(tb, f"sync_global_access_for_associate:{associate_name}")
		_logger().error("[GLOBAL SYNC] failed associate=%s\n%s", associate_name, tb)
		frappe.db.set_single_value(SETTINGS_DOCTYPE, {"ultimo_erro": tb[-5000:]})
		frappe.db.commit()
		raise


def _revoke_all_access_for_email(email: str):
	settings = _get_settings()
	if not _is_integration_enabled(settings):
		return

	email = _normalize_email(email)
	if not _is_institutional_email(email, settings):
		return

	drive = _get_google_drive_service(settings)
	for drive_row in _get_configured_drives(settings):
		revoke_drive_access_if_exists(drive, email, drive_row.drive_id)


def revoke_all_access_for_associate(associate_name: str):
	if not frappe.db.exists("Associado", associate_name):
		return

	associate = frappe.get_doc("Associado", associate_name)
	email = _normalize_email(associate.id_escoteiros)
	if not email:
		return

	try:
		_revoke_all_access_for_email(email)
	except Exception:
		tb = frappe.get_traceback()
		frappe.log_error(tb, f"revoke_all_access_for_associate:{associate_name}")
		_logger().error("[REVOKE ASSOCIATE] failed associate=%s\n%s", associate_name, tb)
		raise


def enqueue_daily_global_access_sync():
	enqueue(
		"gris.api.google_workspace.access_manager.run_daily_global_access_sync",
		queue="long",
		timeout=2400,
		job_name=f"{frappe.local.site}:google-workspace-global-access-sync",
	)


def enqueue_daily_restricted_access_cleanup():
	enqueue(
		"gris.api.google_workspace.access_manager.run_daily_restricted_access_cleanup",
		queue="long",
		timeout=2400,
		job_name=f"{frappe.local.site}:google-workspace-restricted-access-cleanup",
	)


def enqueue_daily_inactive_access_cleanup():
	enqueue(
		"gris.api.google_workspace.access_manager.run_daily_inactive_access_cleanup",
		queue="long",
		timeout=2400,
		job_name=f"{frappe.local.site}:google-workspace-inactive-access-cleanup",
	)


def run_daily_global_access_sync():
	settings = _get_settings()
	if not _is_integration_enabled(settings):
		return

	associates = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo"},
		fields=["name", "id_escoteiros"],
	)
	for associate in associates:
		if not associate.id_escoteiros:
			continue
		sync_global_access_for_associate(associate.name)


def _is_workspace_admin(email: str) -> bool:
	if not frappe.db.exists("User", email):
		return False
	roles = set(frappe.get_roles(email))
	return bool(roles.intersection(ADMIN_ROLES))


def _is_manual_grant_expired(row, expiration_days: int, today) -> bool:
	if row.expira_em:
		return getdate(row.expira_em) < today
	if not row.concedido_em:
		return False
	return getdate(add_days(get_datetime(row.concedido_em), expiration_days)) < today


def run_daily_restricted_access_cleanup():
	settings = _get_settings()
	if not _is_integration_enabled(settings):
		return

	drive_rows = _get_configured_drives(settings)
	global_drive_ids = {row.drive_id for row in drive_rows if row.conceder_a_todos}
	drive_ids = {row.drive_id for row in drive_rows}
	if not drive_ids:
		return

	drive = _get_google_drive_service(settings)
	expiration_days = settings.dias_expiracao_acesso_restrito or 365
	today = getdate()

	associate_names = {
		row.associado for row in (settings.concessoes_manuais or []) if row.ativo and row.associado
	}
	associate_map = {}
	if associate_names:
		associate_rows = frappe.get_all(
			"Associado",
			filters={"name": ["in", list(associate_names)]},
			fields=["name", "id_escoteiros", "status_no_grupo"],
		)
		associate_map = {row.name: row for row in associate_rows}

	changed = False
	for row in settings.concessoes_manuais or []:
		if not row.ativo:
			continue
		if not row.drive_id or row.drive_id not in drive_ids or row.drive_id in global_drive_ids:
			continue

		associate = associate_map.get(row.associado)
		if not associate or associate.status_no_grupo != "Ativo":
			continue

		email = _normalize_email(associate.id_escoteiros or row.email_institucional)
		if not _is_institutional_email(email, settings):
			continue

		if row.email_institucional != email:
			row.email_institucional = email
			changed = True

		if _is_manual_grant_expired(row, expiration_days, today) and not _is_workspace_admin(email):
			revoke_drive_access_if_exists(drive, email, row.drive_id)
			row.ativo = 0
			changed = True
			continue

		grant_drive_access_if_missing(drive, email, row.drive_id, row.tipo_acesso or "reader")
		if not row.concedido_em:
			row.concedido_em = now_datetime()
			changed = True

	if changed:
		settings.save(ignore_permissions=True)
		frappe.db.commit()

	frappe.db.set_single_value(SETTINGS_DOCTYPE, {"ultimo_sync_em": now_datetime(), "ultimo_erro": ""})
	frappe.db.commit()


def run_daily_inactive_access_cleanup():
	settings = _get_settings()
	if not _is_integration_enabled(settings):
		return

	inactive_associates = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Inativo"},
		fields=["id_escoteiros"],
	)

	drive = _get_google_drive_service(settings)
	for associate in inactive_associates:
		email = _normalize_email(associate.id_escoteiros)
		if not _is_institutional_email(email, settings):
			continue
		for drive_row in _get_configured_drives(settings):
			revoke_drive_access_if_exists(drive, email, drive_row.drive_id)

	frappe.db.set_single_value(SETTINGS_DOCTYPE, {"ultimo_sync_em": now_datetime(), "ultimo_erro": ""})
	frappe.db.commit()
