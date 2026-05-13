import frappe

AREA_PORTARIA_NOME = "Portaria"


def execute():
	"""Garante area Portaria em toda festa e atribui Portaria a barracas sem area."""
	if not frappe.db.table_exists("Festa"):
		return
	if not frappe.db.table_exists("Area da Festa"):
		return
	if not frappe.db.table_exists("Barraca da Festa"):
		return

	festas = frappe.get_all("Festa", pluck="name")
	for festa_name in festas:
		_garantir_portaria(festa_name)

	barracas = frappe.get_all(
		"Barraca da Festa",
		filters={"area": ["in", ["", None]]},
		fields=["name", "festa"],
	)
	for b in barracas:
		portaria_name = f"{b.festa} - {AREA_PORTARIA_NOME}"
		if frappe.db.exists("Area da Festa", portaria_name):
			frappe.db.set_value("Barraca da Festa", b.name, "area", portaria_name)

	frappe.db.commit()

	for festa_name in festas:
		try:
			doc = frappe.get_doc("Festa", festa_name)
			doc.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Falha ao recalcular Festa apos patch area: {festa_name}",
			)


def _garantir_portaria(festa_name: str) -> None:
	nome_doc = f"{festa_name} - {AREA_PORTARIA_NOME}"
	if frappe.db.exists("Area da Festa", nome_doc):
		return
	doc = frappe.new_doc("Area da Festa")
	doc.festa = festa_name
	doc.nome_area = AREA_PORTARIA_NOME
	doc.descricao = "Area da portaria. Recebe a arrecadacao dos convites."
	doc.tipo_coord = "Outro"
	doc.insert(ignore_permissions=True)
