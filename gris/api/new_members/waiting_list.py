import frappe
from frappe.utils import getdate, today

from gris.utils.job_logger import definir_resumo, metrica, obter_logger


def update_waiting_list_branch():
	"""
	Update the branch of each associate in the Waiting List according to the transition age.
	If the branch is changed, also update in Novo Associado.
	"""
	vagas_settings = frappe.get_single("Vagas")
	branches = [
		("Filhotes", float(vagas_settings.idade_transicao_filhotes)),
		("Lobinho", float(vagas_settings.idade_transicao_lobinho)),
		("Escoteiro", float(vagas_settings.idade_transicao_escoteiro)),
		("Sênior", float(vagas_settings.idade_transicao_senior)),
		("Pioneiro", float(vagas_settings.idade_transicao_pioneiro)),
	]

	logger = obter_logger("fila_de_espera")
	waiting_list = frappe.get_all(
		"Fila de Espera",
		fields=["name", "associado", "ramo"],
	)
	logger.info(f"Avaliando o ramo de {len(waiting_list)} inscrito(s) na fila de espera.")

	promovidos = 0
	sem_dados = 0
	for item in waiting_list:
		if not item.associado:
			sem_dados += 1
			continue
		assoc = frappe.get_value("Novo Associado", item.associado, ["data_de_nascimento", "ramo"])
		if not assoc or not assoc[0]:
			logger.warning(f"Inscrito {item.name} sem data de nascimento — ramo nao recalculado.")
			sem_dados += 1
			continue
		birth = getdate(assoc[0])
		today_dt = getdate(today())
		years = today_dt.year - birth.year
		months = today_dt.month - birth.month
		if today_dt.day < birth.day:
			months -= 1
		if months < 0:
			years -= 1
			months += 12
		decimal_age = years + months / 12
		for idx, (branch_name, _transition_age) in enumerate(branches):
			if idx == len(branches) - 1 or decimal_age < branches[idx + 1][1]:
				if item.ramo != branch_name:
					frappe.db.set_value("Fila de Espera", item.name, "ramo", branch_name)
					frappe.db.set_value("Novo Associado", item.associado, "ramo", branch_name)
					# Commit por item: a promoção de ramo de cada criança é independente.
					# Um erro em um registro adiante não pode desfazer os já promovidos.
					frappe.db.commit()  # nosemgrep
					promovidos += 1
					logger.info(
						f"{item.associado} promovido(a) de {item.ramo or '—'} para {branch_name} "
						f"({decimal_age:.1f} anos)."
					)
				break

	metrica("promovidos", promovidos, incrementar=False)
	metrica("avaliados", len(waiting_list), incrementar=False)
	metrica("sem_dados", sem_dados, incrementar=False)
	definir_resumo(
		f"{promovidos} inscrito(s) mudaram de ramo (de {len(waiting_list)} avaliados; "
		f"{sem_dados} sem dados suficientes)."
	)
