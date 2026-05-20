# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Utilitários compartilhados para reagir a eventos de Cobranca Infinitepay.

Os módulos consumidores (Festas, futuras integrações) recebem o documento
em handlers registrados via `doc_events` em `hooks.py` e usam este utilitário
para decidir se uma transição de status é interessante para sua lógica.
"""

from __future__ import annotations


def status_mudou_para(doc, target: str) -> bool:
	"""True quando o status atual do doc é `target` E era diferente antes do save.

	Garante que handlers sejam idempotentes em saves subsequentes que não
	mudaram o status (ex.: atualização de outros campos por outros hooks).
	"""
	if getattr(doc, "status", None) != target:
		return False
	old = doc.get_doc_before_save()
	if old is None:
		return True
	return getattr(old, "status", None) != target
