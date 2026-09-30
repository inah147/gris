"""Pasta no Google Drive de cada projeto de captação.

Criada quando a Diretoria aprova a ideia, dentro da pasta configurada em
`Configuracoes de Captacao`. O proponente guarda ali os arquivos de apoio do
detalhamento. Mesmo desenho de `festa_drive` e `project_drive`: job enfileirado,
idempotente (reaproveita uma pasta de mesmo nome) e com nova tentativa em falha
transitória.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint
from googleapiclient.errors import HttpError

from gris.api.google_workspace.access_manager import _execute_with_retry, _get_google_drive_service
from gris.api.google_workspace.project_drive import build_drive_folder_link, extract_drive_folder_id
from gris.utils.job_logger import definir_resumo, metrica, obter_logger

SETTINGS_DOCTYPE = "Configuracoes de Captacao"
PROJETO_DOCTYPE = "Projeto de Captacao"
FOLDER_MIMETYPE = "application/vnd.google-apps.folder"
MAX_CREATE_ATTEMPTS = 3
RETRYABLE_HTTP_STATUS_CODES = {403, 429, 500, 502, 503, 504}


def _logger():
	return obter_logger("google_workspace_captacao_drive", file_count=10)


def enfileirar_criacao_da_pasta(projeto_name: str) -> None:
	"""Chamado na aprovação da ideia. Só enfileira depois do commit da decisão."""
	frappe.enqueue(
		"gris.api.google_workspace.captacao_drive.criar_pasta_do_projeto",
		queue="long",
		timeout=300,
		enqueue_after_commit=True,
		job_name=f"{frappe.local.site}:captacao-drive-create:{projeto_name}:1",
		projeto_name=projeto_name,
	)


def nome_da_pasta(projeto_name: str, titulo: str | None) -> str:
	titulo = (titulo or "").strip()
	return f"{projeto_name} - {titulo}" if titulo else projeto_name


def criar_pasta_do_projeto(projeto_name: str, attempt: int = 1) -> dict[str, str | int]:
	logger = _logger()
	if not projeto_name or not frappe.db.exists(PROJETO_DOCTYPE, projeto_name):
		definir_resumo(f"Projeto {projeto_name} não existe mais.")
		return {"status": "projeto_nao_encontrado"}

	settings = _get_settings()
	if not settings or not cint(settings.habilitar_pastas_drive):
		definir_resumo("Criação de pastas de captação desligada.")
		return {"status": "desligado"}

	pasta_mae = (settings.pasta_captacao or "").strip()
	drive_id = (settings.drive_compartilhado or "").strip()
	if not pasta_mae or not drive_id:
		logger.warning("[CAPTACAO DRIVE] configuração incompleta projeto=%s", projeto_name)
		definir_resumo("Configuração de Drive da captação incompleta.")
		return {"status": "configuracao_incompleta"}

	link_atual, titulo = frappe.db.get_value(
		PROJETO_DOCTYPE, projeto_name, ["link_pasta_google_drive", "titulo"]
	)
	if link_atual and extract_drive_folder_id(link_atual):
		definir_resumo(f"{projeto_name} já tinha pasta.")
		return {"status": "ja_vinculado"}

	folder_name = nome_da_pasta(projeto_name, titulo)
	try:
		drive = _get_google_drive_service()
		_validar_pasta_mae(drive, pasta_mae, drive_id)
		existente = _buscar_pasta(drive, drive_id, pasta_mae, folder_name)
		folder_id = (existente or {}).get("id") or ""
		if folder_id:
			metrica("reaproveitadas")
		else:
			criada = _criar_pasta(drive, pasta_mae, folder_name, projeto_name)
			folder_id = (criada or {}).get("id") or ""
			metrica("criadas")
		if not folder_id:
			raise frappe.ValidationError("Não foi possível determinar o ID da pasta do projeto.")

		_gravar_link(projeto_name, build_drive_folder_link(folder_id))
		definir_resumo(f"Pasta de {projeto_name} vinculada.")
		return {"status": "ok", "folder_id": folder_id, "attempt": attempt}
	except frappe.ValidationError as exc:
		logger.warning("[CAPTACAO DRIVE] configuração inválida projeto=%s detalhe=%s", projeto_name, str(exc))
		definir_resumo(f"Configuração inválida: {exc}")
		return {"status": "configuracao_invalida", "attempt": attempt}
	except Exception as exc:
		frappe.log_error(frappe.get_traceback(), f"criar_pasta_do_projeto:{projeto_name}")
		logger.error("[CAPTACAO DRIVE] falha projeto=%s tentativa=%s", projeto_name, attempt)
		if _vale_tentar_de_novo(exc):
			_agendar_nova_tentativa(projeto_name, attempt)
		definir_resumo(f"Falha ao criar a pasta de {projeto_name} (tentativa {attempt}).")
		return {"status": "erro", "attempt": attempt}


def _agendar_nova_tentativa(projeto_name: str, attempt: int) -> None:
	if attempt >= MAX_CREATE_ATTEMPTS:
		return
	proxima = attempt + 1
	frappe.enqueue(
		"gris.api.google_workspace.captacao_drive.criar_pasta_do_projeto",
		queue="long",
		timeout=300,
		job_name=f"{frappe.local.site}:captacao-drive-create:{projeto_name}:{proxima}",
		projeto_name=projeto_name,
		attempt=proxima,
	)


def _criar_pasta(drive, pasta_mae: str, folder_name: str, projeto_name: str) -> dict:
	return _execute_with_retry(
		lambda: (
			drive.files()
			.create(
				body={
					"name": folder_name,
					"mimeType": FOLDER_MIMETYPE,
					"parents": [pasta_mae],
					"description": f"Pasta do projeto de captação {projeto_name}",
				},
				fields="id,name,createdTime",
				supportsAllDrives=True,
			)
			.execute()
		)
	)


def _validar_pasta_mae(drive, pasta_mae: str, drive_id: str) -> None:
	try:
		metadata = _execute_with_retry(
			lambda: (
				drive.files()
				.get(fileId=pasta_mae, fields="id,mimeType,trashed,driveId", supportsAllDrives=True)
				.execute()
			)
		)
	except HttpError as exc:
		if _status_http(exc) == 404:
			raise frappe.ValidationError("Pasta dos projetos de captação não encontrada no Drive.") from exc
		raise

	if metadata.get("mimeType") != FOLDER_MIMETYPE:
		raise frappe.ValidationError("O item configurado como pasta de captação não é uma pasta.")
	if metadata.get("trashed"):
		raise frappe.ValidationError("A pasta dos projetos de captação está na lixeira.")
	pasta_drive = (metadata.get("driveId") or "").strip()
	if pasta_drive and pasta_drive != drive_id:
		raise frappe.ValidationError("A pasta configurada não pertence ao drive compartilhado selecionado.")


def _buscar_pasta(drive, drive_id: str, pasta_mae: str, folder_name: str) -> dict | None:
	nome = (folder_name or "").replace("\\", "\\\\").replace("'", "\\'")
	params = {
		"q": (
			f"'{pasta_mae}' in parents and trashed = false and "
			f"mimeType = '{FOLDER_MIMETYPE}' and name = '{nome}'"
		),
		"fields": "files(id,name,createdTime)",
		"pageSize": 1,
		"supportsAllDrives": True,
		"includeItemsFromAllDrives": True,
		"corpora": "drive",
		"driveId": drive_id,
	}
	resposta = _execute_with_retry(lambda: drive.files().list(**params).execute())
	arquivos = resposta.get("files") or []
	return arquivos[0] if arquivos else None


def _gravar_link(projeto_name: str, link: str) -> None:
	frappe.db.set_value(PROJETO_DOCTYPE, projeto_name, "link_pasta_google_drive", link, update_modified=False)
	# Commit explícito: a pasta já existe no Drive. Se o job falhar depois daqui, o
	# link não pode se perder — senão a próxima execução cria uma pasta duplicada.
	frappe.db.commit()  # nosemgrep


def _get_settings():
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return None
	return frappe.get_single(SETTINGS_DOCTYPE)


def _vale_tentar_de_novo(exc: Exception) -> bool:
	if isinstance(exc, HttpError):
		return _status_http(exc) in RETRYABLE_HTTP_STATUS_CODES
	return True


def _status_http(exc: HttpError) -> int | None:
	return getattr(getattr(exc, "resp", None), "status", None)
