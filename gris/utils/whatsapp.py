from __future__ import annotations

import re
import time

import frappe
import requests
from frappe.utils import now_datetime

from .whatsapp_errors import WhatsAppConfigurationError, WhatsAppNumberNotFoundError, WhatsAppRequestError

SETTINGS_DOCTYPE = "Configuracoes WhatsApp"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


# ─── Infraestrutura interna ───────────────────────────────────────────────────


def _logger():
	return frappe.logger("whatsapp", allow_site=True, file_count=10)


def _get_config() -> dict:
	"""Lê e valida as configurações da Evolution API a partir do DocType Single."""
	settings = frappe.get_single(SETTINGS_DOCTYPE)

	if not settings.habilitar_integracao:
		raise WhatsAppConfigurationError(
			"Integração com WhatsApp está desabilitada. Habilite em Configuracoes WhatsApp."
		)

	url_api = (settings.get("url_api") or "").strip().rstrip("/")
	api_key = settings.get_password("api_key", raise_exception=False)
	nome_instancia = (settings.get("nome_instancia") or "").strip()

	if not url_api:
		raise WhatsAppConfigurationError("URL da API não configurada em Configuracoes WhatsApp.")
	if not api_key:
		raise WhatsAppConfigurationError("API Key não configurada em Configuracoes WhatsApp.")
	if not nome_instancia:
		raise WhatsAppConfigurationError("Nome da instância não configurado em Configuracoes WhatsApp.")

	return {"url_api": url_api, "api_key": api_key, "nome_instancia": nome_instancia}


def _build_headers(api_key: str) -> dict:
	return {"apikey": api_key, "Content-Type": "application/json"}


def _normalize_phone(number: str) -> str:
	"""Normaliza número de telefone para o formato da Evolution API: 55 + DDD + número.

	Aceita formatos como: +5511999999999, 5511999999999, 11999999999, (11) 99999-9999.
	Números de grupo (JID @g.us) são retornados sem modificação.
	"""
	if "@" in number:
		return number

	digits = re.sub(r"\D", "", number)

	if digits.startswith("55") and len(digits) >= 12:
		# Already has country code; check for duplicate DDD: 55 + DDD + DDD + number
		# e.g. 551111971872252 → 5511971872252
		if len(digits) >= 14 and digits[2:4] == digits[4:6]:
			digits = digits[:2] + digits[4:]
		return digits

	# No country code; check for duplicate DDD: DDD + DDD + number
	# e.g. 1111971872252 (13 digits) → 11971872252 (11 digits)
	if len(digits) > 11 and digits[:2] == digits[2:4]:
		digits = digits[2:]

	return f"55{digits}"


def _post(endpoint: str, payload: dict, *, config: dict | None = None) -> dict:
	"""Executa POST na Evolution API com retry automático para erros transitórios."""
	if config is None:
		config = _get_config()

	url = f"{config['url_api']}{endpoint}"
	headers = _build_headers(config["api_key"])
	logger = _logger()

	for attempt in range(1, MAX_RETRIES + 1):
		try:
			response = requests.post(url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT)
		except requests.RequestException as exc:
			raise WhatsAppRequestError(f"Falha de conexão ao chamar Evolution API: {exc}") from exc

		if response.status_code < 400:
			return response.json()

		if response.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
			try:
				detail = response.json()
			except ValueError:
				detail = response.text or "Sem detalhes."
			# Evolution API returns 400 with exists:False when number is not on WhatsApp
			if response.status_code == 400 and isinstance(detail, dict):
				messages = detail.get("response", {}).get("message", [])
				if isinstance(messages, list) and any(
					isinstance(m, dict) and m.get("exists") is False for m in messages
				):
					number = messages[0].get("number", "") if messages else ""
					raise WhatsAppNumberNotFoundError(f"Número {number} não está registrado no WhatsApp.")
				raise WhatsAppRequestError(f"Evolution API retornou HTTP {response.status_code}: {detail}")
			raise WhatsAppRequestError(f"Evolution API retornou HTTP {response.status_code}: {detail}")

		logger.warning(
			f"Evolution API HTTP {response.status_code} na tentativa {attempt}/{MAX_RETRIES}. Retentando..."
		)
		time.sleep(2 ** (attempt - 1))

	raise WhatsAppRequestError("Número máximo de tentativas atingido.")  # pragma: no cover


def _get(
	endpoint: str,
	*,
	params: dict | None = None,
	config: dict | None = None,
) -> dict | list:
	"""Executa GET na Evolution API com retry automático para erros transitórios."""
	if config is None:
		config = _get_config()

	url = f"{config['url_api']}{endpoint}"
	headers = _build_headers(config["api_key"])
	logger = _logger()

	for attempt in range(1, MAX_RETRIES + 1):
		try:
			response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
		except requests.RequestException as exc:
			raise WhatsAppRequestError(f"Falha de conexão ao chamar Evolution API: {exc}") from exc

		if response.status_code < 400:
			try:
				return response.json()
			except ValueError as exc:
				raise WhatsAppRequestError(
					"Evolution API retornou resposta inválida ao buscar grupos."
				) from exc

		if response.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
			try:
				detail = response.json()
			except ValueError:
				detail = response.text or "Sem detalhes."
			raise WhatsAppRequestError(f"Evolution API retornou HTTP {response.status_code}: {detail}")

		logger.warning(
			f"Evolution API HTTP {response.status_code} na tentativa {attempt}/{MAX_RETRIES}. Retentando..."
		)
		time.sleep(2 ** (attempt - 1))

	raise WhatsAppRequestError("Número máximo de tentativas atingido.")  # pragma: no cover


def _registrar_sucesso() -> None:
	frappe.db.set_single_value(SETTINGS_DOCTYPE, {"ultimo_envio_em": now_datetime(), "ultimo_erro": ""})
	frappe.db.commit()


def _registrar_erro(contexto: str) -> None:
	tb = frappe.get_traceback()
	frappe.log_error(tb, f"WhatsApp:{contexto}")
	frappe.db.set_single_value(SETTINGS_DOCTYPE, {"ultimo_erro": tb[-5000:]})
	frappe.db.commit()


# ─── Funções síncronas (chamadas diretamente ou via enqueue) ──────────────────


def _enviar_texto_sync(numero: str, mensagem: str) -> dict:
	config = _get_config()
	payload = {"number": _normalize_phone(numero), "text": mensagem}

	try:
		result = _post(f"/message/sendText/{config['nome_instancia']}", payload, config=config)
	except Exception:
		_registrar_erro(f"enviar_texto:{numero}")
		raise

	_registrar_sucesso()
	_logger().info(f"Mensagem de texto enviada para {numero}.")
	return result


def _enviar_midia_sync(numero: str, tipo: str, url_ou_base64: str, caption: str = "") -> dict:
	_TIPOS_VALIDOS = {"image", "document", "audio", "video"}
	if tipo not in _TIPOS_VALIDOS:
		raise WhatsAppRequestError(
			f"Tipo de mídia inválido: '{tipo}'. Use: {', '.join(sorted(_TIPOS_VALIDOS))}."
		)

	config = _get_config()
	payload: dict = {
		"number": _normalize_phone(numero),
		"mediatype": tipo,
		"media": url_ou_base64,
	}
	if caption:
		payload["caption"] = caption

	try:
		result = _post(f"/message/sendMedia/{config['nome_instancia']}", payload, config=config)
	except Exception:
		_registrar_erro(f"enviar_midia:{numero}:{tipo}")
		raise

	_registrar_sucesso()
	_logger().info(f"Mídia ({tipo}) enviada para {numero}.")
	return result


def _enviar_para_grupo_sync(
	grupo_jid: str,
	mensagem: str,
	*,
	mencionar_todos: bool = False,
) -> dict:
	config = _get_config()
	payload = {"number": grupo_jid, "text": mensagem}
	if mencionar_todos:
		payload["mentionsEveryOne"] = True

	try:
		result = _post(f"/message/sendText/{config['nome_instancia']}", payload, config=config)
	except Exception:
		_registrar_erro(f"enviar_para_grupo:{grupo_jid}")
		raise

	_registrar_sucesso()
	_logger().info(f"Mensagem enviada para grupo {grupo_jid}.")
	return result


def _enviar_mensagem_formatada_sync(
	numero: str,
	titulo: str,
	descricao: str,
	botoes: list[dict] | None = None,
) -> dict:
	config = _get_config()
	payload: dict = {
		"number": _normalize_phone(numero),
		"title": titulo,
		"description": descricao,
	}
	if botoes:
		payload["buttons"] = botoes

	try:
		result = _post(f"/message/sendButtons/{config['nome_instancia']}", payload, config=config)
	except Exception:
		_registrar_erro(f"enviar_mensagem_formatada:{numero}")
		raise

	_registrar_sucesso()
	_logger().info(f"Mensagem formatada enviada para {numero}.")
	return result


# ─── API Pública ──────────────────────────────────────────────────────────────


def listar_grupos_whatsapp(*, get_participants: bool = False) -> list[dict[str, str]]:
	"""Lista os grupos da instância WhatsApp conectada na Evolution API.

	Args:
		get_participants: Quando True, solicita também os participantes no endpoint da Evolution.

	Returns:
		Lista de grupos no formato [{"id": "...@g.us", "subject": "Nome do grupo"}].

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Falha de rede, HTTP ou payload inválido ao chamar a Evolution API.
	"""
	config = _get_config()
	params = {"getParticipants": str(bool(get_participants)).lower()}
	result = _get(
		f"/group/fetchAllGroups/{config['nome_instancia']}",
		params=params,
		config=config,
	)

	if not isinstance(result, list):
		raise WhatsAppRequestError("Formato inválido na resposta de listagem de grupos.")

	grupos: list[dict[str, str]] = []
	for item in result:
		if not isinstance(item, dict):
			continue

		grupo_id = str(item.get("id") or "").strip()
		if not grupo_id:
			continue

		subject = str(item.get("subject") or "").strip()
		grupos.append({"id": grupo_id, "subject": subject or grupo_id})

	return sorted(grupos, key=lambda grupo: grupo["subject"].casefold())


@frappe.whitelist()
def listar_grupos_whatsapp_para_select() -> list[dict[str, str]]:
	"""Retorna opções de grupos WhatsApp para uso em campos Select no Desk."""
	if not frappe.has_permission("Configuracoes de Recepcao", ptype="write"):
		frappe.throw(
			"Sem permissão para editar Configurações de Recepção.",
			frappe.PermissionError,
		)

	grupos = listar_grupos_whatsapp()
	return [
		{
			"label": f"{grupo['subject']} ({grupo['id']})",
			"value": grupo["id"],
		}
		for grupo in grupos
	]


def enviar_texto(numero: str, mensagem: str, *, enqueue: bool = True) -> dict | None:
	"""Envia mensagem de texto para um número WhatsApp.

	Args:
		numero: Número no formato internacional (ex.: "5511999999999", "+55 11 99999-9999").
		mensagem: Texto a enviar.
		enqueue: Se True (padrão), processa em background. Se False, executa de forma síncrona.

	Returns:
		Resposta da Evolution API (dict) no modo síncrono, ou None quando enfileirado.

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Falha de rede ou HTTP ao chamar a Evolution API (modo síncrono).
	"""
	if enqueue:
		frappe.enqueue(
			"gris.utils.whatsapp._enviar_texto_sync",
			queue="short",
			timeout=60,
			numero=numero,
			mensagem=mensagem,
		)
		return None
	return _enviar_texto_sync(numero, mensagem)


def enviar_midia(
	numero: str,
	tipo: str,
	url_ou_base64: str,
	*,
	caption: str = "",
	enqueue: bool = True,
) -> dict | None:
	"""Envia mídia (imagem, documento, áudio ou vídeo) para um número WhatsApp.

	Args:
		numero: Número no formato internacional.
		tipo: Tipo de mídia. Um de: "image", "document", "audio", "video".
		url_ou_base64: URL pública da mídia ou string base64 do arquivo.
		caption: Legenda opcional (suportada para imagem, documento e vídeo).
		enqueue: Se True (padrão), processa em background.

	Returns:
		Resposta da Evolution API (dict) no modo síncrono, ou None quando enfileirado.

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Tipo inválido, falha de rede ou HTTP (modo síncrono).
	"""
	if enqueue:
		frappe.enqueue(
			"gris.utils.whatsapp._enviar_midia_sync",
			queue="short",
			timeout=120,
			numero=numero,
			tipo=tipo,
			url_ou_base64=url_ou_base64,
			caption=caption,
		)
		return None
	return _enviar_midia_sync(numero, tipo, url_ou_base64, caption)


def enviar_para_grupo(
	grupo_jid: str,
	mensagem: str,
	*,
	mencionar_todos: bool = False,
	enqueue: bool = True,
) -> dict | None:
	"""Envia mensagem de texto para um grupo WhatsApp.

	Args:
		grupo_jid: JID do grupo no formato Evolution API (ex.: "5511999999999-1234567890@g.us").
		mensagem: Texto a enviar.
		mencionar_todos: Quando True, envia com menção geral para todos os participantes do grupo.
		enqueue: Se True (padrão), processa em background.

	Returns:
		Resposta da Evolution API (dict) no modo síncrono, ou None quando enfileirado.

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Falha de rede ou HTTP ao chamar a Evolution API (modo síncrono).
	"""
	if enqueue:
		frappe.enqueue(
			"gris.utils.whatsapp._enviar_para_grupo_sync",
			queue="short",
			timeout=60,
			grupo_jid=grupo_jid,
			mensagem=mensagem,
			mencionar_todos=mencionar_todos,
		)
		return None
	return _enviar_para_grupo_sync(
		grupo_jid,
		mensagem,
		mencionar_todos=mencionar_todos,
	)


def enviar_mensagem_formatada(
	numero: str,
	titulo: str,
	descricao: str,
	botoes: list[dict] | None = None,
	*,
	enqueue: bool = True,
) -> dict | None:
	"""Envia mensagem com título, descrição e botões interativos.

	Args:
		numero: Número no formato internacional.
		titulo: Título da mensagem.
		descricao: Descrição/corpo da mensagem.
		botoes: Lista de botões conforme Evolution API v2.
		        Exemplo: [{"buttonId": "1", "buttonText": {"displayText": "Confirmar"}, "type": "reply"}]
		enqueue: Se True (padrão), processa em background.

	Returns:
		Resposta da Evolution API (dict) no modo síncrono, ou None quando enfileirado.

	Raises:
		WhatsAppConfigurationError: Integração desabilitada ou configuração incompleta.
		WhatsAppRequestError: Falha de rede ou HTTP ao chamar a Evolution API (modo síncrono).
	"""
	if enqueue:
		frappe.enqueue(
			"gris.utils.whatsapp._enviar_mensagem_formatada_sync",
			queue="short",
			timeout=60,
			numero=numero,
			titulo=titulo,
			descricao=descricao,
			botoes=botoes,
		)
		return None
	return _enviar_mensagem_formatada_sync(numero, titulo, descricao, botoes)
