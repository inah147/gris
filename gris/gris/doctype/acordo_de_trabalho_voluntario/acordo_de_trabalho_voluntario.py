# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Acordo de Trabalho Voluntário (ATV) de uma função interna.

O acordo cobre **uma alocação**, não uma pessoa nem uma função em abstrato: a mesma
pessoa pode exercer duas funções e ter um acordo diferente para cada uma. A alocação é
a linha de ``Associado.funcoes_internas`` (child ``Funcao do Associado``), identificada
por ``linha_funcao``.

``linha_funcao`` é ``Data`` e não ``Link`` porque não há como apontar um Link para uma
child table. O ``name`` da linha é identidade estável: os endpoints do portal carregam
o Associado com ``get_doc`` e mutam a linha no lugar, o que preserva o ``name`` — e é
esse mesmo valor que a interface já trafega como ``linha``.

``funcao`` e ``area`` são cópias da linha, preenchidas aqui a partir dela e nunca do que
o cliente mandou: servem para listar os acordos sem abrir o Associado (cuja grade de
funções vive em permlevel 2).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class AcordodeTrabalhoVoluntario(Document):
	def validate(self):
		self._validar_periodo()
		self._espelhar_linha_da_funcao()

	def _validar_periodo(self):
		if self.data_inicio and self.data_fim and getdate(self.data_fim) < getdate(self.data_inicio):
			frappe.throw(_("A data de término do acordo é anterior à de início."))

	def _espelhar_linha_da_funcao(self):
		"""Confere que a linha existe, é daquela pessoa, e copia função e área dela.

		Sem esta checagem o acordo poderia ser gravado apontando para a alocação de
		outra pessoa — e a página de ATVs, que lista por ``linha_funcao``, mostraria o
		acordo no nome errado.
		"""
		linha = frappe.db.get_value(
			"Funcao do Associado",
			self.linha_funcao,
			["parent", "parenttype", "funcao", "area"],
			as_dict=True,
		)
		if not linha or linha.parenttype != "Associado":
			frappe.throw(_("Função interna não encontrada."), frappe.DoesNotExistError)
		if linha.parent != self.associado:
			frappe.throw(_("Esta função não é da pessoa informada."))

		self.funcao = linha.funcao
		self.area = linha.area
