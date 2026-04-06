from __future__ import annotations

import frappe

from gris.api.gestao_de_projetos.avaliacao_tap_service import gerar_avaliacao_tap
from gris.api.llm.errors import LLMRequestError


def processar_avaliacao_tap(projeto_name: str):
	if not projeto_name:
		return

	try:
		avaliacao = gerar_avaliacao_tap(projeto_name)
	except LLMRequestError as exc:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Falha ao gerar avaliação TAP do projeto {projeto_name}",
		)

		error_text = str(exc)
		if "HTTP 429" in error_text:
			user_message = "Serviço de IA temporariamente indisponível por limite de uso (HTTP 429). Tente novamente em alguns minutos."
		else:
			user_message = "Não foi possível gerar a avaliação por IA no momento. Verifique a configuração do provedor e tente novamente."

		frappe.db.set_value(
			"Projeto",
			projeto_name,
			"avaliacao_tap",
			user_message,
			update_modified=True,
		)
		return
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Falha ao gerar avaliação TAP do projeto {projeto_name}",
		)
		frappe.db.set_value(
			"Projeto",
			projeto_name,
			"avaliacao_tap",
			"Não foi possível gerar a avaliação por IA no momento. Tente novamente.",
			update_modified=True,
		)
		return

	frappe.db.set_value(
		"Projeto",
		projeto_name,
		"avaliacao_tap",
		avaliacao,
		update_modified=True,
	)
