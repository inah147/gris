# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ProdutodeVendaFesta(Document):
	def validate(self):
		self._validar_barraca()
		self._validar_expectativa_convite()
		self._calcular_preco_custo()
		self._calcular_margem_lucro()
		self._calcular_cenarios()
		self._calcular_vendas_realizadas()

	def on_update(self):
		self._reagregar_festa()

	def on_trash(self):
		self._reagregar_festa()

	def _validar_barraca(self):
		if not self.barraca:
			return
		festa_da_barraca = frappe.db.get_value("Barraca da Festa", self.barraca, "festa")
		if festa_da_barraca and festa_da_barraca != self.festa:
			frappe.throw(_("A barraca selecionada nao pertence a esta festa."))

	def _validar_expectativa_convite(self):
		if not self.faz_parte_convite:
			return
		if flt(self.expectativa_venda_por_pessoa) < 1:
			frappe.throw(_("Produtos do convite exigem expectativa de venda por pessoa maior ou igual a 1."))

	def _calcular_preco_custo(self):
		if not self.name or self.is_new():
			# Sem name persistido ainda; calculo definitivo acontece no proximo save.
			return
		usos = frappe.get_all(
			"Uso em Produto Festa",
			filters={"produto": self.name},
			fields=["valor_uso"],
		)
		self.preco_custo = sum(flt(u.valor_uso) for u in usos)

	def _calcular_margem_lucro(self):
		venda = flt(self.preco_venda)
		custo = flt(self.preco_custo)
		if venda <= 0:
			self.margem_lucro = 0
		else:
			self.margem_lucro = ((venda - custo) / venda) * 100

	def _calcular_cenarios(self):
		expectativa_pessoa = flt(self.expectativa_venda_por_pessoa)
		publicos = _carregar_publicos(self.festa)

		for chave, publico in publicos.items():
			qtd = expectativa_pessoa * publico
			custo_total = qtd * flt(self.preco_custo)
			receita_total = qtd * flt(self.preco_venda)
			superavit = receita_total - custo_total

			self.set(f"qtd_{chave}", qtd)
			self.set(f"custo_total_{chave}", custo_total)
			self.set(f"receita_total_{chave}", receita_total)
			self.set(f"superavit_{chave}", superavit)

	def _calcular_vendas_realizadas(self):
		self.valor_total_arrecadado = flt(self.qtd_realizada_vendas) * flt(self.preco_venda)

	def _reagregar_festa(self):
		if not self.festa:
			return
		try:
			festa_doc = frappe.get_doc("Festa", self.festa)
			festa_doc.save(ignore_permissions=True)
		except frappe.DoesNotExistError:
			return


def _carregar_publicos(festa: str | None) -> dict[str, float]:
	if not festa:
		return {"min": 0, "intermediario": 0, "max": 0}
	row = (
		frappe.db.get_value(
			"Festa",
			festa,
			[
				"expectativa_publico_min",
				"expectativa_publico_intermediario",
				"expectativa_publico_max",
			],
			as_dict=True,
		)
		or {}
	)
	return {
		"min": flt(row.get("expectativa_publico_min")),
		"intermediario": flt(row.get("expectativa_publico_intermediario")),
		"max": flt(row.get("expectativa_publico_max")),
	}
