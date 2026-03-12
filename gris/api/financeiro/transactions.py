"""
API para gerenciamento de transações financeiras em lote
"""

import json

import frappe


@frappe.whitelist()
def batch_update_transactions(transaction_ids, updates):
	"""
	Atualiza múltiplas transações de uma vez

	Args:
		transaction_ids: Lista de IDs das transações a serem atualizadas (JSON string ou lista)
		updates: Dicionário com os campos a serem atualizados (JSON string ou dict)

	Returns:
		dict: Resultado da operação com contagem de registros atualizados
	"""
	# Parse JSON strings se necessário
	if isinstance(transaction_ids, str):
		transaction_ids = json.loads(transaction_ids)

	if isinstance(updates, str):
		updates = json.loads(updates)

	if not transaction_ids or not isinstance(transaction_ids, list):
		frappe.throw("IDs de transações inválidos")

	if not updates or not isinstance(updates, dict):
		frappe.throw("Dados de atualização inválidos")

	# Campos permitidos para atualização em lote
	allowed_fields = [
		"descricao_reduzida",
		"categoria",
		"centro_de_custo",
		"ordinaria_extraordinaria",
		"transacao_revisada",
	]

	# Valida que apenas campos permitidos estão sendo atualizados
	for field in updates.keys():
		if field not in allowed_fields:
			frappe.throw(f"Campo '{field}' não permitido para atualização em lote")

	updated_count = 0

	for transaction_id in transaction_ids:
		try:
			doc = frappe.get_doc("Transacao Extrato Geral", transaction_id)

			# Aplica as atualizações
			for field, value in updates.items():
				if hasattr(doc, field):
					setattr(doc, field, value)

			doc.save(ignore_permissions=False)
			updated_count += 1

		except frappe.DoesNotExistError:
			frappe.log_error(f"Transação {transaction_id} não encontrada")
			continue
		except Exception as e:
			frappe.log_error(f"Erro ao atualizar transação {transaction_id}: {e!s}")
			continue

	frappe.db.commit()

	return {"success": True, "updated_count": updated_count, "total_requested": len(transaction_ids)}
