import frappe
from frappe.utils import getdate, today

def update_waiting_list_branch():
	"""
	Update the branch of each associate in the Waiting List according to the transition age.
	If the branch is changed, also update in Novo Associado.
	"""
	vagas_settings = frappe.get_single("Vagas")
	ramos = [
		("Filhotes", float(vagas_settings.idade_transicao_filhotes)),
		("Lobinho", float(vagas_settings.idade_transicao_lobinho)),
		("Escoteiro", float(vagas_settings.idade_transicao_escoteiro)),
		("Sênior", float(vagas_settings.idade_transicao_senior)),
		("Pioneiro", float(vagas_settings.idade_transicao_pioneiro)),
	]

	waiting_list = frappe.get_all(
		"Fila de Espera",
		fields=["name", "associado", "ramo"],
	)

	for item in waiting_list:
		if not item.associado:
			continue
		assoc = frappe.get_value("Novo Associado", item.associado, ["data_de_nascimento", "ramo"])
		if not assoc or not assoc[0]:
			continue
		birth = getdate(assoc[0])
		today_dt = getdate(today())
		anos = today_dt.year - birth.year
		meses = today_dt.month - birth.month
		if today_dt.day < birth.day:
			meses -= 1
		if meses < 0:
			anos -= 1
			meses += 12
		idade_decimal = anos + meses/12
		for idx, (branch_name, transition_age) in enumerate(ramos):
			if idx == len(ramos)-1 or idade_decimal < ramos[idx+1][1]:
				if item.ramo != branch_name:
					frappe.db.set_value("Fila de Espera", item.name, "ramo", branch_name)
					frappe.db.set_value("Novo Associado", item.associado, "ramo", branch_name)
					frappe.db.commit()
				break
