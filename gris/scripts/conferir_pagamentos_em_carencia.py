"""Lista os Pagamento Contribuicao Mensal gerados dentro da carência de registro.

Somente leitura: nada é apagado nem alterado. O financeiro usa a lista para decidir
o que remover dos meses que a geração mensal criou antes de respeitar a carência.

    bench --site <site> execute gris.scripts.conferir_pagamentos_em_carencia.executar
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate

from gris.api.financeiro.contribuicoes import (
	get_datas_de_ingresso,
	get_parametros,
	resolver_inicio_do_pagamento,
)


def listar() -> list[dict]:
	pagamentos = frappe.get_all(
		"Pagamento Contribuicao Mensal",
		fields=["name", "associado", "mes_de_referencia", "status", "valor"],
		order_by="associado asc, mes_de_referencia asc",
		limit_page_length=0,
	)
	if not pagamentos:
		return []

	nomes = sorted({p["associado"] for p in pagamentos})
	associados = {
		a["name"]: a
		for a in frappe.get_all(
			"Associado",
			filters={"name": ["in", nomes]},
			fields=["name", "nome_completo", "tipo_registro", "inicio_do_pagamento"],
			limit_page_length=0,
		)
	}
	ingressos = get_datas_de_ingresso(nomes)
	parametros = get_parametros()

	encontrados = []
	for pagamento in pagamentos:
		associado = associados.get(pagamento["associado"])
		if not associado:
			continue
		inicio = resolver_inicio_do_pagamento(
			{**associado, "data_de_ingresso": ingressos.get(associado["name"])}, parametros
		)
		if inicio and getdate(pagamento["mes_de_referencia"]) < inicio:
			encontrados.append(
				{
					"pagamento": pagamento["name"],
					"associado": associado["name"],
					"nome": associado["nome_completo"],
					"mes_de_referencia": str(pagamento["mes_de_referencia"]),
					"inicio_do_pagamento": str(inicio),
					"status": pagamento["status"],
					"valor": pagamento["valor"],
				}
			)
	return encontrados


def executar() -> None:
	encontrados = listar()
	print(f"{len(encontrados)} pagamento(s) gerado(s) dentro da carência.")
	for item in encontrados:
		print(
			f"{item['pagamento']}\t{item['nome']}\tmês {item['mes_de_referencia']}"
			f"\tinício {item['inicio_do_pagamento']}\t{item['status']}\tR$ {item['valor']}"
		)
