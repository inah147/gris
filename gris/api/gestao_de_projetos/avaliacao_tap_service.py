from __future__ import annotations

from gris.api.gestao_de_projetos.prompt_builder import (
	construir_prompts_revisao_tap,
	normalizar_formato_revisao_tap,
)
from gris.api.llm.client import gerar_resposta_modelo
from gris.api.llm.errors import LLMRequestError

FALLBACK_MODEL_ON_429 = "openai/gpt-4o-mini"


def gerar_avaliacao_tap(projeto_name: str) -> str:
	system_prompt, user_prompt = construir_prompts_revisao_tap(projeto_name)
	try:
		raw_output = gerar_resposta_modelo(
			system_prompt=system_prompt,
			user_prompt=user_prompt,
		)
	except LLMRequestError as exc:
		if "HTTP 429" not in str(exc):
			raise

		# Fallback para modelo estável quando o provedor configurado estiver limitando tráfego.
		raw_output = gerar_resposta_modelo(
			system_prompt=system_prompt,
			user_prompt=user_prompt,
			model=FALLBACK_MODEL_ON_429,
		)

	return normalizar_formato_revisao_tap(raw_output)
