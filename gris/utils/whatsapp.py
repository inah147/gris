from __future__ import annotations

import re
import time

import frappe
import requests
from frappe.utils import now_datetime

from .whatsapp_errors import WhatsAppConfigurationError, WhatsAppRequestError

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
		return digits

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
			raise WhatsAppRequestError(
				f"Evolution API retornou HTTP {response.status_code}: {detail}"
			)

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


def _enviar_para_grupo_sync(grupo_jid: str, mensagem: str) -> dict:
	config = _get_config()
	payload = {"number": grupo_jid, "text": mensagem}

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


def enviar_para_grupo(grupo_jid: str, mensagem: str, *, enqueue: bool = True) -> dict | None:
	"""Envia mensagem de texto para um grupo WhatsApp.

	Args:
		grupo_jid: JID do grupo no formato Evolution API (ex.: "5511999999999-1234567890@g.us").
		mensagem: Texto a enviar.
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
		)
		return None
	return _enviar_para_grupo_sync(grupo_jid, mensagem)


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
		        Exemplo: [{"buttonId": "1", "buttonText": {"displayText": "Confirmar"}, "type": 1}]
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
