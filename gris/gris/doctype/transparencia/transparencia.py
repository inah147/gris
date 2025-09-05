# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import frappe
from frappe.website.website_generator import WebsiteGenerator


class Transparencia(WebsiteGenerator):
	def before_save(self):
		# add update timestamp
		self.data_de_atualização = frappe.utils.now_datetime()

		# set title
		is_semestre = self.tipo_arquivo == "Parecer semestral da comissão fiscal"
		semestre_txt = f" - {self.semestre_referencia}° Semestre" if is_semestre else ""
		self.title = f"{self.tipo_arquivo}  - {self.ano_referencia}{semestre_txt}"
