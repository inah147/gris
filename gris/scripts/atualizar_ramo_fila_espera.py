# File moved to /api/update_waiting_list_branch.py (English name)
# The branch update script for the waiting list is now in gris/api/update_waiting_list_branch.py
from datetime import datetime

import frappe
from frappe.utils import getdate, today


def atualizar_ramo_fila_espera():
	# Carrega configurações de ramos e idades de transição
	vagas_settings = frappe.get_single("Vagas")
	# Ordem dos ramos
	ramos = [
		("Filhotes", float(vagas_settings.idade_transicao_filhotes)),
		("Lobinho", float(vagas_settings.idade_transicao_lobinho)),
		("Escoteiro", float(vagas_settings.idade_transicao_escoteiro)),
		("Sênior", float(vagas_settings.idade_transicao_senior)),
		("Pioneiro", float(vagas_settings.idade_transicao_pioneiro)),
	]

	# Busca todos na fila de espera
	fila = frappe.get_all(
		"Fila de Espera",
		fields=["name", "associado", "ramo"],
	)

	for item in fila:
		if not item.associado:
			continue
		# Busca data de nascimento
		assoc = frappe.get_value("Novo Associado", item.associado, ["data_de_nascimento", "ramo"])
		if not assoc or not assoc[0]:
			continue
		birth = getdate(assoc[0])
		today_dt = getdate(today())
		# Calcula idade em anos.meses
		anos = today_dt.year - birth.year
		meses = today_dt.month - birth.month
		if today_dt.day < birth.day:
			meses -= 1
		if meses < 0:
			anos -= 1
			meses += 12
		idade_decimal = anos + meses / 12
		# Descobre ramo correto
		for idx, (ramo_nome, idade_transicao) in enumerate(ramos):
			if idx == len(ramos) - 1 or idade_decimal < ramos[idx + 1][1]:
				if item.ramo != ramo_nome:
					# Atualiza Fila de Espera
					frappe.db.set_value("Fila de Espera", item.name, "ramo", ramo_nome)
					# Atualiza Novo Associado
					frappe.db.set_value("Novo Associado", item.associado, "ramo", ramo_nome)
					frappe.db.commit()
				break
