from __future__ import annotations

import frappe

# Os lembretes da cobrança da contribuição passaram a sair no dia do vencimento, no
# dia seguinte (aviso de atraso) e depois de 7 em 7 dias. Quem ainda está com os
# padrões antigos (intervalo de 3 dias e 2 lembretes) ganha os novos; quem já
# ajustou algum dos dois à mão não é tocado.
DOCTYPE = "Configuracoes Contribuicao Mensal"
PADRAO_ANTIGO = {"dias_lembrete_apos_vencimento": "3", "max_lembretes": "2"}
PADRAO_NOVO = {"dias_lembrete_apos_vencimento": 7, "max_lembretes": 3}


def execute():
	atuais = {campo: frappe.db.get_single_value(DOCTYPE, campo, cache=False) for campo in PADRAO_ANTIGO}
	if all(str(atuais[campo]) == antigo for campo, antigo in PADRAO_ANTIGO.items()):
		frappe.db.set_single_value(DOCTYPE, PADRAO_NOVO)
