from __future__ import annotations

import frappe


def execute():
	"""Dá nome e área de verdade às Funcao Voluntario legadas.

	O DocType nascia sem `titulo` e sem autoname (nome = hash) e com `area` como
	Select sem options. Agora `titulo` é o nome do documento e `area` é Link para
	Unidade Organizacional. Este patch preenche o título a partir do que existia e
	descarta áreas que não correspondem a nenhuma unidade cadastrada.
	"""
	if not frappe.db.table_exists("Funcao Voluntario"):
		return

	linhas = frappe.db.get_all(
		"Funcao Voluntario",
		fields=["name", "titulo", "categoria", "area"],
	)
	if not linhas:
		return

	unidades = {u.name for u in frappe.db.get_all("Unidade Organizacional", fields=["name"])}
	titulos_usados = {(linha.titulo or "").strip() for linha in linhas if (linha.titulo or "").strip()}

	for linha in linhas:
		area = (linha.area or "").strip()
		area_valida = area if area in unidades else None

		titulo = (linha.titulo or "").strip() or _montar_titulo(linha.categoria, area, titulos_usados)
		titulos_usados.add(titulo)

		frappe.db.set_value(
			"Funcao Voluntario",
			linha.name,
			{"titulo": titulo, "area": area_valida},
			update_modified=False,
		)

		# O nome antigo é um hash ilegível; com autoname `field:titulo` o esperado
		# passa a ser o próprio título.
		if linha.name != titulo and not frappe.db.exists("Funcao Voluntario", titulo):
			frappe.rename_doc("Funcao Voluntario", linha.name, titulo, force=True, show_alert=False)

	frappe.db.commit()


def _montar_titulo(categoria: str | None, area: str, usados: set[str]) -> str:
	base = " — ".join(parte for parte in [(categoria or "").strip(), area] if parte) or "Função sem título"
	titulo = base
	sufixo = 2
	while titulo in usados:
		titulo = f"{base} ({sufixo})"
		sufixo += 1
	return titulo
