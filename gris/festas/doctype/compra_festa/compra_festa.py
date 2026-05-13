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
		self._calcular_quantidade_compra_base()
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

	def _cotacao_escolhida(self):
		for c in self.cotacoes or []:
			if c.escolhida:
				return c
		return None

	def _calcular_quantidade_compra_base(self):
		"""Calcula a soma total de uso em unidade de compra (para itens usados em produtos)."""
		if not self.usado_em_produtos:
			return
		total = 0.0
		for uso in self.usos_em_produto or []:
			if not uso.unidade_medida_uso or not uso.quantidade_usada:
				continue
			total += converter(flt(uso.quantidade_usada), uso.unidade_medida_uso, self.unidade_compra)
		# Armazena internamente para uso em _calcular_cenarios
		self._soma_uso_total = total

	def _calcular_cenarios(self):
		"""Calcula qtd sugerida, valor total, sobra e valor de sobra para cada cenário."""
		escolhida = self._cotacao_escolhida()
		soma_uso = getattr(self, "_soma_uso_total", 0.0)

		# Dados da cotação escolhida
		qtd_pacote = 0.0
		valor_pacote = 0.0
		if escolhida and not escolhida.doacao and flt(escolhida.quantidade) > 0:
			try:
				qtd_pacote = converter(
					flt(escolhida.quantidade), escolhida.unidade_medida, self.unidade_compra
				)
			except Exception:
				qtd_pacote = 0.0
			valor_pacote = flt(escolhida.valor)

		# Busca público por cenário da festa
		publicos = _carregar_publicos_festa(self.festa)

		# Busca qtd_cenario dos produtos vinculados (query única, evita N+1)
		produtos_qtd = _carregar_qtd_cenarios_produtos(
			[uso.produto for uso in (self.usos_em_produto or []) if uso.produto]
		)

		for chave in CENARIOS:
			# ---------- quantidade sugerida ----------
			if self.usado_em_produtos:
				# soma: para cada uso, converter qtd para unidade_compra × qtd do produto no cenário
				soma_cenario = 0.0
				for uso in self.usos_em_produto or []:
					if not uso.produto or not uso.quantidade_usada or not uso.unidade_medida_uso:
						continue
					qtd_uso_em_compra = converter(
						flt(uso.quantidade_usada), uso.unidade_medida_uso, self.unidade_compra
					)
					qtd_produto_cenario = produtos_qtd.get(uso.produto, {}).get(chave, 0.0)
					soma_cenario += qtd_uso_em_compra * qtd_produto_cenario
				qtd_sugerida = _ceil_pacotes(soma_cenario, qtd_pacote)
			elif self.varia_com_publico:
				# qtd_compra_final é "por pessoa" × expectativa do cenário
				qtd_sugerida = _ceil_pacotes(flt(self.quantidade_compra_final) * publicos[chave], qtd_pacote)
			else:
				# constante: mesmo valor para todos os cenários
				qtd_sugerida = _ceil_pacotes(flt(self.quantidade_compra_final), qtd_pacote)

			# ---------- valor total ----------
			valor_total_cen = qtd_sugerida * valor_pacote if qtd_pacote > 0 else 0.0

			# ---------- sobra individual ----------
			if self.usado_em_produtos and qtd_pacote > 0:
				qtd_sobra = max(0.0, qtd_sugerida * qtd_pacote - soma_uso)
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

		valor = flt(escolhida.valor)
		self.cotacao_escolhida_valor = valor

		quantidade_final = flt(self.quantidade_compra_final)
		if quantidade_final <= 0:
			self.valor_total_compra = 0
			return

		self.valor_total_compra = quantidade_final * valor

	def _calcular_usos_em_produto(self):
		escolhida = self._cotacao_escolhida()
		qtd_pacote = 0.0
		if escolhida and not escolhida.doacao and flt(escolhida.quantidade) > 0:
			try:
				qtd_pacote = converter(
					flt(escolhida.quantidade), escolhida.unidade_medida, self.unidade_compra
				)
			except Exception:
				qtd_pacote = 0.0
		
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
	return float(math.ceil(qtd_total / qtd_pacote))


def _carregar_publicos_festa(festa: str | None) -> dict[str, float]:
	if not festa:
		return {"min": 0.0, "intermediario": 0.0, "max": 0.0}
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
