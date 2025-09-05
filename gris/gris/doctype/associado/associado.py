# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

# import frappe
import datetime
import hashlib
import re

import frappe
from frappe.model.document import Document


class Associado(Document):
	def _fix_phones(self):
		if self.telefone:
			num = re.sub(r"\D", "", self.telefone)
			self.telefone = f"+55{num}" if not num.startswith("55") else f"+{num}"
		if self.telefone_responsavel_1:
			num = re.sub(r"\D", "", self.telefone_responsavel_1)
			self.telefone_responsavel_1 = f"+55{num}" if not num.startswith("55") else f"+{num}"
		if self.telefone_responsavel_2:
			num = re.sub(r"\D", "", self.telefone_responsavel_2)
			self.telefone_responsavel_2 = f"+55{num}" if not num.startswith("55") else f"+{num}"

	def _fix_names(self):
		if self.nome_completo:
			self.nome_completo = self.nome_completo.title()
		if self.nome_responsavel_1:
			self.nome_responsavel_1 = self.nome_responsavel_1.title()
		if self.nome_responsavel_2:
			self.nome_responsavel_2 = self.nome_responsavel_2.title()

	def validate(self):
		desligado = False
		for record in self.historico_no_grupo:
			if record.data_de_desligamento:
				desligado = True
				break

		if desligado:
			self.status_no_grupo = "Inativo"
			self.status = "Desconhecido"
		else:
			self.status_no_grupo = "Ativo"

			expiration = datetime.datetime.strptime(str(self.validade_registro)[:10], "%Y-%m-%d").date()
			self.status = "Válido" if expiration > datetime.date.today() else "Vencido"

	def autoname(self):
		# select a project name based on customer
		if self.registro:
			self.name = self.registro
		else:
			self.name = frappe.generate_hash(length=10)

	def before_insert(self):
		# data anonymization
		if self.cpf:
			self.cpf = hashlib.md5(self.cpf.encode("utf-8")).hexdigest()

		if self.cpf_responsavel_1:
			self.cpf_responsavel_1 = hashlib.md5(self.cpf_responsavel_1.encode("utf-8")).hexdigest()

		if self.cpf_responsavel_2:
			self.cpf_responsavel_2 = hashlib.md5(self.cpf_responsavel_2.encode("utf-8")).hexdigest()

		# fix phones
		self._fix_phones()

		# fix names
		self._fix_names()

	def before_save(self):
		if self.pais_divorciados == "Não":
			self.tipo_guarda = "-"

		# fix phones
		self._fix_phones()

		# fix names
		self._fix_names()
