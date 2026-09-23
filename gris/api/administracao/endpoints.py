"""Escrita da estrutura da UEL: áreas e funções, pelo portal.

Toda mutação abre com `garantir_gestor_estrutura()`. Os documentos são gravados
com `save()`, sem `ignore_permissions`: `Gestor da UEL` tem write declarado nos
dois DocTypes, e as regras de negócio (ciclo na hierarquia, responsável válido,
desvínculo com gente dentro) ficam nos controllers, não aqui.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

from .consultas import listar_funcoes, listar_unidades
from .permissoes import garantir_gestor_estrutura


@frappe.whitelist(methods=["POST"])
def salvar_unidade(payload: str) -> dict:
	"""Cria ou atualiza uma área, incluindo a lista de funções dela.

	Substitui o registro inteiro: o payload é o formulário todo, e campo ausente
	vira vazio. É o que o dialog da tela envia.
	"""
	garantir_gestor_estrutura()
	dados = _carregar(payload)

	nome = _texto(dados.get("name"))
	area = _texto(dados.get("area"))
	if not area:
		frappe.throw(_("Informe o nome da área."))

	if nome:
		doc = frappe.get_doc("Unidade Organizacional", nome)
		# Área criada pela sincronização de seções é reconciliada pelo nome exato e
		# some do organograma se for desativada — renomear ou desligar pelo portal
		# quebraria a rotina em silêncio.
		if doc.origem_automatica:
			if area != doc.area:
				frappe.throw(_("O nome de uma área criada automaticamente não pode ser alterado."))
			if not _booleano(dados.get("ativa"), padrao=True):
				frappe.throw(_("Uma área criada automaticamente não pode ser desativada por aqui."))
		elif area != doc.area:
			# `name` é o próprio texto da área: renomear cascateia nos vínculos.
			frappe.rename_doc("Unidade Organizacional", doc.name, area, force=True, show_alert=False)
			doc = frappe.get_doc("Unidade Organizacional", area)
	else:
		doc = frappe.new_doc("Unidade Organizacional")
		doc.area = area

	doc.responde_para = _texto(dados.get("responde_para")) or None
	doc.responsavel = _texto(dados.get("responsavel")) or None
	doc.descricao = _texto(dados.get("descricao")) or None
	doc.ordem = _inteiro(dados.get("ordem"))
	if not doc.origem_automatica:
		doc.ativa = 1 if _booleano(dados.get("ativa"), padrao=True) else 0

	doc.funcoes = []
	for item in dados.get("funcoes") or []:
		funcao = _texto(item.get("funcao") if isinstance(item, dict) else item)
		if not funcao:
			continue
		observacao = _texto(item.get("observacao")) if isinstance(item, dict) else ""
		doc.append("funcoes", {"funcao": funcao, "observacao": observacao or None})

	doc.save()
	return {"ok": True, "name": doc.name, "unidades": listar_unidades()}


@frappe.whitelist(methods=["POST"])
def mover_unidade(payload: str) -> dict:
	"""Troca a quem uma área responde. É o arraste da visualização interativa.

	Endpoint próprio e enxuto de propósito: arrastar não deve reenviar o formulário
	inteiro. A checagem de ciclo continua no controller.
	"""
	garantir_gestor_estrutura()
	dados = _carregar(payload)

	nome = _texto(dados.get("name"))
	if not nome or not frappe.db.exists("Unidade Organizacional", nome):
		frappe.throw(_("Área não encontrada."), frappe.DoesNotExistError)

	novo_pai = _texto(dados.get("responde_para")) or None
	if novo_pai and not frappe.db.exists("Unidade Organizacional", novo_pai):
		frappe.throw(_("Área de destino não encontrada."), frappe.DoesNotExistError)

	doc = frappe.get_doc("Unidade Organizacional", nome)
	doc.responde_para = novo_pai
	doc.save()
	return {"ok": True, "unidades": listar_unidades()}


@frappe.whitelist(methods=["POST"])
def salvar_funcao(payload: str) -> dict:
	"""Cria ou atualiza uma função, com linha, status e responsabilidades.

	Como `salvar_unidade`, substitui o registro inteiro a partir do formulário.
	"""
	garantir_gestor_estrutura()
	dados = _carregar(payload)

	nome = _texto(dados.get("name"))
	titulo = _texto(dados.get("titulo"))
	if not titulo:
		frappe.throw(_("Informe o título da função."))

	if nome:
		doc = frappe.get_doc("Funcao Voluntario", nome)
		if titulo != doc.titulo:
			# A sincronização de seções reconhece a função pelo título exato.
			if doc.origem_automatica:
				frappe.throw(_("O título de uma função criada automaticamente não pode ser alterado."))
			frappe.rename_doc("Funcao Voluntario", doc.name, titulo, force=True, show_alert=False)
			doc = frappe.get_doc("Funcao Voluntario", titulo)
	else:
		doc = frappe.new_doc("Funcao Voluntario")
		doc.titulo = titulo

	doc.categoria = _texto(dados.get("categoria")) or None
	doc.descricao = _texto(dados.get("descricao")) or None
	doc.ativa = 1 if _booleano(dados.get("ativa"), padrao=True) else 0

	doc.responsabilidades = []
	for item in dados.get("responsabilidades") or []:
		if not isinstance(item, dict):
			continue
		responsabilidade = _texto(item.get("responsabilidade"))
		if not responsabilidade:
			continue
		doc.append(
			"responsabilidades",
			{"responsabilidade": responsabilidade, "detalhe": _texto(item.get("detalhe")) or None},
		)

	doc.save()
	return {"ok": True, "name": doc.name, "funcoes": listar_funcoes()}


# ---------------------------------------------------------------------------
# Apoio
# ---------------------------------------------------------------------------


def _carregar(payload: str) -> dict:
	try:
		dados = json.loads(payload or "{}")
	except ValueError:
		frappe.throw(_("Não foi possível ler os dados enviados."))
	if not isinstance(dados, dict):
		frappe.throw(_("Não foi possível ler os dados enviados."))
	return dados


def _texto(valor) -> str:
	return valor.strip() if isinstance(valor, str) else ""


def _inteiro(valor) -> int:
	try:
		return int(valor or 0)
	except (TypeError, ValueError):
		return 0


def _booleano(valor, padrao: bool = False) -> bool:
	if valor is None:
		return padrao
	if isinstance(valor, str):
		return valor.strip().lower() in {"1", "true", "sim", "on"}
	return bool(valor)
