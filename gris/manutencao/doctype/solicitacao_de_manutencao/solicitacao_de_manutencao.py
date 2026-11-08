# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Solicitação de Manutenção — pedido de conserto na sede do grupo.

Qualquer pessoa com login abre pelo portal (`/manutencao/solicitar`) e acompanha
a fila em `/manutencao/acompanhamento`. A equipe com o papel "Gestor de
Manutencao" organiza em `/manutencao/gestao`: prioridade, data prevista, quem
executa e o andamento. Os endpoints ficam em `gris.api.manutencao.portal`.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_fullname, now_datetime

from gris.api.manutencao import constantes as c


class SolicitacaodeManutencao(Document):
	def before_insert(self) -> None:
		if not self.solicitante:
			user = frappe.session.user
			if user and user != "Guest":
				self.solicitante = user

		if self.solicitante and not self.solicitante_nome:
			self.solicitante_nome = get_fullname(self.solicitante) or self.solicitante

		if not self.data_solicitacao:
			self.data_solicitacao = now_datetime()

		# Quem pede relata; quem decide andamento é a gestão. Um status vindo
		# pronto (importação, cadastro pelo Desk) fica de pé.
		if not self.status:
			self.status = c.STATUS_RECEBIDA

		# Sugestão inicial a partir do que a pessoa contou, para a fila já nascer
		# ordenada antes de alguém da gestão olhar.
		if not self.prioridade:
			self.prioridade = c.PRIORIDADE_POR_URGENCIA.get(
				(self.urgencia_informada or "").strip(), c.PRIORIDADE_MEDIA
			)

	def validate(self) -> None:
		self._normalizar_texto()
		self._validar_opcoes()
		self._validar_custo()
		self._marcar_datas_do_fluxo()

	def _normalizar_texto(self) -> None:
		self.titulo = (self.titulo or "").strip()
		self.local = (self.local or "").strip()
		self.descricao = (self.descricao or "").strip()
		self.responsavel_execucao = (self.responsavel_execucao or "").strip()

		limites = (
			("titulo", _("O que precisa ser feito"), c.TITULO_MAX),
			("local", _("Local"), c.LOCAL_MAX),
			("descricao", _("Descrição"), c.DESCRICAO_MAX),
			("responsavel_execucao", _("Quem vai executar"), c.RESPONSAVEL_MAX),
			("observacoes_internas", _("Observações internas"), c.TEXTO_INTERNO_MAX),
			("resumo_execucao", _("O que foi feito"), c.TEXTO_INTERNO_MAX),
		)
		for campo, rotulo, maximo in limites:
			if len(self.get(campo) or "") > maximo:
				frappe.throw(_("O campo '{0}' deve ter no máximo {1} caracteres.").format(rotulo, maximo))

	def _validar_opcoes(self) -> None:
		# O Frappe já recusa opção fora do Select, mas com uma mensagem genérica
		# em inglês; aqui a mensagem diz qual campo e em português.
		regras = (
			("categoria", _("Categoria"), c.CATEGORIAS),
			("urgencia_informada", _("Urgência"), c.URGENCIAS),
			("status", _("Status"), c.STATUS),
			("prioridade", _("Prioridade"), c.PRIORIDADES),
		)
		for campo, rotulo, opcoes in regras:
			valor = (self.get(campo) or "").strip()
			if valor not in opcoes:
				frappe.throw(_("{0} inválido(a): {1}.").format(rotulo, valor or _("vazio")))

	def _validar_custo(self) -> None:
		if self.custo_estimado and flt(self.custo_estimado) < 0:
			frappe.throw(_("O custo estimado não pode ser negativo."))

	def _marcar_datas_do_fluxo(self) -> None:
		"""Carimba início e conclusão a partir da transição de status.

		Ninguém precisa lembrar de preencher data: mover o status basta.
		"""
		status = (self.status or "").strip()

		# Uma vez iniciada, a data de início não se apaga: se a manutenção parar
		# e voltar para a fila, a primeira tentativa continua sendo a que conta.
		if status in c.STATUS_EM_EXECUCAO and not self.data_inicio:
			self.data_inicio = now_datetime()

		if status == c.STATUS_CONCLUIDA:
			if not self.data_conclusao:
				self.data_conclusao = now_datetime()
			# Conserto rápido, concluído sem passar por "Em andamento".
			if not self.data_inicio:
				self.data_inicio = self.data_conclusao
		elif self.data_conclusao:
			# Reaberta: a conclusão deixa de valer.
			self.data_conclusao = None
