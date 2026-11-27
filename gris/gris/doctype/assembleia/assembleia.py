# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, formatdate, get_time, getdate, now_datetime

from gris.api.assembleias import constantes as c
from gris.api.assembleias.padroes import segunda_convocacao

DOCTYPES_DE_INSCRICAO = (c.DOCTYPE_CANDIDATURA, c.DOCTYPE_CHAPA, c.DOCTYPE_ASSUNTO)

# O que o edital publicado congela (CA-06.7). Concluído e orientação dos itens da pauta
# continuam livres: são usados durante a própria assembleia.
CAMPOS_TRAVADOS_PELO_EDITAL = (
	"data",
	"tipo",
	"hora_primeira_convocacao",
	"hora_segunda_convocacao",
	"edital_texto_topo",
	"edital_texto_rodape",
	"data_publicacao_edital",
	"edital_incluir_links",
)
CAMPOS_TRAVADOS_DA_PAUTA = ("titulo", "tem_votacao", "finalidade")


class Assembleia(Document):
	def validate(self):
		self.titulo = f"Assembleia {self.tipo} — {formatdate(self.data, 'dd/MM/yyyy')}" if self.data else ""
		if self.hora_primeira_convocacao and not self.hora_segunda_convocacao:
			self.hora_segunda_convocacao = segunda_convocacao(self.hora_primeira_convocacao)
		self._validar_dia_livre()
		self._validar_edital_publicado()
		self._sincronizar_checklist()

	@property
	def eletiva(self) -> bool:
		return any(item.finalidade == c.FINALIDADE_DIRETORIA for item in self.pauta)

	def _validar_dia_livre(self):
		# O índice único em `data` daria um DuplicateEntryError sem explicação.
		outra = frappe.db.exists(c.DOCTYPE_ASSEMBLEIA, {"data": self.data, "name": ["!=", self.name]})
		if outra:
			frappe.throw(_("Já existe uma assembleia em {0}.").format(formatdate(self.data, "dd/MM/yyyy")))

	def _validar_edital_publicado(self):
		antes = self.get_doc_before_save()
		if not antes or not cint(antes.edital_publicado):
			return
		if not cint(self.edital_publicado):
			frappe.throw(_("Um edital publicado não volta a ser rascunho."))
		alterados = [
			campo
			for campo in CAMPOS_TRAVADOS_PELO_EDITAL
			if _normalizado(campo, self.get(campo)) != _normalizado(campo, antes.get(campo))
		]
		if alterados or _pauta_congelada(antes.pauta) != _pauta_congelada(self.pauta):
			frappe.throw(
				_("O edital já foi publicado: data, horários, tipo, textos e pauta não podem mais mudar.")
			)

	def _sincronizar_checklist(self):
		"""O item "Divulgar o edital" acompanha a publicação e não é marcado à mão (CA-05.7)."""
		for etapa in self.checklist:
			if etapa.chave != c.CHECKLIST_DIVULGAR_EDITAL:
				continue
			publicado = cint(self.edital_publicado)
			if publicado and not cint(etapa.concluido):
				etapa.concluido = 1
				etapa.concluido_em = self.edital_publicado_em or now_datetime()
				etapa.concluido_por = frappe.session.user
			elif not publicado:
				etapa.concluido = 0
				etapa.concluido_em = None
				etapa.concluido_por = None

	def on_trash(self):
		if self.edital_publicado and "System Manager" not in frappe.get_roles():
			frappe.throw(
				_("O edital já foi publicado. Para excluir, fale com o administrador do sistema."),
				frappe.PermissionError,
			)
		apagar_inscricoes(self.name)


def _normalizado(campo: str, valor) -> str:
	"""Data e hora chegam do banco e do portal em formatos diferentes (9:00:00 x 09:00)."""
	if not valor:
		return ""
	if campo.startswith("hora_"):
		return get_time(valor).strftime("%H:%M")
	if campo in ("data", "data_publicacao_edital"):
		return str(getdate(valor))
	return str(valor).strip()


def _pauta_congelada(itens) -> list[tuple]:
	return [tuple(str(item.get(campo) or "") for campo in CAMPOS_TRAVADOS_DA_PAUTA) for item in itens]


def apagar_inscricoes(assembleia: str) -> None:
	"""Candidaturas, chapas e assuntos gerais da assembleia (CA-02.7).

	`ignore_permissions`: os DocTypes de inscrição só são gravados pelos formulários, e
	quem gerencia a assembleia não tem `delete` neles. Quem chegou aqui já passou pela
	permissão de excluir a assembleia.
	"""
	for doctype in DOCTYPES_DE_INSCRICAO:
		for name in frappe.get_all(doctype, filters={"assembleia": assembleia}, pluck="name"):
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
