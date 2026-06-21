"""Popula o site local com dados fictícios para testes manuais.

Uso (dentro do bench, local de desenvolvimento):
    bench --site <site> execute gris.scripts.seed_demo_data.run

Via Frappe Manager:
    fm shell gris -c "bench --site gris.localhost execute gris.scripts.seed_demo_data.run"

Idempotente: pode ser executado várias vezes sem duplicar registros.
"""

import frappe
from frappe.utils import add_years, get_first_day, nowdate


def run():
	if not frappe.conf.get("developer_mode"):
		frappe.throw("Seed de dados só deve ser executado em ambiente de desenvolvimento (developer_mode).")

	unidades = _seed_unidades_organizacionais()
	_seed_habilidades()
	associados = _seed_associados(unidades)
	_seed_responsaveis()
	contas_fixas = _seed_contas_fixas()
	_seed_pagamentos_conta_fixa(contas_fixas)
	_seed_pagamentos_contribuicao_mensal(associados)

	frappe.db.commit()
	print("Seed de dados concluído.")


def _seed_unidades_organizacionais():
	unidades = [
		{"area": "Grupo Escoteiro Demo", "responde_para": None},
		{"area": "Seção Lobinho Demo", "responde_para": "Grupo Escoteiro Demo"},
		{"area": "Seção Escoteiro Demo", "responde_para": "Grupo Escoteiro Demo"},
	]
	for unidade in unidades:
		if frappe.db.exists("Unidade Organizacional", unidade["area"]):
			continue
		frappe.get_doc({"doctype": "Unidade Organizacional", **unidade}).insert(ignore_permissions=True)
	return [u["area"] for u in unidades]


def _seed_habilidades():
	for habilidade in ["Primeiros Socorros", "Culinária ao ar livre", "Orientação e Mapas"]:
		if frappe.db.exists("Habilidade", habilidade):
			continue
		frappe.get_doc({"doctype": "Habilidade", "habilidade": habilidade}).insert(ignore_permissions=True)


def _seed_associados(unidades):
	associados = [
		{
			"nome_completo": "Ana Beatriz Souza",
			"cpf": "11111111111",
			"data_de_nascimento": add_years(nowdate(), -12),
			"sexo": "Feminino",
			"categoria": "Beneficiário",
			"ramo": "Lobinho",
			"area": unidades[1],
			"ingresso": add_years(nowdate(), -1),
		},
		{
			"nome_completo": "Bruno Carlos Lima",
			"cpf": "22222222222",
			"data_de_nascimento": add_years(nowdate(), -14),
			"sexo": "Masculino",
			"categoria": "Beneficiário",
			"ramo": "Escoteiro",
			"area": unidades[2],
			"ingresso": add_years(nowdate(), -2),
		},
		{
			"nome_completo": "Carla Dias Pereira",
			"cpf": "33333333333",
			"data_de_nascimento": add_years(nowdate(), -34),
			"sexo": "Feminino",
			"categoria": "Escotista",
			"ramo": "Não se aplica",
			"area": unidades[0],
			"ingresso": add_years(nowdate(), -3),
		},
	]

	created = []
	for associado in associados:
		ingresso = associado.pop("ingresso")
		existing = frappe.db.exists("Associado", {"nome_completo": associado["nome_completo"]})
		if existing:
			created.append(existing)
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"historico_no_grupo": [{"data_de_ingresso": ingresso}],
				**associado,
			}
		)
		doc.insert(ignore_permissions=True)
		created.append(doc.name)
	return created


def _seed_responsaveis():
	responsaveis = [
		{
			"nome_completo": "Daniela Fernandes Costa",
			"cpf": "44444444444",
			"email": "daniela.fernandes@example.com",
			"celular": "11999990001",
		},
		{
			"nome_completo": "Eduardo Gomes Martins",
			"cpf": "55555555555",
			"email": "eduardo.martins@example.com",
			"celular": "11999990002",
		},
	]
	for responsavel in responsaveis:
		if frappe.db.exists("Responsavel", {"cpf": responsavel["cpf"]}):
			continue
		frappe.get_doc({"doctype": "Responsavel", **responsavel}).insert(ignore_permissions=True)


def _seed_contas_fixas():
	contas = [
		{"descricao": "Aluguel da Sede Demo", "valor": 1200.00, "dia_vencimento": 10, "ativa": 1},
		{"descricao": "Conta de Luz Demo", "valor": 350.50, "dia_vencimento": 15, "ativa": 1},
	]
	nomes = []
	for conta in contas:
		if not frappe.db.exists("Conta Fixa", conta["descricao"]):
			frappe.get_doc({"doctype": "Conta Fixa", **conta}).insert(ignore_permissions=True)
		nomes.append(conta["descricao"])
	return nomes


def _seed_pagamentos_conta_fixa(contas_fixas):
	mes_referencia = get_first_day(nowdate())
	for conta in contas_fixas:
		if frappe.db.exists("Pagamento Conta Fixa", {"conta": conta, "mes_referencia": mes_referencia}):
			continue
		frappe.get_doc(
			{
				"doctype": "Pagamento Conta Fixa",
				"conta": conta,
				"status": "Em Aberto",
				"mes_referencia": mes_referencia,
				"valor": frappe.db.get_value("Conta Fixa", conta, "valor"),
			}
		).insert(ignore_permissions=True)


def _seed_pagamentos_contribuicao_mensal(associados):
	mes_referencia = get_first_day(nowdate())
	for associado in associados:
		if frappe.db.exists(
			"Pagamento Contribuicao Mensal", {"associado": associado, "mes_de_referencia": mes_referencia}
		):
			continue
		frappe.get_doc(
			{
				"doctype": "Pagamento Contribuicao Mensal",
				"associado": associado,
				"status": "Em Aberto",
				"mes_de_referencia": mes_referencia,
				"valor": 60,
			}
		).insert(ignore_permissions=True)
