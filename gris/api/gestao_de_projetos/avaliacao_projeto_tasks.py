from __future__ import annotations

import frappe

from gris.api.gestao_de_projetos.avaliacao_projeto_service import (
	gerar_resumo_avaliacao_completa,
	gerar_resumo_avaliacoes_individuais,
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


def processar_resumo_individuais(avaliacao_name: str):
	"""Background job: gera resumo das avaliações individuais via LLM."""
	if not avaliacao_name:
		return

	try:
		resumo = gerar_resumo_avaliacoes_individuais(avaliacao_name)
	except LLMRequestError as exc:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Falha ao gerar resumo individuais da avaliação {avaliacao_name}",
		)
		user_message = _ERROR_429 if "HTTP 429" in str(exc) else _ERROR_GENERIC
		frappe.db.set_value(
			"Avaliacao de Projeto",
			avaliacao_name,
			"resumo_avaliacoes_individuais",
			user_message,
			update_modified=True,
		)
		return
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Falha ao gerar resumo individuais da avaliação {avaliacao_name}",
		)
		frappe.db.set_value(
			"Avaliacao de Projeto",
			avaliacao_name,
			"resumo_avaliacoes_individuais",
			_ERROR_GENERIC,
			update_modified=True,
		)
		return

	frappe.db.set_value(
		"Avaliacao de Projeto",
		avaliacao_name,
		"resumo_avaliacoes_individuais",
		resumo,
		update_modified=True,
	)


def processar_resumo_completo(avaliacao_name: str):
	"""Background job: gera resumo completo da avaliação via LLM."""
	if not avaliacao_name:
		return

	try:
		resumo = gerar_resumo_avaliacao_completa(avaliacao_name)
	except LLMRequestError as exc:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Falha ao gerar resumo completo da avaliação {avaliacao_name}",
		)
		user_message = _ERROR_429 if "HTTP 429" in str(exc) else _ERROR_GENERIC
		frappe.db.set_value(
			"Avaliacao de Projeto",
			avaliacao_name,
			"resumo_avaliacao_completa",
			user_message,
			update_modified=True,
		)
		return
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Falha ao gerar resumo completo da avaliação {avaliacao_name}",
		)
		frappe.db.set_value(
			"Avaliacao de Projeto",
			avaliacao_name,
			"resumo_avaliacao_completa",
			_ERROR_GENERIC,
			update_modified=True,
		)
		return

	frappe.db.set_value(
		"Avaliacao de Projeto",
		avaliacao_name,
		"resumo_avaliacao_completa",
		resumo,
		update_modified=True,
	)
