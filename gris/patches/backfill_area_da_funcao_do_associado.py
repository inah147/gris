import frappe

DOCTYPE = "Funcao Voluntario"
COLUNA = "area"


def execute():
	"""Garante área em toda linha de `Associado.funcoes_internas`.

	A coluna `area` da linha era só cache do `fetch_from` da função. Agora ela é a
	fonte de verdade da posição da pessoa no organograma e virou obrigatória, então
	precisa estar preenchida antes que a coluna de origem seja derrubada.

	Roda antes de `unificar_funcoes_de_secao`: depois da fusão, a linha aponta para a
	função genérica e a seção não existe mais em `Funcao Voluntario` — este JOIN não
	resolveria mais nada.
	"""
	if not frappe.db.table_exists(DOCTYPE):
		return
	if not frappe.db.has_column(DOCTYPE, COLUNA):
		return
	if not frappe.db.table_exists("Funcao do Associado"):
		return

	# Nomes de tabela e coluna são literais fixos; não há entrada de usuário aqui.
	frappe.db.sql(
		"""
		UPDATE `tabFuncao do Associado` fa
		  JOIN `tabFuncao Voluntario` fv ON fv.`name` = fa.`funcao`
		   SET fa.`area` = fv.`area`
		 WHERE fa.`parenttype` = 'Associado'
		   AND IFNULL(fa.`area`, '') = ''
		   AND IFNULL(fv.`area`, '') != ''
		"""
	)

	restantes = frappe.db.count(
		"Funcao do Associado", {"parenttype": "Associado", "area": ["in", ["", None]]}
	)
	if restantes:
		# Histórico sem área é dado, não defeito de configuração: não se inventa área
		# para ninguém. Fica visível no aviso `funcoes_sem_area` do organograma.
		print(f"  → {restantes} linha(s) de função interna seguem sem área; veja o aviso do organograma.")

	frappe.db.commit()
