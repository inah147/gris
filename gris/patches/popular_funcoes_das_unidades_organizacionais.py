import frappe

DOCTYPE = "Funcao Voluntario"
COLUNA = "area"


def execute():
	"""Transforma o Link único `Funcao Voluntario.area` no vínculo M:N da área.

	A função deixou de pertencer a uma área só: quem lista as funções agora é a
	`Unidade Organizacional`, pela child table `funcoes`. Este patch reconstrói
	esses vínculos a partir do que o modelo antigo já registrava.

	Roda em post_model_sync porque `tabFuncao da Area` só existe depois do sync do
	DocType — e, do outro lado, a coluna `area` continua no banco, porque o sync do
	Frappe nunca faz DROP COLUMN. A janela entre as duas coisas é exatamente aqui.
	"""
	if not frappe.db.table_exists(DOCTYPE):
		return
	if not frappe.db.has_column(DOCTYPE, COLUNA):
		# Patch já rodou (a coluna é derrubada por `remover_area_da_funcao_voluntario`),
		# ou a instalação é nova e nunca teve o campo.
		return

	# O DocField já sumiu com o sync, então `frappe.get_all` não enxerga mais a
	# coluna: a leitura precisa ser em SQL cru.
	linhas = frappe.db.sql(
		"SELECT `name`, `area` FROM `tabFuncao Voluntario` WHERE IFNULL(`area`, '') != ''",
		as_dict=True,
	)
	if not linhas:
		return

	existentes = {
		(v["parent"], v["funcao"])
		for v in frappe.get_all(
			"Funcao da Area",
			filters={"parenttype": "Unidade Organizacional"},
			fields=["parent", "funcao"],
		)
	}
	proximo_idx: dict[str, int] = {}
	criados = 0

	for linha in linhas:
		area = linha["area"]
		funcao = linha["name"]
		if (area, funcao) in existentes:
			continue
		if not frappe.db.exists("Unidade Organizacional", area):
			# Área apagada depois que a função foi criada: não há vínculo a fazer.
			continue

		if area not in proximo_idx:
			proximo_idx[area] = (
				frappe.db.count("Funcao da Area", {"parent": area, "parenttype": "Unidade Organizacional"})
				or 0
			)
		proximo_idx[area] += 1

		# Inserir o filho direto, sem `get_doc(area).save()`: o `validate()` da
		# Unidade Organizacional recusa responsável inativo, e uma área legada nessa
		# situação derrubaria o migrate inteiro por um motivo sem relação nenhuma.
		frappe.get_doc(
			{
				"doctype": "Funcao da Area",
				"parent": area,
				"parenttype": "Unidade Organizacional",
				"parentfield": "funcoes",
				"funcao": funcao,
				"idx": proximo_idx[area],
			}
		).insert(ignore_permissions=True)
		existentes.add((area, funcao))
		criados += 1

	if criados:
		print(f"  → {criados} vínculo(s) de função criados nas unidades organizacionais.")
	frappe.db.commit()
