# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import hashlib
import re

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today


class NovoAssociado(Document):
	def autoname(self):
		if self.cpf:
			cpf_clean = re.sub(r"\D", "", self.cpf)
			self.name = hashlib.md5(cpf_clean.encode("utf-8")).hexdigest()

	def before_insert(self):
		ramo = _ramo_por_data_de_nascimento(self.data_de_nascimento)
		if ramo:
			self.ramo = ramo

	def validate(self):
		self._sincronizar_data_registro_provisorio()

	def _sincronizar_data_registro_provisorio(self):
		"""Mantém a data de ativação do registro provisório em sincronia com o flag.

		A data alimenta o aviso automático de seguimento (ver
		``gris.api.registro_provisorio_notificacoes``). Ao desmarcar o flag, a data e o
		controle de aviso são limpos para que um novo ciclo recomece do zero.
		"""
		if self.registro_provisorio_efetivado:
			if not self.data_registro_provisorio_efetivado:
				self.data_registro_provisorio_efetivado = today()
		else:
			self.data_registro_provisorio_efetivado = None
			self.data_aviso_seguimento_provisorio = None

	def on_trash(self):
		"""Limpa referências em Responsavel Vinculo ao excluir Novo Associado."""
		vinculos = frappe.get_all(
			"Responsavel Vinculo",
			filters={"beneficiario_novo_associado": self.name},
			pluck="name",
		)
		for vinculo_name in vinculos:
			frappe.db.set_value(
				"Responsavel Vinculo", vinculo_name, "beneficiario_novo_associado", None
			)


def _ramo_por_data_de_nascimento(data_de_nascimento):
	"""Retorna o ramo correspondente à idade decimal calculada da data de nascimento.

	Usa as idades de transição definidas no Single ``Vagas`` como limite superior
	de cada ramo: se a idade for maior que a idade de transição, o jovem é
	promovido ao próximo ramo. O último ramo (Pioneiro) acolhe qualquer idade acima.
	"""
	if not data_de_nascimento:
		return None

	vagas = frappe.get_single("Vagas")
	ramos = [
		("Filhotes", float(vagas.idade_transicao_filhotes or 0)),
		("Lobinho", float(vagas.idade_transicao_lobinho or 0)),
		("Escoteiro", float(vagas.idade_transicao_escoteiro or 0)),
		("Sênior", float(vagas.idade_transicao_senior or 0)),
		("Pioneiro", float(vagas.idade_transicao_pioneiro or 0)),
	]

	nascimento = getdate(data_de_nascimento)
	hoje = getdate(today())
	anos = hoje.year - nascimento.year
	meses = hoje.month - nascimento.month
	if hoje.day < nascimento.day:
		meses -= 1
	if meses < 0:
		anos -= 1
		meses += 12
	idade_decimal = anos + meses / 12

	for nome, idade_transicao in ramos[:-1]:
		if idade_decimal <= idade_transicao:
			return nome
	return ramos[-1][0]
