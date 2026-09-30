from __future__ import annotations

import frappe

# O cronograma das atividades de captação passou a contar dias do projeto (dia 0, dia
# 10…) em vez de datas de calendário: o projeto só começa de verdade quando um edital
# o financia. Antes disso ele guardou datas de início e término. As colunas antigas
# ficam no banco — o Frappe não apaga coluna removida do DocType —, e aqui viram dias:
# a primeira data de cada projeto é o dia 0.
DOCTYPE = "Atividade de Projeto de Captacao"


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return
	if not (frappe.db.has_column(DOCTYPE, "data_inicio") and frappe.db.has_column(DOCTYPE, "data_termino")):
		return

	# Datas eram dias inteiros e inclusivos (1º a 31 de janeiro são 31 dias); em dias do
	# projeto o intervalo é contínuo, então o término anda um dia. Só toca linha que
	# ainda está em 0 a 0, para rodar de novo sem estragar o que já foi convertido.
	frappe.db.sql(
		"""
		UPDATE `tabAtividade de Projeto de Captacao` a
		JOIN (
			SELECT parent, MIN(COALESCE(data_inicio, data_termino)) AS dia_zero
			FROM `tabAtividade de Projeto de Captacao`
			GROUP BY parent
		) b ON b.parent = a.parent
		SET a.dia_inicio = DATEDIFF(COALESCE(a.data_inicio, a.data_termino), b.dia_zero),
			a.dia_termino = DATEDIFF(COALESCE(a.data_termino, a.data_inicio), b.dia_zero) + 1
		WHERE b.dia_zero IS NOT NULL
			AND COALESCE(a.data_inicio, a.data_termino) IS NOT NULL
			AND a.dia_inicio = 0
			AND a.dia_termino = 0
		"""
	)
