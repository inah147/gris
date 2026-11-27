# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from gris.api.assembleias.constantes import DOCTYPE_CONFIGURACOES, PRAZO_SEM_LIMITE
from gris.api.assembleias.textos import validar_texto
from gris.api.google_workspace.festa_drive import extract_drive_folder_id
from gris.festas.doctype.configuracoes_de_festas.configuracoes_de_festas import (
	_get_active_party_drive_map as drives_ativos,
)

PRAZOS = ("mesa", "diretoria", "comissao_fiscal", "delegado", "assuntos_gerais")
TEXTOS = ("texto_topo_edital", "texto_rodape_edital", "modelo_ata")


class ConfiguracoesdeAssembleias(Document):
	def validate(self):
		self._normalizar()
		self._validar_numeros()
		self._validar_prazos()
		self._validar_textos()
		self._validar_drive()

	def _normalizar(self):
		self.drive_compartilhado_assembleias = (self.drive_compartilhado_assembleias or "").strip()
		pasta = (self.pasta_assembleias_id or "").strip()
		# Aceita o link colado do navegador; guarda só o ID.
		self.pasta_assembleias_id = extract_drive_folder_id(pasta) or pasta

	def _validar_numeros(self):
		if cint(self.dias_limite_edital) <= 0:
			frappe.throw(_("A antecedência mínima do edital precisa ser de pelo menos 1 dia."))
		if cint(self.voto_jovens) and cint(self.idade_minima_voto_jovem) <= 0:
			frappe.throw(_("Informe a partir de que idade os jovens votam."))
		if (
			cint(self.voto_jovens)
			and cint(self.voto_representado_por_responsavel)
			and cint(self.idade_minima_representacao_meses) >= cint(self.idade_minima_voto_jovem) * 12
		):
			frappe.throw(
				_(
					"A idade de representação pelo responsável precisa ser menor que a idade em que o jovem vota."
				)
			)
		for campo in (
			"vagas_comissao_fiscal",
			"suplentes_comissao_fiscal",
			"associados_por_delegado",
		):
			if cint(self.get(campo)) < 0:
				frappe.throw(_("“{0}” não pode ser negativo.").format(_(self.meta.get_label(campo))))
		if cint(self.associados_por_delegado) == 0:
			frappe.throw(_("Informe quantos associados dão direito a uma vaga de delegado."))

	def _validar_prazos(self):
		for chave in PRAZOS:
			unidade = self.get(f"prazo_{chave}_unidade") or PRAZO_SEM_LIMITE
			if unidade != PRAZO_SEM_LIMITE and cint(self.get(f"prazo_{chave}_valor")) <= 0:
				frappe.throw(
					_("O prazo “{0}” em {1} precisa ser maior que zero.").format(
						_(self.meta.get_label(f"prazo_{chave}_unidade")), unidade.lower()
					)
				)

	def _validar_textos(self):
		for campo in TEXTOS:
			validar_texto(self.get(campo), _(self.meta.get_label(campo)))
		for tabela, rotulo in (
			("pauta_ordinaria", "Pauta ordinária"),
			("pauta_extraordinaria", "Pauta extraordinária"),
		):
			for item in self.get(tabela) or []:
				validar_texto(item.titulo, _("{0}, item {1}").format(rotulo, item.idx))

	def _validar_drive(self):
		if (
			self.drive_compartilhado_assembleias
			and self.drive_compartilhado_assembleias not in drives_ativos()
		):
			frappe.throw(
				_("Drive compartilhado inválido. Selecione um drive ativo em Configurações Google Workspace.")
			)
		if not cint(self.habilitar_pastas_drive):
			return
		if not self.drive_compartilhado_assembleias:
			frappe.throw(_("Selecione o drive compartilhado das assembleias."))
		if not self.pasta_assembleias_id:
			frappe.throw(_("Informe a pasta raiz das assembleias."))


@frappe.whitelist()
def opcoes_de_drive() -> list[dict[str, str]]:
	"""Drives ativos para o Select do Desk."""
	if not frappe.has_permission(DOCTYPE_CONFIGURACOES, "write"):
		frappe.throw(_("Sem permissão para editar as configurações de assembleias."), frappe.PermissionError)
	return [{"label": nome, "value": drive_id} for drive_id, nome in drives_ativos().items()]


@frappe.whitelist()
def grupos_para_select() -> dict:
	"""Grupos do WhatsApp para o Select do grupo da Diretoria, com o erro devolvido como dado.

	Com a integração desligada ou fora do ar, a listagem levanta exceção, e o Desk abriria
	o modal "Erro de Servidor" a cada visita à tela.
	"""
	from gris.utils.whatsapp import listar_grupos_whatsapp_para_select
	from gris.utils.whatsapp_errors import WhatsAppConfigurationError, WhatsAppRequestError

	try:
		return {"grupos": listar_grupos_whatsapp_para_select(doctype=DOCTYPE_CONFIGURACOES), "erro": None}
	except (WhatsAppConfigurationError, WhatsAppRequestError) as erro:
		return {"grupos": None, "erro": str(erro)}
