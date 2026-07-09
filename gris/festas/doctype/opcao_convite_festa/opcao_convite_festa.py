# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, nowdate


def lote_vigente(lotes: list, hoje=None) -> dict | None:
	"""Retorna o lote cujo período contém ``hoje`` (ou None se nenhum for válido).

	``lotes`` é uma lista de linhas ``Lote Opcao Convite Festa`` (docs ou dicts).
	"""
	hoje = getdate(hoje or nowdate())
	for lote in lotes or []:
		inicio = lote.get("data_inicio") if isinstance(lote, dict) else lote.data_inicio
		fim = lote.get("data_fim") if isinstance(lote, dict) else lote.data_fim
		if not inicio or not fim:
			continue
		if getdate(inicio) <= hoje <= getdate(fim):
			return lote
	return None


def _ultimo_lote(lotes: list) -> dict | None:
	"""Retorna o lote com a maior data de término (referência quando não há vigente)."""
	validos = [
		lote
		for lote in (lotes or [])
		if (lote.get("data_fim") if isinstance(lote, dict) else lote.data_fim)
	]
	if not validos:
		return None
	return max(
		validos,
		key=lambda lote: getdate(
			lote.get("data_fim") if isinstance(lote, dict) else lote.data_fim
		),
	)


class OpcaoConviteFesta(Document):
	def validate(self):
		self._validar_nome_unico_por_festa()
		self._aplicar_lote_vigente()

	def _validar_nome_unico_por_festa(self):
		if not self.festa or not self.nome_convite:
			return
		nome_esperado = f"{self.festa} - {self.nome_convite}"
		# Em edição: se o name não muda, é o mesmo registro.
		if not self.is_new() and self.name == nome_esperado:
			return
		if frappe.db.exists("Opcao Convite Festa", nome_esperado):
			frappe.throw(
				_("Já existe uma opção de convite com este nome para a festa selecionada.")
			)

	def _aplicar_lote_vigente(self):
		"""Define ``valor``/``valor_consumacao``/``ativo`` a partir dos lotes.

		- Portaria: não usa lotes; mantém valores fixos.
		- Sem lotes cadastrados: modo manual (não altera valor/ativo).
		- Com lotes: usa o lote vigente; se nenhum for vigente, desativa o
		  convite e mantém o último lote como referência de valor.
		"""
		if self.portaria:
			self.lotes = []
			self._validar_consumacao_nao_excede_valor(flt(self.valor), flt(self.valor_consumacao))
			return

		if not self.lotes:
			self._validar_consumacao_nao_excede_valor(flt(self.valor), flt(self.valor_consumacao))
			return

		for lote in self.lotes:
			if lote.data_inicio and lote.data_fim and getdate(lote.data_fim) < getdate(lote.data_inicio):
				frappe.throw(_("A data de término de um lote não pode ser anterior à de início."))
			self._validar_consumacao_nao_excede_valor(flt(lote.valor), flt(lote.valor_consumacao))

		vigente = lote_vigente(self.lotes)
		if vigente:
			self.valor = flt(vigente.valor)
			self.valor_consumacao = flt(vigente.valor_consumacao)
			return

		# Nenhum lote vigente: desativa a venda e mantém o último lote como referência.
		self.ativo = 0
		ultimo = _ultimo_lote(self.lotes)
		if ultimo:
			self.valor = flt(ultimo.valor)
			self.valor_consumacao = flt(ultimo.valor_consumacao)

	def _validar_consumacao_nao_excede_valor(self, valor: float, consumacao: float):
		if consumacao > valor:
			frappe.throw(_("O valor de consumação não pode ser maior que o valor do convite."))


def atualizar_lotes_opcoes_convite() -> dict[str, int]:
	"""Job diário: reavalia o lote vigente das opções de convite com lotes.

	Recalcula valor/consumação/ativo conforme a data atual, para festas em
	andamento. Só toca opções não-portaria que possuem lotes cadastrados.
	"""
	festas = frappe.get_all("Festa", filters={"status": "Em andamento"}, pluck="name")
	if not festas:
		return {"avaliadas": 0, "atualizadas": 0}

	opcoes = frappe.get_all(
		"Opcao Convite Festa",
		filters={"festa": ("in", festas), "portaria": 0},
		pluck="name",
	)
	avaliadas = 0
	atualizadas = 0
	for nome in opcoes:
		doc = frappe.get_doc("Opcao Convite Festa", nome)
		if not doc.lotes:
			continue
		avaliadas += 1
		antes = {
			"valor": flt(doc.valor),
			"valor_consumacao": flt(doc.valor_consumacao),
			"ativo": cint(doc.ativo),
		}
		doc._aplicar_lote_vigente()
		mudou = {
			campo: valor
			for campo, valor in {
				"valor": flt(doc.valor),
				"valor_consumacao": flt(doc.valor_consumacao),
				"ativo": cint(doc.ativo),
			}.items()
			if valor != antes[campo]
		}
		if mudou:
			frappe.db.set_value("Opcao Convite Festa", nome, mudou, update_modified=False)
			atualizadas += 1
	if atualizadas:
		frappe.db.commit()
	return {"avaliadas": avaliadas, "atualizadas": atualizadas}
