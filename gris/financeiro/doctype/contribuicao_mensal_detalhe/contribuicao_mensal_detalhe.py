# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import getdate


class ContribuicaoMensalDetalhe(Document):
	def validate(self):
		# Normaliza para o primeiro dia do mês: a apuração agrupa por mês, não por dia.
		if self.mes_referencia:
			data = getdate(self.mes_referencia)
			self.mes_referencia = data.replace(day=1)
