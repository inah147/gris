from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class Projeto(Document):
	def validate(self):
		self._validate_dates()
		self._hydrate_people_data()
		self._validate_sponsor_category()
		self._validate_people_scopes()

	def _validate_dates(self):
		if self.data_de_inicio and self.data_de_termino:
			if getdate(self.data_de_inicio) > getdate(self.data_de_termino):
				frappe.throw(_("Data de inicio nao pode ser maior que data de termino."))

		for tarefa in self.tarefas or []:
			if tarefa.data_inicio and tarefa.prazo and getdate(tarefa.data_inicio) > getdate(tarefa.prazo):
				frappe.throw(
					_("Tarefa '{0}' com data de inicio maior que prazo.").format(
						tarefa.descricao or tarefa.idx
					)
				)
			if tarefa.data_entrega and tarefa.prazo and getdate(tarefa.data_entrega) > getdate(tarefa.prazo):
				tarefa.status = "Atrasado"

		for item in self.cronograma or []:
			if (
				item.data_inicio
				and item.data_termino
				and getdate(item.data_inicio) > getdate(item.data_termino)
			):
				frappe.throw(_("Cronograma com data de inicio maior que data de termino."))

	def _hydrate_people_data(self):
		for row in self.outros_envolvidos or []:
			if not row.associado:
				continue
			payload = _get_associado_payload(row.associado)
			row.email = payload["email"]
			row.telefone = payload["telefone"]

		for row in self.equipe_de_interesse or []:
			tipo = (row.tipo_pessoa or "").strip()
			if tipo == "Associado":
				if not row.associado:
					frappe.throw(_("Selecione um associado para membros da equipe com tipo 'Associado'."))
				payload = _get_associado_payload(row.associado)
				row.nome = payload["nome"]
				row.email = payload["email"]
				row.telefone = payload["telefone"]
			elif tipo == "Responsavel":
				if not row.responsavel:
					frappe.throw(_("Selecione um responsavel para membros da equipe com tipo 'Responsavel'."))
				payload = _get_responsavel_payload(row.responsavel)
				row.nome = payload["nome"]
				row.email = payload["email"]
				row.telefone = payload["telefone"]
			else:
				if not row.nome:
					frappe.throw(_("Informe o nome para membros da equipe com tipo 'Nome livre'."))
				if not row.email or not row.telefone:
					frappe.throw(
						_("Email e telefone sao obrigatorios para membros de equipe com nome livre.")
					)

	def _validate_people_scopes(self):
		team_names = {row.nome for row in (self.equipe_de_interesse or []) if row.nome}

		for tarefa in self.tarefas or []:
			if tarefa.responsavel and tarefa.responsavel not in team_names:
				frappe.throw(
					_("Responsavel '{0}' da tarefa deve existir na equipe de interesse.").format(
						tarefa.responsavel
					)
				)

	def _validate_sponsor_category(self):
		if not self.padrinho_associado:
			return

		categoria = frappe.db.get_value("Associado", self.padrinho_associado, "categoria")
		if categoria and categoria.lower().startswith("benefici"):
			frappe.throw(_("Padrinho associado nao pode ter categoria Beneficiario."))


@frappe.whitelist()
def get_contato_pessoa(doctype_name: str, docname: str) -> dict[str, Any]:
	if doctype_name not in {"Associado", "Responsavel"}:
		frappe.throw(_("Tipo de pessoa invalido."))

	if doctype_name == "Associado":
		return _get_associado_payload(docname)

	return _get_responsavel_payload(docname)


def _get_associado_payload(name: str) -> dict[str, str]:
	data = frappe.db.get_value(
		"Associado",
		name,
		["nome_completo", "id_escoteiros", "email", "telefone"],
		as_dict=True,
	)
	if not data:
		frappe.throw(_("Associado nao encontrado."))

	email = data.get("id_escoteiros") or data.get("email")
	if not email or not data.get("telefone"):
		frappe.throw(_("Associado selecionado nao possui email ou telefone preenchido."))

	return {
		"nome": data.get("nome_completo") or name,
		"email": email,
		"telefone": data.get("telefone"),
	}


def _get_responsavel_payload(name: str) -> dict[str, str]:
	data = frappe.db.get_value(
		"Responsavel",
		name,
		["nome_completo", "email", "celular", "telefone_secundario"],
		as_dict=True,
	)
	if not data:
		frappe.throw(_("Responsavel nao encontrado."))

	telefone = data.get("celular") or data.get("telefone_secundario")
	if not data.get("email") or not telefone:
		frappe.throw(_("Responsavel selecionado nao possui email ou telefone preenchido."))

	return {
		"nome": data.get("nome_completo") or name,
		"email": data.get("email"),
		"telefone": telefone,
	}
