from __future__ import annotations

import frappe

# Ponto de partida levantado com o grupo. Semeado por patch, e não por fixture,
# porque a lista é editada pela gestão: o import de fixtures sobrescreveria as
# edições a cada migrate.
TIPOS = (
	("Infraestrutura e sede", "Construção, reforma e manutenção da sede e dos espaços do grupo."),
	(
		"Equipamentos e materiais de campo",
		"Barracas, cozinha de campo, ferramentas e materiais de atividade.",
	),
	("Formação de adultos", "Cursos e capacitação de escotistas e dirigentes."),
	(
		"Programa educativo e atividades",
		"Atividades com os jovens: acampamentos, excursões e projetos das seções.",
	),
	(
		"Inclusão e acessibilidade",
		"Bolsas, acessibilidade e participação de jovens em situação de vulnerabilidade.",
	),
	("Meio ambiente e sustentabilidade", "Ações ambientais, horta, reciclagem e educação ambiental."),
	("Eventos e acampamentos", "Grandes eventos, jamborees e acampamentos regionais ou nacionais."),
	("Tecnologia e comunicação", "Equipamentos, sistemas e divulgação do grupo."),
)


def execute():
	if not frappe.db.table_exists("Tipo de Projeto de Captacao"):
		return

	for tipo, descricao in TIPOS:
		if frappe.db.exists("Tipo de Projeto de Captacao", tipo):
			continue
		frappe.get_doc(
			{"doctype": "Tipo de Projeto de Captacao", "tipo": tipo, "descricao": descricao, "ativo": 1}
		).insert(ignore_permissions=True)
