"""Liga cada `Responsavel` ao cadastro de `Associado` da mesma pessoa.

Os dois DocTypes sempre derivaram o `name` do md5 do CPF, então a relação já estava no
banco — só nunca tinha sido escrita. Este patch a torna explícita, migra hobbies e
habilidades para o cadastro de associado e coloca essas pessoas no Conselho de
Responsáveis com a função de Responsável Legal.

Roda para quem tem pelo menos um vínculo: ser responsável é ter beneficiário. Quem ficou
sem nenhum (a recepção apaga o vínculo na desistência) não entra no conselho.

O resolver de CPF é o de `gris.utils.documento`, que cobre as três convenções de hash —
recalcular o md5 aqui acharia nada para a maior parte da base, sem erro nenhum. Para quem
já passou pela anonimização do funil e não tem mais CPF, sobra o `name`, que é a convenção
canônica.
"""

from __future__ import annotations

import frappe


def execute():
	for tabela in ("Responsavel", "Responsavel Vinculo", "Associado", "Unidade Organizacional"):
		if not frappe.db.table_exists(tabela):
			return
	if not frappe.db.has_column("Responsavel", "associado"):
		return

	from gris.api.pessoas import vincular_responsavel_ao_associado

	responsaveis = frappe.get_all(
		"Responsavel Vinculo",
		filters={"responsavel": ["is", "set"]},
		pluck="responsavel",
		distinct=True,
	)

	vinculados = 0
	sem_associado = 0
	com_erro = 0

	for responsavel in responsaveis:
		try:
			if vincular_responsavel_ao_associado(responsavel):
				vinculados += 1
			else:
				sem_associado += 1
		except Exception:
			# Um cadastro torto não pode derrubar o migrate inteiro: registra e segue.
			com_erro += 1
			frappe.log_error(
				title="Vincular responsável ao associado",
				message=f"{responsavel}\n\n{frappe.get_traceback()}",
			)

	print(
		f"  → Responsáveis que também são associados: {vinculados} vinculados, "
		f"{sem_associado} sem cadastro de associado, {com_erro} com erro"
	)
	frappe.db.commit()
