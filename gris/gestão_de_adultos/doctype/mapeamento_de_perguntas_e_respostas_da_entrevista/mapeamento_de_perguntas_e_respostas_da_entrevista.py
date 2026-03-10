import frappe
from frappe.model.document import Document


class Mapeamentodeperguntaserespostasdaentrevista(Document):
	@staticmethod
	def prepare_for_import(docdict):
		id_origem = docdict.get("id_origem")
		if id_origem is None:
			return

		existing_name = frappe.db.get_value(
			docdict.get("doctype"),
			{"id_origem": id_origem},
			"name",
		)

		docdict["name"] = existing_name or str(id_origem)
