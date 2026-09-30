"""Quem pode o quê na Captação de Recursos.

Nada aqui vem de papel no DocType: a Diretoria e a Relações Institucionais saem da
lotação (`gris.utils.diretoria`), e o proponente é quem enviou a ideia. Por isso os
endpoints gravam o `Projeto de Captacao` com `ignore_permissions=True` **depois** de
passar por estas funções — o DocType só dá permissão ao `System Manager`, para que
ninguém contorne o fluxo pela API REST genérica.

O `Perfil` é calculado uma vez por requisição: a lotação custa algumas consultas e
cada endpoint pergunta várias coisas sobre o mesmo usuário.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import frappe
from frappe import _
from frappe.utils import cint

from gris.utils import diretoria

ROLE_ADMIN = "System Manager"


@dataclass(frozen=True)
class Perfil:
	user: str
	admin: bool = False
	diretoria: bool = False
	presidente: bool = False
	relacoes_institucionais: bool = False
	somente_presidente_aprova: bool = False
	pessoas: tuple[str, ...] = field(default_factory=tuple)

	@property
	def decide_pela_diretoria(self) -> bool:
		"""Aprova a ideia e dá a aprovação final. Basta um membro — ou só o presidente."""
		if self.admin:
			return True
		if self.somente_presidente_aprova:
			return self.presidente
		return self.diretoria

	@property
	def revisa(self) -> bool:
		return self.admin or self.relacoes_institucionais

	@property
	def ve_o_banco(self) -> bool:
		"""Vê todos os projetos, e não só os que propôs."""
		return self.admin or self.diretoria or self.relacoes_institucionais

	@property
	def move_cards(self) -> bool:
		return self.admin or self.diretoria or self.relacoes_institucionais


def perfil_do_usuario(user: str | None = None) -> Perfil:
	user = user or frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Entre no portal para acessar a Captação de Recursos."), frappe.PermissionError)

	papeis = diretoria.papeis_na_diretoria(user)
	return Perfil(
		user=user,
		admin=ROLE_ADMIN in frappe.get_roles(user),
		diretoria=papeis["membro"],
		presidente=papeis["presidente"],
		relacoes_institucionais=papeis["relacoes_institucionais"],
		somente_presidente_aprova=bool(
			cint(frappe.db.get_single_value(diretoria.DOCTYPE_CONFIGURACOES, "somente_presidente_aprova"))
		),
		pessoas=tuple(papeis["pessoas"]),
	)


def eh_proponente(perfil: Perfil, doc) -> bool:
	return bool(doc.proponente_user) and doc.proponente_user.lower() == perfil.user.lower()


def pode_ver(perfil: Perfil, doc) -> bool:
	return perfil.ve_o_banco or eh_proponente(perfil, doc)


def garantir_que_ve(perfil: Perfil, doc) -> None:
	if not pode_ver(perfil, doc):
		frappe.throw(_("Você não tem acesso a este projeto."), frappe.PermissionError)


def garantir_proponente(perfil: Perfil, doc) -> None:
	if not (perfil.admin or eh_proponente(perfil, doc)):
		frappe.throw(_("Só quem propôs o projeto pode fazer isso."), frappe.PermissionError)


def garantir_diretoria(perfil: Perfil) -> None:
	if perfil.decide_pela_diretoria:
		return
	if perfil.somente_presidente_aprova:
		frappe.throw(
			_("Só o Diretor(a) Presidente pode decidir sobre projetos de captação."), frappe.PermissionError
		)
	frappe.throw(
		_("Só membros da Diretoria podem decidir sobre projetos de captação."), frappe.PermissionError
	)


def garantir_revisor(perfil: Perfil) -> None:
	if not perfil.revisa:
		frappe.throw(
			_("A revisão técnica é feita pela equipe de Relações Institucionais."), frappe.PermissionError
		)


def garantir_quem_move(perfil: Perfil) -> None:
	if not perfil.move_cards:
		frappe.throw(
			_("Só a Diretoria e a equipe de Relações Institucionais movem projetos no banco."),
			frappe.PermissionError,
		)


def garantir_quem_cancela(perfil: Perfil, doc) -> None:
	"""A Diretoria e a RI encerram qualquer projeto; o proponente pode retirar o próprio."""
	if perfil.move_cards or eh_proponente(perfil, doc):
		return
	frappe.throw(_("Você não pode cancelar este projeto."), frappe.PermissionError)
