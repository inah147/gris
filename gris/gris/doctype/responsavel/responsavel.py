# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import hashlib
import re

from frappe.model.document import Document

from gris.utils.funcoes_internas import (
	validar_funcao_do_conselho,
	validar_funcoes_internas,
	validar_vinculo_funcao_area,
)


class Responsavel(Document):
	def autoname(self):
		if self.cpf:
			cpf_clean = re.sub(r"\D", "", self.cpf)
			self.name = hashlib.md5(cpf_clean.encode("utf-8")).hexdigest()  # nosec B324

	def validate(self):
		# Mesmas regras da grade do `Associado`: o responsável também recebe função no
		# organograma. Ver `gris.utils.funcoes_internas`.
		validar_funcoes_internas(self)
		validar_funcao_do_conselho(self)
		validar_vinculo_funcao_area(self)
