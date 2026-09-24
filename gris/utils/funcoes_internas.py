# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Regras da grade `funcoes_internas`, compartilhadas por quem a tem.

A grade nasceu só no `Associado` e as regras viviam no controller dele. Quando o
`Responsavel` passou a poder receber função no organograma, copiar as validações para o
segundo controller criaria duas versões da mesma regra — e é exatamente assim que uma
delas fica para trás.

O child `Funcao do Associado` guarda `parenttype` por linha, então o DocType serve aos dois
pais; o que precisava virar comum eram as validações. Elas não olham para nada específico
de associado: só para as linhas e para o catálogo de `Unidade Organizacional.funcoes`.
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate


def validar_funcoes_internas(doc) -> None:
	"""Só uma função pode ser a principal, e o período tem que fazer sentido.

	A principal é a que o organograma mostra no card; com duas marcadas a escolha viraria
	sorteio pela ordem das linhas.
	"""
	principais = [linha for linha in (doc.funcoes_internas or []) if linha.principal]
	if len(principais) > 1:
		frappe.throw(
			frappe._("Marque apenas uma função interna como principal (há {0} marcadas).").format(
				len(principais)
			)
		)

	for linha in doc.funcoes_internas or []:
		if linha.data_inicio and linha.data_fim and getdate(linha.data_fim) < getdate(linha.data_inicio):
			frappe.throw(
				frappe._("Função interna na linha {0}: a data de fim é anterior à de início.").format(
					linha.idx
				)
			)


def validar_vinculo_funcao_area(doc) -> None:
	"""Toda função interna nova precisa de área, e o par tem que estar vinculado.

	A área é o que posiciona a pessoa no organograma, e o vínculo válido mora em
	`Unidade Organizacional.funcoes`.

	Os recortes abaixo não são zelo, e é por eles que a área não é `reqd` no schema:
	existem linhas antigas de funções que nunca tiveram área, e existem linhas cujo vínculo
	pode ser desfeito depois. Validar tudo tornaria esses cadastros insalváveis para sempre
	— e o `Associado` é gravado em lote pela importação do Paxtu, pela cobrança e pela
	recepção, que quebrariam semanas depois por uma edição sem relação aparente. Então só
	entram as linhas que entraram ou mudaram agora, e que ainda estão em vigor.
	"""
	if frappe.flags.in_migrate or frappe.flags.in_patch or frappe.flags.in_install:
		return

	anterior = doc.get_doc_before_save()
	antes = {(linha.funcao, linha.area) for linha in (anterior.funcoes_internas or [])} if anterior else set()

	hoje = getdate()
	suspeitas = [
		linha
		for linha in (doc.funcoes_internas or [])
		if linha.funcao
		# Linha que já existia assim não é problema novo: só o que entrou ou mudou.
		and (linha.funcao, linha.area) not in antes
		# Histórico é imutável e não precisa obedecer ao catálogo de hoje.
		and (not linha.data_fim or getdate(linha.data_fim) >= hoje)
	]
	if not suspeitas:
		return

	for linha in suspeitas:
		if not linha.area:
			frappe.throw(
				frappe._("Função interna na linha {0}: escolha a área onde {1} é exercida.").format(
					linha.idx, frappe.bold(linha.funcao)
				)
			)

	permitidos = {
		(vinculo["funcao"], vinculo["parent"])
		for vinculo in frappe.get_all(
			"Funcao da Area",
			filters={
				"parenttype": "Unidade Organizacional",
				"parent": ["in", sorted({linha.area for linha in suspeitas})],
			},
			fields=["parent", "funcao"],
		)
	}
	for linha in suspeitas:
		if (linha.funcao, linha.area) not in permitidos:
			frappe.throw(
				frappe._(
					"Função interna na linha {0}: {1} não está vinculada à área {2}. "
					"Vincule a função na unidade organizacional ou escolha outra área."
				).format(linha.idx, frappe.bold(linha.funcao), frappe.bold(linha.area))
			)
