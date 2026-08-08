# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, flt, getdate

# Limite defensivo: um orçamento cobre no máximo 5 exercícios.
MAX_MESES_PERIODO = 60

DISTRIBUICAO_UNIFORME = "Uniforme no período"
DISTRIBUICAO_MES_ESPECIFICO = "Mês específico"


def primeiro_dia_do_mes(valor) -> date:
	"""Normaliza qualquer data para o primeiro dia do seu mês."""
	data = getdate(valor)
	return data.replace(day=1)


def meses_do_periodo(data_inicio, data_fim) -> list[str]:
	"""Lista os meses (``YYYY-MM``) cobertos pelo período, do mais antigo ao mais recente.

	Retorna lista vazia quando o período é inválido (fim anterior ao início).
	"""
	if not data_inicio or not data_fim:
		return []

	inicio = primeiro_dia_do_mes(data_inicio)
	fim = primeiro_dia_do_mes(data_fim)
	if fim < inicio:
		return []

	meses: list[str] = []
	cursor = inicio
	while cursor <= fim:
		meses.append(cursor.strftime("%Y-%m"))
		cursor = getdate(add_months(cursor, 1))
	return meses


def contar_meses(data_inicio, data_fim) -> int:
	"""Quantidade de meses do período, sem materializar a lista."""
	if not data_inicio or not data_fim:
		return 0

	inicio = primeiro_dia_do_mes(data_inicio)
	fim = primeiro_dia_do_mes(data_fim)
	if fim < inicio:
		return 0
	return (fim.year - inicio.year) * 12 + (fim.month - inicio.month) + 1


def distribuir_valor(valor, n_meses: int) -> list[float]:
	"""Divide um valor em ``n_meses`` parcelas cuja soma é exatamente o valor original.

	A divisão é feita em centavos; o resto é distribuído a partir do primeiro mês para
	evitar diferenças de arredondamento no total do orçamento.
	"""
	if n_meses <= 0:
		return []

	total_centavos = round(flt(valor) * 100)
	base, resto = divmod(total_centavos, n_meses)
	parcelas = [base] * n_meses
	for i in range(resto):
		parcelas[i] += 1
	return [p / 100.0 for p in parcelas]


def distribuicao_do_item(item, meses: list[str]) -> dict[str, float]:
	"""Retorna quanto do item é previsto em cada mês (``{"YYYY-MM": valor}``).

	``item`` pode ser um documento filho ou um dict com as mesmas chaves.
	"""
	if not meses:
		return {}

	get = item.get if isinstance(item, dict) else (lambda campo: getattr(item, campo, None))
	valor = flt(get("valor_previsto"))
	distribuicao = get("distribuicao") or DISTRIBUICAO_UNIFORME

	if distribuicao == DISTRIBUICAO_MES_ESPECIFICO:
		mes_referencia = get("mes_referencia")
		if not mes_referencia:
			return {}
		chave = primeiro_dia_do_mes(mes_referencia).strftime("%Y-%m")
		if chave not in meses:
			return {}
		return {chave: valor}

	parcelas = distribuir_valor(valor, len(meses))
	return dict(zip(meses, parcelas, strict=True))


class PrevisaoOrcamentaria(Document):
	def validate(self):
		self._validar_periodo()
		self._validar_itens()
		self.calcular_totais()

	def _validar_periodo(self):
		if getdate(self.data_inicio) > getdate(self.data_fim):
			frappe.throw(_("O início do período não pode ser posterior ao fim."))

		if contar_meses(self.data_inicio, self.data_fim) > MAX_MESES_PERIODO:
			frappe.throw(_("O período da previsão não pode ultrapassar {0} meses.").format(MAX_MESES_PERIODO))

	def _validar_itens(self):
		meses = set(self.meses())
		for item in self.itens or []:
			if flt(item.valor_previsto) <= 0:
				frappe.throw(_("Linha {0}: o valor previsto deve ser maior que zero.").format(item.idx))

			if item.distribuicao != DISTRIBUICAO_MES_ESPECIFICO:
				item.mes_referencia = None
				continue

			if not item.mes_referencia:
				frappe.throw(
					_("Linha {0}: informe o mês de referência para distribuição em mês específico.").format(
						item.idx
					)
				)

			item.mes_referencia = primeiro_dia_do_mes(item.mes_referencia)
			if item.mes_referencia.strftime("%Y-%m") not in meses:
				frappe.throw(
					_("Linha {0}: o mês de referência está fora do período da previsão.").format(item.idx)
				)

	def calcular_totais(self):
		receitas = sum(flt(i.valor_previsto) for i in self.itens or [] if i.tipo == "Receita")
		despesas = sum(flt(i.valor_previsto) for i in self.itens or [] if i.tipo == "Despesa")
		self.total_receitas_previstas = flt(receitas, 2)
		self.total_despesas_previstas = flt(despesas, 2)
		self.resultado_previsto = flt(receitas - despesas, 2)

	def meses(self) -> list[str]:
		"""Meses (``YYYY-MM``) cobertos pela previsão."""
		return meses_do_periodo(self.data_inicio, self.data_fim)

	def distribuicao_mensal(self) -> dict[str, dict[str, float]]:
		"""Previsto por mês, separado em receitas e despesas."""
		meses = self.meses()
		acumulado = {mes: {"receitas": 0.0, "despesas": 0.0} for mes in meses}
		for item in self.itens or []:
			chave = "receitas" if item.tipo == "Receita" else "despesas"
			for mes, valor in distribuicao_do_item(item, meses).items():
				acumulado[mes][chave] += valor
		for valores in acumulado.values():
			valores["receitas"] = flt(valores["receitas"], 2)
			valores["despesas"] = flt(valores["despesas"], 2)
		return acumulado
