from __future__ import annotations

import frappe

from gris.api.gestao_adultos.summary_service import gerar_resumo_entrevista

INTERVIEW_DTYPE = "Entrevista por Competencias"


def enfileirar_resumo_entrevista(entrevista_name: str):
	if not entrevista_name:
		return

	frappe.enqueue(
		method="gris.api.gestao_adultos.summary_tasks.processar_resumo_entrevista",
		queue="long",
		timeout=600,
		enqueue_after_commit=True,
		entrevista_name=entrevista_name,
	)


def processar_resumo_entrevista(entrevista_name: str):
	if not entrevista_name:
		return

	try:
		resumo = gerar_resumo_entrevista(entrevista_name)
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Falha ao gerar resumo da entrevista {entrevista_name}",
		)
		return

	frappe.db.set_value(
		INTERVIEW_DTYPE,
		entrevista_name,
		"resumo",
		resumo,
		update_modified=False,
	)
