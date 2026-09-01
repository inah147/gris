import json
import time

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime
from frappe.utils.background_jobs import enqueue
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from gris.utils.job_logger import definir_resumo, metrica, obter_logger

SETTINGS_DOCTYPE = "Configuracoes Google Workspace"
DEFAULT_DOMAIN = "escoteiros.org.br"
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}
# 403 com um destes motivos é definitivo: API desligada no projeto ou falta de permissão.
PERMANENT_403_REASONS = {
	"accessnotconfigured",
	"servicedisabled",
	"forbidden",
	"insufficientpermissions",
	"insufficientfilepermissions",
	"domainpolicy",
}
MAX_RETRIES = 5
VOLUNTEER_CATEGORIES = {"Dirigente", "Escotista", "Colaboradores", "Profissional Escoteiro"}
ADMIN_ROLES = {"System Manager", "Administrator"}


def _logger():
	return obter_logger("google_workspace_access", file_count=10)


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


def get_service_account_credentials(settings=None):
	"""Credenciais da service account configurada no Single de Workspace.

	Exposta separadamente do cliente do Drive porque o mesmo escopo ``auth/drive`` serve
	para a Docs API (usada na geração da declaracao de idoneidade em ``recepcao_drive``):
	recuperar as credenciais de dentro de um cliente ja construido depende de detalhe
	interno da googleapiclient.
	"""
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

	return service_account.Credentials.from_service_account_info(
		service_account_info,
		scopes=DRIVE_SCOPES,
	)


def _get_google_drive_service(settings=None):
	credentials = get_service_account_credentials(settings)
	return build("drive", "v3", credentials=credentials, static_discovery=False)


def _motivos_do_erro(exc: HttpError) -> set[str]:
	"""Códigos de ``reason`` que o Google devolve no corpo do erro, normalizados.

	O mesmo motivo aparece em grafias diferentes conforme a API: ``SERVICE_DISABLED`` na
	Docs, ``accessNotConfigured`` na Drive. Descartar separadores e caixa deixa a
	comparação depender só das letras.
	"""
	motivos = set()
	for detalhe in getattr(exc, "error_details", None) or []:
		if not isinstance(detalhe, dict):
			continue
		valor = detalhe.get("reason")
		if isinstance(valor, str) and valor.strip():
			motivos.add(valor.strip().lower().replace("_", "").replace("-", ""))
	return motivos


def _e_403_permanente(exc: HttpError) -> bool:
	"""Distingue os dois 403 opostos do Google.

	O mesmo status cobre limite de taxa (transitório, vale repetir) e API desabilitada ou
	sem permissão (permanente). Repetir o segundo caso só faz o usuário esperar os cinco
	ciclos de backoff antes de ver um erro que já era definitivo na primeira tentativa.
	"""
	return bool(_motivos_do_erro(exc) & PERMANENT_403_REASONS)


def _execute_with_retry(operation):
	last_exc = None
	for attempt in range(1, MAX_RETRIES + 1):
		try:
			return operation()
		except HttpError as exc:
			status_code = getattr(getattr(exc, "resp", None), "status", None)
			if status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
				raise
			if status_code == 403 and _e_403_permanente(exc):
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
	_logger().info("Enfileirando a sincronizacao diaria de acessos do Google Workspace.")
	definir_resumo("Sincronização de acessos do Workspace enviada para a fila longa.")
	enqueue(
		"gris.api.google_workspace.access_manager.run_daily_global_access_sync",
		queue="long",
		timeout=2400,
		job_name=f"{frappe.local.site}:google-workspace-global-access-sync",
	)


def enqueue_daily_restricted_access_cleanup():
	_logger().info("Enfileirando a limpeza diaria de acessos restritos.")
	definir_resumo("Limpeza de acessos restritos enviada para a fila longa.")
	enqueue(
		"gris.api.google_workspace.access_manager.run_daily_restricted_access_cleanup",
		queue="long",
		timeout=2400,
		job_name=f"{frappe.local.site}:google-workspace-restricted-access-cleanup",
	)


def enqueue_daily_inactive_access_cleanup():
	_logger().info("Enfileirando a limpeza diaria de acessos de associados inativos.")
	definir_resumo("Limpeza de acessos de inativos enviada para a fila longa.")
	enqueue(
		"gris.api.google_workspace.access_manager.run_daily_inactive_access_cleanup",
		queue="long",
		timeout=2400,
		job_name=f"{frappe.local.site}:google-workspace-inactive-access-cleanup",
	)


def run_daily_global_access_sync():
	logger = _logger()
	settings = _get_settings()
	if not _is_integration_enabled(settings):
		logger.warning("Integracao com o Google Workspace desativada — sincronizacao ignorada.")
		definir_resumo("Integração com o Google Workspace desativada.")
		return

	associates = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo"},
		fields=["name", "id_escoteiros"],
	)
	logger.info(f"Sincronizando acessos de {len(associates)} associado(s) ativo(s).")

	sincronizados = 0
	sem_email = 0
	for associate in associates:
		if not associate.id_escoteiros:
			sem_email += 1
			continue
		sync_global_access_for_associate(associate.name)
		sincronizados += 1

	metrica("sincronizados", sincronizados, incrementar=False)
	metrica("sem_id_escoteiros", sem_email, incrementar=False)
	definir_resumo(
		f"{sincronizados} associado(s) sincronizado(s) no Google Workspace; {sem_email} sem ID Escoteiros."
	)


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
	logger = _logger()
	settings = _get_settings()
	if not _is_integration_enabled(settings):
		logger.warning("Integracao com o Google Workspace desativada — limpeza ignorada.")
		definir_resumo("Integração com o Google Workspace desativada.")
		return

	drive_rows = _get_configured_drives(settings)
	global_drive_ids = {row.drive_id for row in drive_rows if row.conceder_a_todos}
	drive_ids = {row.drive_id for row in drive_rows}
	if not drive_ids:
		logger.warning("Nenhum drive compartilhado configurado — nada a revisar.")
		definir_resumo("Nenhum drive compartilhado configurado.")
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
			logger.info("Acesso restrito revogado por expiracao: %s no drive %s.", email, row.drive_id)
			metrica("acessos_revogados")
			continue

		grant_drive_access_if_missing(drive, email, row.drive_id, row.tipo_acesso or "reader")
		metrica("acessos_revalidados")
		if not row.concedido_em:
			row.concedido_em = now_datetime()
			changed = True

	if changed:
		settings.save(ignore_permissions=True)
		# Commit explícito: as concessões já foram efetivadas na API do Google. Sem
		# persistir agora, uma falha adiante desfaria só o nosso lado e o próximo ciclo
		# tentaria conceder de novo o que já existe.
		frappe.db.commit()  # nosemgrep

	frappe.db.set_single_value(SETTINGS_DOCTYPE, {"ultimo_sync_em": now_datetime(), "ultimo_erro": ""})
	definir_resumo(f"{len(drive_ids)} drive(s) revisado(s); concessões manuais expiradas foram revogadas.")


def run_daily_inactive_access_cleanup():
	logger = _logger()
	settings = _get_settings()
	if not _is_integration_enabled(settings):
		logger.warning("Integracao com o Google Workspace desativada — limpeza ignorada.")
		definir_resumo("Integração com o Google Workspace desativada.")
		return

	inactive_associates = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Inativo"},
		fields=["id_escoteiros"],
	)
	logger.info(f"Revisando acessos de {len(inactive_associates)} associado(s) inativo(s).")

	drive = _get_google_drive_service(settings)
	revogados = 0
	ignorados = 0
	for associate in inactive_associates:
		email = _normalize_email(associate.id_escoteiros)
		if not _is_institutional_email(email, settings):
			ignorados += 1
			continue
		for drive_row in _get_configured_drives(settings):
			revoke_drive_access_if_exists(drive, email, drive_row.drive_id)
		revogados += 1
		logger.info("Acessos revogados para o associado inativo %s.", email)

	metrica("inativos_processados", revogados, incrementar=False)
	metrica("sem_email_institucional", ignorados, incrementar=False)
	frappe.db.set_single_value(SETTINGS_DOCTYPE, {"ultimo_sync_em": now_datetime(), "ultimo_erro": ""})
	definir_resumo(
		f"Acessos revisados para {revogados} associado(s) inativo(s); {ignorados} sem e-mail institucional."
	)
