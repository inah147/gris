"""Popula o site local com dados fictícios para testes manuais.

Uso (dentro do bench, local de desenvolvimento):
    bench --site <site> execute gris.scripts.seed_demo_data.run

Via Frappe Manager:
    fm shell gris -c "bench --site gris.localhost execute gris.scripts.seed_demo_data.run"

Idempotente: pode ser executado várias vezes sem duplicar registros.

Cobre os doctypes "de conteúdo" criáveis manualmente dos módulos Gris, Financeiro,
Gestão de Adultos e Gestão de Projetos. Ficam de fora deste seed:
- Doctypes mestre/configuração já cobertos por fixtures (gris/hooks.py), como
  Centro de Custo, Categoria de Transacao, Unidade Organizacional (real),
  ODS Projeto, Mapeamento de perguntas e respostas da entrevista, Role,
  Role Profile e Email Template.

Instituicao Financeira e Carteira NÃO têm fixture — por isso o seed as cria
(`_seed_instituicoes_financeiras`/`_seed_carteiras`), senão as transações do extrato
falham na validação de link em um site novo.
- Singles de configuração (Configuracoes de Associados, Configuracoes WhatsApp etc.).
- Tabelas filhas (istable=1), que só existem como linhas de outro documento.
- Doctypes de importação de extrato bancário (Transacao BTG Empresas, Transacao
  Infinitepay *, Transacao Portao 3) e o respectivo log (Log Importacao de
  Associados), que representam dados brutos de integrações, não registros manuais.
- Transparencia, por exigir um arquivo real (campo Attach).
"""

import frappe
from frappe.utils import add_days, add_months, add_years, get_first_day, now, nowdate


def run():
	if not frappe.conf.get("developer_mode"):
		frappe.throw("Seed de dados só deve ser executado em ambiente de desenvolvimento (developer_mode).")

	unidades = _seed_unidades_organizacionais()
	_seed_habilidades()
	_seed_funcoes_voluntario()
	_seed_feriados()
	_seed_calendario()

	associados = _seed_associados(unidades)
	responsaveis = _seed_responsaveis()
	_seed_responsavel_vinculo(responsaveis, associados)

	novos_associados = _seed_novos_associados()
	_seed_fila_de_espera(novos_associados)
	_seed_agenda_de_visitas(novos_associados)
	_seed_pesquisa_de_novos_associados(responsaveis)
	_seed_resposta_manifestacao_de_interesse()
	_seed_metrica_mensal_de_associados()

	_seed_instituicoes_financeiras()
	_seed_carteiras()
	contas_fixas = _seed_contas_fixas()
	_seed_pagamentos_conta_fixa(contas_fixas)
	_seed_pagamentos_contribuicao_mensal(associados)
	_seed_transacoes_extrato_geral(associados, contas_fixas)
	_seed_transacoes_conciliacao()

	projeto = _seed_projeto(associados)
	_seed_avaliacao_de_projeto(projeto)
	_seed_entrevista_por_competencias(associados)

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


def _seed_funcoes_voluntario():
	funcoes = [
		{"categoria": "Escotista", "area": "Seção Lobinho Demo"},
		{"categoria": "Dirigente", "area": "Grupo Escoteiro Demo"},
	]
	for funcao in funcoes:
		if frappe.db.exists("Funcao Voluntario", funcao):
			continue
		frappe.get_doc({"doctype": "Funcao Voluntario", **funcao}).insert(ignore_permissions=True)


def _seed_feriados():
	feriados = [
		{"id": "DEMO-FERIADO-001", "nome": "Feriado Demo - Tiradentes", "data": "2026-04-21", "tipo": "Nacional"},
		{"id": "DEMO-FERIADO-002", "nome": "Feriado Demo - Aniversário da Cidade", "data": "2026-08-09", "tipo": "Municipal"},
	]
	for feriado in feriados:
		if frappe.db.exists("Feriados", feriado["id"]):
			continue
		frappe.get_doc({"doctype": "Feriados", **feriado}).insert(ignore_permissions=True)


def _seed_calendario():
	eventos = [
		{
			"id": "DEMO-CAL-001",
			"atividade": "Acampamento Demo de Fim de Ano",
			"secao": "Seção Escoteiro Demo",
			"local": "Sede do Grupo Escoteiro Demo",
			"nivel": "Local",
			"inicio": add_days(nowdate(), 30),
			"termino": add_days(nowdate(), 32),
		},
		{
			"id": "DEMO-CAL-002",
			"atividade": "Reunião Demo de Matilha",
			"secao": "Seção Lobinho Demo",
			"local": "Sede do Grupo Escoteiro Demo",
			"nivel": "Local",
			"inicio": add_days(nowdate(), 7),
			"termino": add_days(nowdate(), 7),
		},
	]
	for evento in eventos:
		if frappe.db.exists("Calendario", evento["id"]):
			continue
		frappe.get_doc({"doctype": "Calendario", **evento}).insert(ignore_permissions=True)


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
			"email": "ana.souza@example.com",
			"telefone": "11999990101",
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
			"email": "bruno.lima@example.com",
			"telefone": "11999990102",
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
			# Coordenadora do projeto demo: Envolvido no Projeto exige email e telefone.
			"email": "carla.pereira@example.com",
			"telefone": "11999990103",
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
	created = []
	for responsavel in responsaveis:
		existing = frappe.db.exists("Responsavel", {"cpf": responsavel["cpf"]})
		if existing:
			created.append(existing)
			continue
		doc = frappe.get_doc({"doctype": "Responsavel", **responsavel})
		doc.insert(ignore_permissions=True)
		created.append(doc.name)
	return created


def _seed_responsavel_vinculo(responsaveis, associados):
	if len(responsaveis) < 1 or len(associados) < 1:
		return
	vinculos = [
		{
			"responsavel": responsaveis[0],
			"beneficiario_associado": associados[0],
			"primeiro_responsavel": 1,
			"é_guardiao_legal": 1,
		},
	]
	for vinculo in vinculos:
		name = vinculo["responsavel"] + vinculo["beneficiario_associado"]
		if frappe.db.exists("Responsavel Vinculo", name):
			continue
		frappe.get_doc({"doctype": "Responsavel Vinculo", **vinculo}).insert(ignore_permissions=True)


def _seed_novos_associados():
	leads = [
		{
			"nome_completo": "Fernanda Lima Rocha",
			"cpf": "66666666666",
			"data_de_nascimento": add_years(nowdate(), -10),
			"sexo": "Feminínio",
			"ramo": "Lobinho",
			"status": "Visita Agendada",
			"visita_agendada": 1,
		},
		{
			"nome_completo": "Gustavo Henrique Alves",
			"cpf": "77777777777",
			"data_de_nascimento": add_years(nowdate(), -13),
			"sexo": "Masculino",
			"ramo": "Escoteiro",
			"status": "Fila de espera",
		},
	]
	created = []
	for lead in leads:
		existing = frappe.db.exists("Novo Associado", {"cpf": lead["cpf"]})
		if existing:
			created.append(existing)
			continue
		doc = frappe.get_doc({"doctype": "Novo Associado", **lead})
		doc.insert(ignore_permissions=True)
		created.append(doc.name)
	return created


def _seed_fila_de_espera(novos_associados):
	if len(novos_associados) < 2:
		return
	if frappe.db.exists("Fila de Espera", {"associado": novos_associados[1]}):
		return
	frappe.get_doc(
		{
			"doctype": "Fila de Espera",
			"associado": novos_associados[1],
			"ramo": "Escoteiro",
			"dt_inclusao_fila": now(),
		}
	).insert(ignore_permissions=True)


def _seed_agenda_de_visitas(novos_associados):
	if len(novos_associados) < 1:
		return
	if frappe.db.exists("Agenda de Visitas", {"jovem": novos_associados[0]}):
		return
	frappe.get_doc(
		{
			"doctype": "Agenda de Visitas",
			"jovem": novos_associados[0],
			"data_da_visita": add_days(nowdate(), 5),
			"ramo": "Lobinho",
		}
	).insert(ignore_permissions=True)


def _seed_pesquisa_de_novos_associados(responsaveis):
	if len(responsaveis) < 1:
		return
	responsavel = responsaveis[0]
	if frappe.db.exists("Pesqusa de Novos Associados", responsavel):
		return
	frappe.get_doc(
		{
			"doctype": "Pesqusa de Novos Associados",
			"responsavel": responsavel,
			"como_conheceu_movimento": "Através de um amigo",
			"nps_recepcao": "9",
			"data_resposta": nowdate(),
		}
	).insert(ignore_permissions=True)


def _seed_resposta_manifestacao_de_interesse():
	if frappe.db.exists("Resposta Manifestacao de Interesse", {"cpf_do_jovem": "88888888888"}):
		return
	frappe.get_doc(
		{
			"doctype": "Resposta Manifestacao de Interesse",
			"nome_do_jovem": "Helena Martins Cardoso",
			"cpf_do_jovem": "88888888888",
			"nome_do_responsavel": "Igor Martins Cardoso",
			"email_do_responsavel": "igor.cardoso@example.com",
			"celular_do_responsavel": "11999990003",
			"cpf_do_responsavel": "99999999999",
			"data_e_horario_de_resposta": now(),
			"dados_confirmados": 1,
			"aceite_lgpd": 1,
		}
	).insert(ignore_permissions=True)


def _seed_metrica_mensal_de_associados():
	mes_referencia = get_first_day(nowdate())
	if frappe.db.exists("Metrica Mensal de Associados", {"mes_referencia": mes_referencia}):
		return
	frappe.get_doc(
		{
			"doctype": "Metrica Mensal de Associados",
			"mes_referencia": mes_referencia,
			"qt_ativos_uel": 3,
			"qt_evasao": 0,
			"qt_novos": 2,
		}
	).insert(ignore_permissions=True)


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


def _seed_instituicoes_financeiras():
	"""Instituições usadas pelas transações demo.

	Não há fixture para Instituicao Financeira/Carteira: em um site novo elas não existem
	e as transações do extrato falhariam na validação de link.
	"""
	for nome in ("Portão 3", "Espécie", "BTG Empresas", "Infinitepay"):
		if frappe.db.exists("Instituicao Financeira", nome):
			continue
		frappe.get_doc(
			{"doctype": "Instituicao Financeira", "nome": nome, "ativa": 1}
		).insert(ignore_permissions=True)


def _seed_carteiras():
	"""Carteiras usadas pelas transações demo, vinculadas às instituições."""
	carteiras = [
		("Ramo Escoteiro", "Portão 3"),
		("Ramo Lobinho", "Portão 3"),
		("Espécie", "Espécie"),
		("BTG Empresas", "BTG Empresas"),
		("Infinitepay", "Infinitepay"),
	]
	for nome, instituicao in carteiras:
		if frappe.db.exists("Carteira", nome):
			continue
		frappe.get_doc(
			{
				"doctype": "Carteira",
				"nome": nome,
				"instituicao_financeira": instituicao,
				"ativa": 1,
				"saldo_inicial": 0,
			}
		).insert(ignore_permissions=True)


def _seed_transacoes_extrato_geral(associados, contas_fixas):
	mes_referencia = get_first_day(nowdate())

	transacoes = [
		{
			"id": "DEMO-EXTRATO-001",
			"descricao": "Doação Demo recebida via Pix",
			"debito_credito": "Crédito",
			"valor": 500,
			"valor_absoluto": 500,
			"data_transacao": mes_referencia,
			"metodo": "Pix",
			"carteira": "Ramo Escoteiro",
			"instituicao": "Portão 3",
			"categoria": "Doação",
		},
		{
			"id": "DEMO-EXTRATO-002",
			"descricao": "Pagamento Demo de contribuição mensal",
			"debito_credito": "Crédito",
			"valor": 60,
			"valor_absoluto": 60,
			"data_transacao": mes_referencia,
			"metodo": "Pix",
			"carteira": "Ramo Lobinho",
			"instituicao": "Portão 3",
			"categoria": "Contribuição Mensal",
			"beneficiario": associados[0] if associados else None,
		},
		{
			"id": "DEMO-EXTRATO-003",
			"descricao": "Pagamento Demo de conta fixa",
			"debito_credito": "Débito",
			"valor": -1200,
			"valor_absoluto": 1200,
			"data_transacao": mes_referencia,
			"metodo": "Boleto",
			"carteira": "Espécie",
			"instituicao": "Espécie",
			"categoria": "Contas Ordinárias",
			"conta_fixa": contas_fixas[0] if contas_fixas else None,
		},
	]

	for transacao in transacoes:
		if frappe.db.exists("Transacao Extrato Geral", transacao["id"]):
			continue
		frappe.get_doc({"doctype": "Transacao Extrato Geral", **transacao}).insert(ignore_permissions=True)


def _seed_transacoes_conciliacao():
	"""Transações para exercitar a tela de Conciliação (/financeiro/conciliacao).

	Monta pares em que a MESMA transação real aparece nas duas fontes — descrição no
	formato da planilha e no formato da integração — mais transações de sistema sem par.
	"""
	transacoes = [
		# Par exato: casa por valor e data.
		("CONC-P1", "Planilha", 150.00, 5, "Pix recebido de MARIA SILVA", "Contribuição Mensal"),
		("CONC-S1", "Sistema", 150.00, 5, "Pagamento em Pix de Maria Silva", None),
		# Par exato de doação.
		("CONC-P2", "Planilha", 300.00, 4, "Pix recebido de JOAO SOUZA", "Doação"),
		("CONC-S2", "Sistema", 300.00, 4, "Pagamento em Pix de Joao Souza", None),
		# Par com centavos de diferença: exercita a tolerância de valor (±R$1).
		("CONC-P3", "Planilha", 60.00, 3, "Pix recebido de ANA COSTA", "Contribuição Mensal"),
		("CONC-S3", "Sistema", 60.49, 3, "Pagamento em Pix de Ana Costa", None),
		# Sem par na planilha: exercita o botão "Não é duplicata".
		("CONC-S4", "Sistema", -89.90, 2, "Taxa de maquininha InfinitePay", None),
		("CONC-S5", "Sistema", 1250.00, 1, "Depósito de vendas InfinitePay", None),
	]

	for _id, fonte, valor, dias_atras, descricao, categoria in transacoes:
		if frappe.db.exists("Transacao Extrato Geral", _id):
			continue
		data = add_days(nowdate(), -dias_atras)
		frappe.get_doc(
			{
				"doctype": "Transacao Extrato Geral",
				"id": _id,
				"fonte": fonte,
				"descricao": descricao,
				"valor": valor,
				"valor_absoluto": abs(valor),
				"debito_credito": "Crédito" if valor > 0 else "Débito",
				"data_transacao": data,
				"data_deposito": data,
				"timestamp_transacao": f"{data} 10:00:00",
				"metodo": "Pix",
				"carteira": "Infinitepay",
				"instituicao": "Infinitepay",
				"categoria": categoria,
			}
		).insert(ignore_permissions=True)


def _seed_projeto(associados):
	nome_do_projeto = "Projeto Demo - Mutirão de Reforma da Sede"
	existing = frappe.db.exists("Projeto", {"nome_do_projeto": nome_do_projeto})
	if existing:
		return existing

	coordenador = associados[2] if len(associados) > 2 else associados[0]
	doc = frappe.get_doc(
		{
			"doctype": "Projeto",
			"nome_do_projeto": nome_do_projeto,
			"coordenador": coordenador,
			"status": "Rascunho",
			"data_de_inicio": nowdate(),
			"data_de_termino": add_months(nowdate(), 2),
			"justificativa": "A sede precisa de reparos para receber as atividades das seções.",
			"alinhamento_com_escotismo": "Desenvolve protagonismo juvenil e trabalho em equipe.",
			"ods": [{"ods": "ODS 04"}],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _seed_avaliacao_de_projeto(projeto):
	if not projeto:
		return
	if frappe.db.exists("Avaliacao de Projeto", {"projeto": projeto}):
		return
	frappe.get_doc(
		{
			"doctype": "Avaliacao de Projeto",
			"projeto": projeto,
			"status": "Em andamento",
		}
	).insert(ignore_permissions=True)


def _seed_entrevista_por_competencias(associados):
	if not associados:
		return
	escotista = associados[2] if len(associados) > 2 else associados[0]
	if frappe.db.exists("Entrevista por Competencias", {"associado": escotista}):
		return
	frappe.get_doc(
		{
			"doctype": "Entrevista por Competencias",
			"associado": escotista,
			"funcao_atual": "Escotista",
			"motivo_da_entrevista": "Ingresso",
		}
	).insert(ignore_permissions=True)
