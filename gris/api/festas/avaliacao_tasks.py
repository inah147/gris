from __future__ import annotations

from collections.abc import Callable

import frappe

from gris.api.festas.avaliacao_service import (
	gerar_resumo_avaliacao_completa_festa,
	gerar_resumo_avaliacoes_convidados_festa,
	gerar_resumo_avaliacoes_individuais_festa,
)
from gris.api.llm.errors import LLMRequestError

_ERROR_429 = (
	"Serviço de IA temporariamente indisponível por limite de uso (HTTP 429). "
	"Tente novamente em alguns minutos."
)
_ERROR_GENERIC = (
	"Não foi possível gerar o resumo por IA no momento. "
	"Verifique a configuração do provedor e tente novamente."
)


def _processar(avaliacao_name: str, campo: str, gerar: Callable[[str], str]) -> None:
	if not avaliacao_name:
		return

	try:
		resumo = gerar(avaliacao_name)
	except LLMRequestError as exc:
		frappe.log_error(
			message=frappe.get_traceback(), title=f"Falha ao gerar {campo} da avaliação {avaliacao_name}"
		)
		resumo = _ERROR_429 if "HTTP 429" in str(exc) else _ERROR_GENERIC
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(), title=f"Falha ao gerar {campo} da avaliação {avaliacao_name}"
		)
		resumo = _ERROR_GENERIC

	frappe.db.set_value("Avaliacao Festa", avaliacao_name, campo, resumo, update_modified=True)


def processar_resumo_individuais_festa(avaliacao_name: str) -> None:
	"""Background job: gera o resumo das avaliações individuais da equipe."""
	_processar(avaliacao_name, "resumo_avaliacoes_individuais", gerar_resumo_avaliacoes_individuais_festa)


def processar_resumo_completo_festa(avaliacao_name: str) -> None:
	"""Background job: gera o resumo completo da avaliação."""
	_processar(avaliacao_name, "resumo_avaliacao_completa", gerar_resumo_avaliacao_completa_festa)


def processar_resumo_convidados_festa(avaliacao_name: str) -> None:
	"""Background job: gera o resumo das avaliações dos convidados."""
	_processar(avaliacao_name, "resumo_avaliacoes_convidados", gerar_resumo_avaliacoes_convidados_festa)
