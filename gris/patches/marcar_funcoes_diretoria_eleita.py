from __future__ import annotations

import frappe

# As três funções que o estatuto de todo Grupo Escoteiro elege em assembleia. Só
# os títulos exatos: as diretorias nomeadas variam de grupo para grupo e são
# marcadas pela tela de Funções.
FUNCOES_ELEITAS = ("Diretor(a) Presidente", "Diretor(a) Administrativo", "Diretor(a) Financeiro")


def execute():
	if not frappe.db.has_column("Funcao Voluntario", "diretoria"):
		return

	for titulo in FUNCOES_ELEITAS:
		if not frappe.db.exists("Funcao Voluntario", titulo):
			continue
		# Não sobrescreve quem já marcou pela tela.
		if frappe.db.get_value("Funcao Voluntario", titulo, "diretoria"):
			continue
		frappe.db.set_value("Funcao Voluntario", titulo, "diretoria", "Eleita", update_modified=False)
