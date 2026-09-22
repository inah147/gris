import frappe

from gris.utils.documento import id_por_cpf, ids_possiveis_por_cpf


def execute():
	"""Acerta o identificador dos ``Associado`` criados antes da convenção canônica do CPF.

	O controller hasheava o CPF como o operador digitou, então o cadastro nascia com um
	``name`` diferente do que ``Responsavel`` e ``Novo Associado`` derivam do mesmo CPF —
	era isso que impedia a recepção de encontrar o cadastro do jovem ao finalizar. E o
	campo ``cpf`` era re-hasheado em cada gravação, afastando-o do próprio ``name``.

	Duas correções, ambas idempotentes:

	1. ``cpf = name`` onde os dois divergem, desfazendo o hash acumulado. O ``name`` é a
	   referência porque é ele que o resto do sistema aponta.
	2. Renomeia para o identificador canônico os cadastros cujo CPF cru ainda existe em
	   ``Novo Associado`` — o único lugar onde o número ainda está em claro. É esse rename
	   que solta os jovens já parados no fim do funil. Os demais cadastros antigos ficam
	   com o hash que têm (o CPF cru deles não existe mais em lugar nenhum) e continuam
	   sendo encontrados pelas duas convenções em
	   ``gris.utils.documento.ids_possiveis_por_cpf``.
	"""
	if not frappe.db.table_exists("Associado") or not frappe.db.table_exists("Novo Associado"):
		return

	_realinhar_campo_cpf()
	_renomear_para_o_id_canonico()

	frappe.db.commit()


def _realinhar_campo_cpf() -> None:
	associado = frappe.qb.DocType("Associado")
	divergentes = (
		frappe.qb.from_(associado)
		.select(associado.name)
		.where(associado.cpf.notnull() & (associado.cpf != associado.name))
	).run(as_dict=True)

	for linha in divergentes:
		frappe.db.set_value("Associado", linha.name, "cpf", linha.name, update_modified=False)

	if divergentes:
		print(f"  → {len(divergentes)} Associado com o campo cpf realinhado ao name")


def _renomear_para_o_id_canonico() -> None:
	renomeados = 0
	conflitos = 0

	for jovem in frappe.get_all("Novo Associado", fields=["name", "cpf"]):
		canonico = id_por_cpf(jovem.cpf)
		if not canonico:
			continue

		legado = _associado_legado(jovem.cpf, canonico)
		if not legado:
			continue

		if frappe.db.exists("Associado", canonico):
			# Já existe cadastro com o nome certo: renomear criaria conflito, e escolher
			# qual dos dois sobrevive é decisão de quem cuida dos dados, não da migração.
			print(f"  ⚠️  Associado {legado} e {canonico} coexistem para o mesmo CPF — conferir à mão")
			conflitos += 1
			continue

		frappe.rename_doc("Associado", legado, canonico, force=True, show_alert=False)
		frappe.db.set_value("Associado", canonico, "cpf", canonico, update_modified=False)
		renomeados += 1

	if renomeados or conflitos:
		print(f"  → {renomeados} Associado renomeado para o identificador canônico ({conflitos} conflito(s))")


def _associado_legado(cpf: str | None, canonico: str) -> str | None:
	"""``name`` do Associado daquele CPF gravado em alguma convenção antiga."""
	for candidato in ids_possiveis_por_cpf(cpf):
		if candidato == canonico:
			continue
		if frappe.db.exists("Associado", candidato):
			return candidato

	return None
