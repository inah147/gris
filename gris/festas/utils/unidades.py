# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _

UNIDADES = ("unidade", "kg", "g", "litro", "ml")

# Cada unidade aponta para (familia, fator de conversao para a unidade base da familia)
# Familias: massa (base g), volume (base ml), unidade (base unidade)
_FATORES = {
	"kg": ("massa", 1000.0),
	"g": ("massa", 1.0),
	"litro": ("volume", 1000.0),
	"ml": ("volume", 1.0),
	"unidade": ("unidade", 1.0),
}


def converter(quantidade: float | None, de_unidade: str, para_unidade: str) -> float:
	"""Converte `quantidade` de `de_unidade` para `para_unidade`.

	Lanca ValidationError quando as unidades nao pertencem a mesma familia.
	"""
	if quantidade is None:
		return 0.0
	if de_unidade not in _FATORES or para_unidade not in _FATORES:
		frappe.throw(
			_("Unidade de medida desconhecida: {0} ou {1}.").format(de_unidade, para_unidade)
		)

	familia_origem, fator_origem = _FATORES[de_unidade]
	familia_destino, fator_destino = _FATORES[para_unidade]

	if familia_origem != familia_destino:
		frappe.throw(
			_("Conversao incompativel entre {0} e {1}.").format(de_unidade, para_unidade)
		)

	return (float(quantidade) * fator_origem) / fator_destino
