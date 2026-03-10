from __future__ import annotations

import frappe
import requests

from .errors import LLMConfigurationError, LLMRequestError

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_TIMEOUT = 45


def _get_openrouter_api_key() -> str:
	settings = frappe.get_single("Configuracoes LLM")
	api_key = settings.get_password("api_key", raise_exception=False)
	if not api_key:
		raise LLMConfigurationError("API key não configurada em Configuracoes LLM.")
	return api_key


def _get_openrouter_model() -> str:
	settings = frappe.get_single("Configuracoes LLM")
	configured_model = (settings.get("modelo") or settings.get("model") or "").strip()
	return configured_model or DEFAULT_MODEL


def _extract_openrouter_error_detail(response: requests.Response) -> str:
	try:
		data = response.json()
	except ValueError:
		return (response.text or "").strip() or "Erro sem detalhes retornados."

	error = data.get("error") if isinstance(data, dict) else None
	if isinstance(error, dict):
		message = str(error.get("message") or "").strip()
		code = str(error.get("code") or "").strip()
		if code and message:
			return f"{code}: {message}"
		if message:
			return message

	message = (data.get("message") or "").strip() if isinstance(data, dict) else ""
	if message:
		return message

	return "Erro sem detalhes retornados."


def _extract_message_content(response_json: dict) -> str:
	message = ((response_json.get("choices") or [{}])[0] or {}).get("message", {})
	content = message.get("content", "")

	if isinstance(content, str):
		return content.strip()

	if isinstance(content, list):
		parts: list[str] = []
		for item in content:
			if isinstance(item, dict):
				text = item.get("text")
				if isinstance(text, str) and text.strip():
					parts.append(text.strip())
			elif isinstance(item, str) and item.strip():
				parts.append(item.strip())

		return "\n".join(parts).strip()

	return ""


def gerar_resposta_modelo(
	*,
	system_prompt: str,
	user_prompt: str,
	model: str | None = None,
	temperature: float = 0.2,
) -> str:
	if not system_prompt:
		raise LLMRequestError("Prompt de sistema vazio para chamada ao modelo.")

	if not user_prompt:
		raise LLMRequestError("Prompt de usuário vazio para chamada ao modelo.")

	api_key = _get_openrouter_api_key()
	request_model = (model or _get_openrouter_model() or DEFAULT_MODEL).strip()
	headers = {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
		"HTTP-Referer": frappe.utils.get_url(),
		"X-Title": "GRIS - Entrevista por Competências",
	}
	payload = {
		"model": request_model,
		"temperature": temperature,
		"messages": [
			{
				"role": "system",
				"content": system_prompt,
			},
			{
				"role": "user",
				"content": user_prompt,
			}
		],
	}

	try:
		response = requests.post(
			OPENROUTER_ENDPOINT,
			headers=headers,
			json=payload,
			timeout=DEFAULT_TIMEOUT,
		)
	except requests.RequestException as exc:
		raise LLMRequestError("Falha de conexão ao consultar OpenRouter.") from exc

	if response.status_code >= 400:
		detail = _extract_openrouter_error_detail(response)
		raise LLMRequestError(
			f"OpenRouter retornou HTTP {response.status_code} para modelo '{request_model}': {detail}"
		)

	try:
		data = response.json()
	except ValueError as exc:
		raise LLMRequestError("Resposta inválida recebida do OpenRouter.") from exc

	content = _extract_message_content(data)
	if not isinstance(content, str) or not content.strip():
		raise LLMRequestError("OpenRouter não retornou conteúdo textual na resposta.")

	return content.strip()
