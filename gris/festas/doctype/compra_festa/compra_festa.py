# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from gris.festas.utils.unidades import converter

CENARIOS = ("min", "intermediario", "max")
_CENARIO_FIELD_MAP = {
	"Mínimo": "min",
	"Intermediário": "intermediario",
	"Máximo": "max",
}


class CompraFesta(Document):
	def validate(self):
		self._validar_area()
		self._validar_usos_em_produto()
		self._validar_cotacoes()
		self._validar_unidades()
		self._calcular_cenarios()
		self._calcular_quantidade_compra()
		self._calcular_valor_total()
		self._calcular_usos_em_produto()

	def on_update(self):
		self._reagregar_produtos()
		self._reagregar_festa()

	def on_trash(self):
		self._reagregar_produtos()
		self._reagregar_festa()

	def _validar_area(self):
		if not self.area:
			return
		festa_da_area = frappe.db.get_value("Area da Festa", self.area, "festa")
		if festa_da_area and festa_da_area != self.festa:
			frappe.throw(_("A area selecionada nao pertence a esta festa."))

	def _validar_usos_em_produto(self):
		for uso in self.usos_em_produto or []:
			if not uso.produto:
				continue
			festa_do_produto = frappe.db.get_value("Produto de Venda Festa", uso.produto, "festa")
			if festa_do_produto and festa_do_produto != self.festa:
				frappe.throw(_("O produto selecionado nao pertence a esta festa."))

	def _validar_cotacoes(self):
		escolhidas = [c for c in self.cotacoes or [] if c.escolhida]
		if len(escolhidas) > 1:
			frappe.throw(_("Apenas uma cotacao pode ser marcada como escolhida."))

	def _validar_unidades(self):
		"""Garante que cotacoes e usos sejam converciveis para a unidade de compra.

		`converter` lanca ValidationError quando as unidades pertencem a familias
		diferentes (ex.: litro vs kg), evitando calculos silenciosamente incorretos.
		"""
		escolhida = self._cotacao_escolhida()
		if escolhida and flt(escolhida.quantidade) > 0:
			converter(flt(escolhida.quantidade), escolhida.unidade_medida, self.unidade_compra)
		if self.usado_em_produtos:
			for uso in self.usos_em_produto or []:
				if not uso.unidade_medida_uso or not uso.quantidade_usada:
					continue
				converter(flt(uso.quantidade_usada), uso.unidade_medida_uso, self.unidade_compra)

	def _cotacao_escolhida(self):
		for c in self.cotacoes or []:
			if c.escolhida:
				return c
		return None

	def _calcular_cenarios(self):
		"""Calcula qtd sugerida, valor total, sobra e valor de sobra para cada cenário."""
		escolhida = self._cotacao_escolhida()

		# Dados da cotação escolhida.
		# Em doações, a quantidade do pacote continua valendo (para manter as
		# quantidades sugeridas), mas o valor é zerado.
		qtd_pacote = 0.0
		valor_pacote = 0.0
		if escolhida and flt(escolhida.quantidade) > 0:
			qtd_pacote = converter(flt(escolhida.quantidade), escolhida.unidade_medida, self.unidade_compra)
			valor_pacote = 0.0 if escolhida.doacao else flt(escolhida.valor)

		# Busca qtd_cenario dos produtos vinculados (query única, evita N+1)
		produtos_qtd = _carregar_qtd_cenarios_produtos(
			[uso.produto for uso in (self.usos_em_produto or []) if uso.produto]
		)

		for chave in CENARIOS:
			# ---------- quantidade sugerida (nº de cotações) ----------
			soma_cenario = 0.0
			if self.usado_em_produtos:
				# Varia com o público pelos produtos: para cada uso, qtd usada (na
				# unidade de compra) x qtd do produto no cenário (expectativa de venda
				# por pessoa x público), arredondado para cima em cotações inteiras.
				for uso in self.usos_em_produto or []:
					if not uso.produto or not uso.quantidade_usada or not uso.unidade_medida_uso:
						continue
					qtd_uso_em_compra = converter(
						flt(uso.quantidade_usada), uso.unidade_medida_uso, self.unidade_compra
					)
					qtd_produto_cenario = produtos_qtd.get(uso.produto, {}).get(chave, 0.0)
					soma_cenario += qtd_uso_em_compra * qtd_produto_cenario
				qtd_sugerida = _ceil_pacotes(soma_cenario, qtd_pacote)
			else:
				# Constante: a quantidade final já é o nº de cotações a comprar.
				qtd_sugerida = flt(self.quantidade_compra_final)

			# ---------- valor total ----------
			valor_total_cen = qtd_sugerida * valor_pacote if qtd_pacote > 0 else 0.0

			# ---------- sobra individual ----------
			# O que sobra das cotações compradas depois do consumo do cenário.
			if self.usado_em_produtos and qtd_pacote > 0:
				qtd_sobra = max(0.0, qtd_sugerida * qtd_pacote - soma_cenario)
			else:
				qtd_sobra = 0.0

			# ---------- valor de sobra ----------
			preco_unitario = (valor_pacote / qtd_pacote) if qtd_pacote > 0 else 0.0
			valor_sobra = qtd_sobra * preco_unitario

			self.set(f"qtd_sugerida_{chave}", qtd_sugerida)
			self.set(f"valor_total_{chave}", valor_total_cen)
			self.set(f"qtd_sobra_individual_{chave}", qtd_sobra)
			self.set(f"valor_sobra_{chave}", valor_sobra)

	def _calcular_quantidade_compra(self):
		"""Define quantidade_compra igual à qtd_sugerida do cenário escolhido na Festa."""
		cenario_festa = frappe.db.get_value("Festa", self.festa, "cenario_simulacao") or "Intermediário"
		chave = _CENARIO_FIELD_MAP.get(cenario_festa, "intermediario")
		self.quantidade_compra = flt(self.get(f"qtd_sugerida_{chave}"))

	def _calcular_valor_total(self):
		escolhida = self._cotacao_escolhida()
		if not escolhida or escolhida.doacao:
			self.cotacao_escolhida_valor = 0
			self.valor_total_compra = 0
			return

		self.cotacao_escolhida_valor = flt(escolhida.valor)

		# A quantidade final é o nº de cotações a comprar (ex.: 6 garrafas de
		# 500 ml), não a quantidade na unidade de compra. O custo é essa contagem
		# x o valor da cotação — mesmo cálculo do diálogo do portal.
		self.valor_total_compra = flt(self.quantidade_compra_final) * flt(escolhida.valor)

	def _calcular_usos_em_produto(self):
		escolhida = self._cotacao_escolhida()
		qtd_pacote = 0.0
		if escolhida and flt(escolhida.quantidade) > 0:
			qtd_pacote = converter(flt(escolhida.quantidade), escolhida.unidade_medida, self.unidade_compra)

		valor_total = flt(self.cotacao_escolhida_valor)
		for uso in self.usos_em_produto or []:
			if not uso.unidade_medida_uso or not uso.quantidade_usada:
				uso.fracao_item = 0
				uso.valor_uso = 0
				continue
			qtd_em_compra = converter(flt(uso.quantidade_usada), uso.unidade_medida_uso, self.unidade_compra)
			fracao = (qtd_em_compra / qtd_pacote) if qtd_pacote > 0 else 0
			uso.fracao_item = fracao
			uso.valor_uso = fracao * valor_total

	def _reagregar_produtos(self):
		produtos = {uso.produto for uso in self.usos_em_produto or [] if uso.produto}
		for nome in produtos:
			try:
				prod = frappe.get_doc("Produto de Venda Festa", nome)
				prod.save(ignore_permissions=True)
			except frappe.DoesNotExistError:
				continue

	def _reagregar_festa(self):
		if not self.festa:
			return
		try:
			festa_doc = frappe.get_doc("Festa", self.festa)
			festa_doc.save(ignore_permissions=True)
		except frappe.DoesNotExistError:
			return


# ---------- Helpers ----------


def _ceil_pacotes(qtd_total: float, qtd_pacote: float) -> float:
	"""Arredonda qtd_total para cima em múltiplos de pacotes. Retorna nº de pacotes."""
	if qtd_pacote <= 0:
		return 0.0
	# Arredonda antes do ceil para absorver o erro de ponto flutuante das
	# conversões (70 g x 100 = 7,000000000000001 kg não pode virar 8 pacotes).
	return float(math.ceil(round(qtd_total / qtd_pacote, 9)))


def _carregar_qtd_cenarios_produtos(nomes: list[str]) -> dict[str, dict[str, float]]:
	"""Retorna {nome_produto: {min: float, intermediario: float, max: float}}."""
	if not nomes:
		return {}
	rows = frappe.get_all(
		"Produto de Venda Festa",
		filters={"name": ("in", nomes)},
		fields=["name", "qtd_min", "qtd_intermediario", "qtd_max"],
	)
	return {
		r.name: {
			"min": flt(r.qtd_min),
			"intermediario": flt(r.qtd_intermediario),
			"max": flt(r.qtd_max),
		}
		for r in rows
	}
