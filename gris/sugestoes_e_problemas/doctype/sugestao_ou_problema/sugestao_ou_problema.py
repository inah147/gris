# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Sugestao ou Problema — canal interno de feedback do GRIS.

Guarda o relato de quem usa o sistema (bug ou pedido de funcionalidade) e serve
de fonte para o kanban em `/sugestoes/acompanhamento`. Quando um responsavel e
alocado, `gris.gestao_de_tarefas.board_sync_sugestoes` cria a tarefa espelho no
quadro "Desenvolvimento do GRIS" para o item aparecer em "Minhas tarefas".
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_fullname, now_datetime, strip_html

from gris.api.sugestoes.constantes import (
	COLUNA_CONCLUIDO,
	COLUNA_EM_DESENVOLVIMENTO,
	COLUNAS,
	COLUNAS_DE_TRIAGEM,
	DESCRICAO_MAX,
	MODULOS,
	ROLE_DESENVOLVEDOR,
	TIPOS,
	TITULO_MAX,
	coluna_inicial,
	modulos_para_tipo,
)


class SugestaoouProblema(Document):
	def before_insert(self) -> None:
		if not self.solicitante:
			user = frappe.session.user
			if user and user != "Guest":
				self.solicitante = user

		if self.solicitante and not self.solicitante_nome:
			self.solicitante_nome = get_fullname(self.solicitante) or self.solicitante

		if not self.data_submissao:
			self.data_submissao = now_datetime()

		# O Select preenche a primeira opcao sozinho quando o `options` nao comeca
		# com quebra de linha. Toda submissao nova entra na coluna de triagem do
		# seu tipo, entao o valor herdado so vale se ja for o correto.
		if not self.status or self.status in COLUNAS_DE_TRIAGEM:
			self.status = coluna_inicial(self.tipo)

	def validate(self) -> None:
		self._normalizar_texto()
		self._validar_tipo_e_modulo()
		self._validar_status()
		self._validar_responsavel()
		self._marcar_datas_do_fluxo()

	def _marcar_datas_do_fluxo(self) -> None:
		"""Carimba as datas que alimentam a linha do tempo do dialog.

		Sao derivadas da transicao de coluna, e nao editaveis: quem move o card
		nao deveria ter de lembrar de preencher data nenhuma.
		"""
		status = (self.status or "").strip()

		# Uma vez iniciado, o inicio nao se apaga: se o item voltar para triagem
		# e avancar de novo, a data que interessa continua sendo a primeira.
		if status == COLUNA_EM_DESENVOLVIMENTO and not self.data_inicio_desenvolvimento:
			self.data_inicio_desenvolvimento = now_datetime()

		if status == COLUNA_CONCLUIDO:
			if not self.data_conclusao:
				self.data_conclusao = now_datetime()
			# Concluir sem ter passado por "Em desenvolvimento" (item pequeno,
			# resolvido direto) deixaria a linha do tempo com um buraco no meio.
			if not self.data_inicio_desenvolvimento:
				self.data_inicio_desenvolvimento = self.data_conclusao
		elif self.data_conclusao:
			# Reaberto: a conclusao deixa de valer.
			self.data_conclusao = None

	def _normalizar_texto(self) -> None:
		self.titulo = (self.titulo or "").strip()
		self.descricao = (self.descricao or "").strip()

		if len(self.titulo) > TITULO_MAX:
			frappe.throw(_("O título deve ter no máximo {0} caracteres.").format(TITULO_MAX))

		# `descricao` e HTML do editor WYSIWYG: o limite vale para o texto que a
		# pessoa realmente escreveu, nao para as tags que o editor gera.
		if len(strip_html(self.descricao)) > DESCRICAO_MAX:
			frappe.throw(_("A descrição deve ter no máximo {0} caracteres.").format(DESCRICAO_MAX))

	def _validar_tipo_e_modulo(self) -> None:
		tipo = (self.tipo or "").strip()
		modulo = (self.modulo or "").strip()

		if tipo not in TIPOS:
			frappe.throw(_("Tipo inválido: {0}.").format(tipo or "vazio"))
		if modulo not in MODULOS:
			frappe.throw(_("Módulo inválido: {0}.").format(modulo or "vazio"))

		# "Novo módulo" so faz sentido pedindo funcionalidade: nao da para relatar
		# um problema em algo que ainda nao existe.
		if modulo not in modulos_para_tipo(tipo):
			frappe.throw(_("O módulo '{0}' não pode ser usado com o tipo '{1}'.").format(modulo, tipo))

	def _validar_status(self) -> None:
		status = (self.status or "").strip()
		if status not in COLUNAS:
			frappe.throw(_("Status inválido: {0}.").format(status or "vazio"))

		# Colunas de triagem sao definidas pelo tipo; deixar as duas abertas para
		# qualquer tipo permitiria um bug parar em "Solicitações de funcionalidades".
		if status in COLUNAS_DE_TRIAGEM and status != coluna_inicial(self.tipo):
			frappe.throw(_("Um item do tipo '{0}' não pode ficar na coluna '{1}'.").format(self.tipo, status))

	def _validar_responsavel(self) -> None:
		responsavel = (self.responsavel or "").strip()
		if not responsavel:
			return

		if ROLE_DESENVOLVEDOR not in frappe.get_roles(responsavel):
			frappe.throw(
				_("{0} não tem o papel '{1}' e não pode ser responsável por uma solicitação.").format(
					get_fullname(responsavel) or responsavel, ROLE_DESENVOLVEDOR
				)
			)
