"""Seed do módulo Gris (associados, responsáveis, calendários, configs)."""

import random
from datetime import date, timedelta

import frappe

from ..credentials import get
from ..faker_helpers import (
	RAMO_FAIXAS,
	cpf_hash,
	date_range,
	fake,
	fake_cep,
	fake_cpf,
	fake_data_nascimento_adulto,
	fake_data_nascimento_para_idade,
	fake_data_nascimento_ramo,
	fake_telefone,
	first_of_month,
)
from ..safe_insert import all_names, first_name, safe_get_or_create, safe_insert, set_single

# ===========================================================================
# Masters simples (sem dependência interna, e que NÃO são fixtures)
# ===========================================================================


def seed_habilidades(n: int):
	skills = [
		"Comunicação",
		"Liderança",
		"Trabalho em equipe",
		"Organização",
		"Resolução de problemas",
		"Criatividade",
		"Pensamento crítico",
		"Tecnologia",
		"Pedagogia",
		"Esportes",
		"Música",
		"Artes",
		"Primeiros socorros",
		"Cozinha",
		"Idiomas",
		"Escrita",
		"Fotografia",
		"Marketing",
	]
	created = 0
	for nome in skills[:n]:
		safe_insert({"doctype": "Habilidade", "habilidade": nome})
		created += 1
	print(f"  → {created} Habilidade")


# Áreas estruturais do grupo: (área, área-mãe, ordem). As áreas de seção não
# entram aqui — elas nascem de `sincronizar_secoes()`, a partir do campo `secao`.
UNIDADES_ORGANIZACIONAIS = [
	("Presidência", None, 0),
	("Programa", "Presidência", 1),
	("Administrativo", "Presidência", 2),
	("Financeiro", "Presidência", 3),
	("Manutenção", "Administrativo", 1),
	("Eventos", "Administrativo", 2),
]


def seed_unidades_organizacionais():
	"""Monta a árvore de áreas. Sem ela o organograma nasce vazio em dev."""
	created = 0
	for area, mae, ordem in UNIDADES_ORGANIZACIONAIS:
		if frappe.db.exists("Unidade Organizacional", area):
			continue
		safe_insert(
			{
				"doctype": "Unidade Organizacional",
				"area": area,
				"responde_para": mae,
				"ordem": ordem,
				"ativa": 1,
				"descricao": f"Área de {area} do grupo.",
			}
		)
		created += 1
	print(f"  → {created} Unidade Organizacional")


# (título, linha, áreas, responsabilidades). A função vale em todas as áreas da
# lista: "Membro de Equipe" e "Coordenador(a) de Adultos" existem com mais de uma
# justamente para o seed exercitar o vínculo M:N.
FUNCOES_VOLUNTARIO = [
	("Diretor(a) Presidente", "Dirigente", ["Presidência"], ["Representar o grupo", "Presidir reuniões"]),
	(
		"Diretor(a) de Programa",
		"Dirigente",
		["Programa"],
		["Coordenar as seções", "Acompanhar escotistas"],
	),
	(
		"Diretor(a) Administrativo",
		"Dirigente",
		["Administrativo"],
		["Cuidar da sede", "Organizar documentos"],
	),
	("Diretor(a) Financeiro", "Dirigente", ["Financeiro"], ["Prestar contas", "Controlar o caixa"]),
	(
		"Coordenador(a) de Adultos",
		"Dirigente",
		["Administrativo", "Programa"],
		["Acompanhar a linha de formação"],
	),
	("Coordenador(a) de Eventos", "Colaborador", ["Eventos"], ["Organizar festas e campanhas"]),
	(
		"Membro de Equipe",
		"Colaborador",
		["Manutenção", "Eventos"],
		["Executar os mutirões de manutenção"],
	),
]


def seed_funcoes_voluntario(n: int):
	"""Funções internas do grupo, com suas responsabilidades e áreas."""
	created = 0
	vinculos = 0
	for titulo, categoria, areas, responsabilidades in FUNCOES_VOLUNTARIO[:n]:
		if not frappe.db.exists("Funcao Voluntario", titulo):
			safe_insert(
				{
					"doctype": "Funcao Voluntario",
					"titulo": titulo,
					"categoria": categoria,
					"ativa": 1,
					"descricao": f"{titulo} — função interna do grupo.",
					"responsabilidades": [{"responsabilidade": r} for r in responsabilidades],
				}
			)
			created += 1
		vinculos += _vincular_funcao_as_areas(titulo, areas)
	print(f"  → {created} Funcao Voluntario ({vinculos} vínculo(s) de área)")


def _vincular_funcao_as_areas(titulo: str, areas: list[str]) -> int:
	"""Liga a função às áreas onde ela pode ser exercida.

	Roda antes de `seed_responsaveis_de_area`: as áreas ainda estão sem responsável,
	então o `save()` não esbarra na validação de responsável.
	"""
	criados = 0
	for area in areas:
		if not frappe.db.exists("Unidade Organizacional", area):
			continue
		if frappe.db.exists(
			"Funcao da Area",
			{"parent": area, "parenttype": "Unidade Organizacional", "funcao": titulo},
		):
			continue
		doc = frappe.get_doc("Unidade Organizacional", area)
		doc.append("funcoes", {"funcao": titulo})
		doc.save(ignore_permissions=True)
		criados += 1
	return criados


def seed_responsaveis_de_area(associado_names: list[str]):
	"""Elege um responsável para cada área, respeitando a hierarquia.

	Roda depois de `seed_associados` porque `Unidade Organizacional.responsavel`
	é Link para Associado.
	"""
	if not associado_names:
		return

	elegiveis = frappe.get_all(
		"Associado",
		filters={
			"name": ["in", associado_names],
			"categoria": ["!=", "Beneficiário"],
			"status_no_grupo": "Ativo",
		},
		pluck="name",
	)
	if not elegiveis:
		return

	# A área vem da função interna: é o mesmo caminho que o organograma percorre.
	from gris.api.gestao_adultos.organograma import lotacoes_atuais

	lotacoes, _sem_area = lotacoes_atuais(elegiveis)
	por_area: dict[str, list[str]] = {}
	for linha in sorted(lotacoes, key=lambda x: x["associado"]):
		por_area.setdefault(linha["area"], []).append(linha["associado"])

	definidos = 0
	ja_lidera: set[str] = set()
	for area, _mae, _ordem in UNIDADES_ORGANIZACIONAIS:
		if not frappe.db.exists("Unidade Organizacional", area):
			continue
		if frappe.db.get_value("Unidade Organizacional", area, "responsavel"):
			continue
		candidatos = [c for c in por_area.get(area, []) if c not in ja_lidera]
		if not candidatos:
			continue
		escolhido = candidatos[0]
		ja_lidera.add(escolhido)
		frappe.db.set_value("Unidade Organizacional", area, "responsavel", escolhido)
		definidos += 1
	print(f"  → {definidos} responsáveis de área")


def seed_feriados(n: int):
	"""Feriados nacionais e municipais (autoname=field:id)."""
	base = [
		("nat-2025-01-01", "Confraternização Universal", "2025-01-01", "nacional"),
		("nat-2025-04-21", "Tiradentes", "2025-04-21", "nacional"),
		("nat-2025-09-07", "Independência", "2025-09-07", "nacional"),
		("nat-2025-11-15", "Proclamação da República", "2025-11-15", "nacional"),
		("nat-2025-12-25", "Natal", "2025-12-25", "nacional"),
		("nat-2026-01-01", "Confraternização Universal 2026", "2026-01-01", "nacional"),
		("nat-2026-04-21", "Tiradentes 2026", "2026-04-21", "nacional"),
	]
	created = 0
	for id_, nome, dt, tipo in base[:n]:
		safe_insert(
			{
				"doctype": "Feriados",
				"id": id_,
				"nome": nome,
				"data": dt,
				"tipo": tipo,
				"descricao": f"Feriado {tipo}: {nome}",
			}
		)
		created += 1
	print(f"  → {created} Feriados")


# ===========================================================================
# Pessoas
# ===========================================================================


def seed_responsaveis(n: int) -> list[str]:
	"""Cria n Responsáveis. Nome = MD5(cpf). Retorna lista de nomes criados/existentes."""
	habilidades = all_names("Habilidade", limit=10)
	created = 0
	names = []
	for _ in range(n):
		cpf = fake_cpf()
		name = cpf_hash(cpf)
		if frappe.db.exists("Responsavel", name):
			names.append(name)
			continue
		# Faker pt_BR
		nome = fake.name()
		doc = frappe.get_doc(
			{
				"doctype": "Responsavel",
				"nome_completo": nome,
				"data_de_nascimento": fake_data_nascimento_adulto(),
				"sexo": random.choice(["Masculino", "Feminino"]),
				"estado_civil": random.choice(["Solteiro(a)", "Casado(a)", "Divorciado(a)", "Viúvo(a)"]),
				"cpf": cpf,
				"rg": fake.numerify("##.###.###-#"),
				"orgao_expedidor": "SSP",
				"cep": fake_cep(),
				"endereço": fake.street_name(),
				"número": random.randint(1, 9999),
				"complemento": random.choice(["", "Apto 101", "Casa", "Bloco B"]),
				"bairro": fake.bairro(),
				"estado": random.choice(["SP", "RJ", "MG", "PR"]),
				"cidade": fake.city(),
				"email": fake.email(),
				"celular": fake_telefone(),
				"escolaridade": random.choice(
					[
						"Ensino médio completo",
						"Ensino superior completo",
						"Especialização completa",
					]
				),
				"profissão": fake.job(),
				"local_de_trabalho": fake.company(),
				"o_que_gosta_de_fazer_no_dia_a_dia": fake.sentence(),
				"habilidades": [
					{"habilidade": h} for h in random.sample(habilidades, min(2, len(habilidades)))
				]
				if habilidades
				else [],
			}
		)
		try:
			doc.insert(ignore_permissions=True)
			names.append(doc.name)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Responsavel '{nome}': {e}")
	print(f"  → {created} Responsavel")
	return names


def seed_novos_associados(por_ramo: int) -> list[str]:
	"""Cria `por_ramo` novos associados para CADA ramo (cobre 5 ramos)."""
	created = 0
	names = []
	statuses = [
		"Novo Contato",
		"Conversa Inicial",
		"Visita Agendada",
		"Aguardar Dados",
		"Fazer Registro",
		"Acompanhamento",
		"Fila de espera",
		"Concluído",
	]
	for ramo, _idade_min, _idade_max in RAMO_FAIXAS:
		for i in range(por_ramo):
			cpf = fake_cpf()
			name = cpf_hash(cpf)
			if frappe.db.exists("Novo Associado", name):
				names.append(name)
				continue
			status = statuses[i % len(statuses)]
			data_nasc = fake_data_nascimento_ramo(ramo)
			doc = frappe.get_doc(
				{
					"doctype": "Novo Associado",
					"nome_completo": fake.name(),
					"data_de_nascimento": data_nasc,
					"sexo": random.choice(["Masculino", "Feminino"]),
					"etnia": random.choice(["Branca", "Parda", "Preta", "Amarela", "Indígena"]),
					"estrangeiro": 0,
					"pais_nascimento": "Brasil",
					"uf_de_nascimento": random.choice(["SP", "RJ", "MG"]),
					"cidade_de_nascimento": fake.city(),
					"rg": fake.numerify("##.###.###-#"),
					"orgao_expedidor": "SSP",
					"cpf": cpf,
					"estado_civil": "Solteiro(a)",
					"religiao": random.choice(
						["Católica", "Evangélico/Petencostal", "Espírita", "Sem Religião"]
					),
					"escolaridade": "Ensino fundamental incompleto",
					"profissao": "Estudante",
					"cep": fake_cep(),
					"endereco": fake.street_name(),
					"numero": random.randint(1, 9999),
					"estado": random.choice(["SP", "RJ", "MG"]),
					"cidade": fake.city(),
					"bairro": fake.bairro(),
					"email": fake.email(),
					"celular": fake_telefone(),
					"email_cobranca": fake.email(),
					"telefone_cobranca": fake_telefone(),
					"status": status,
					"ramo": ramo,
					"tipo_de_registro": random.choice(["Provisório", "Definitivo"]),
					"visita_agendada": 1 if status in {"Visita Agendada", "Aguardar Dados"} else 0,
					"primeira_visita_realizada": 1
					if status not in {"Novo Contato", "Conversa Inicial"}
					else 0,
					"dados_para_registro_enviados": 1
					if status in {"Fazer Registro", "Acompanhamento", "Concluído"}
					else 0,
					"boleto_definitivo_gerado": 1 if status == "Concluído" else 0,
					"registro_definitivo_efetivado": 1 if status == "Concluído" else 0,
				}
			)
			try:
				doc.insert(ignore_permissions=True)
				names.append(doc.name)
				created += 1
			except Exception as e:
				print(f"  ⚠️  Novo Associado: {e}")
	print(f"  → {created} Novo Associado")
	return names


def _historico_para(status_no_grupo: str, anos_atras: int = 3) -> list[dict]:
	hoje = date.today()
	ingresso = date(hoje.year - anos_atras, max(1, hoje.month), 1)
	if status_no_grupo == "Inativo":
		desligamento = hoje - timedelta(days=random.randint(30, 365))
		return [{"data_de_ingresso": ingresso, "data_de_desligamento": desligamento}]
	return [{"data_de_ingresso": ingresso}]


RAMOS_DE_SECAO = ("Lobinho", "Escoteiro", "Sênior", "Pioneiro")

#: Nome da seção de cada ramo, como o Paxtu preenche o campo `secao`.
SECAO_POR_RAMO = {
	"Filhotes": "Ninho",
	"Lobinho": "Alcateia",
	"Escoteiro": "Tropa Escoteira",
	"Sênior": "Tropa Sênior",
	"Pioneiro": "Clã Pioneiro",
}
AREAS_DIRIGENTE = ("Presidência", "Programa", "Administrativo", "Financeiro")
AREAS_APOIO = ("Manutenção", "Eventos")


def _area_para(categoria: str, ramo: str, areas_existentes: set[str]) -> str | None:
	"""Espalha os adultos pela árvore para o organograma ter profundidade.

	Escotista fica de fora: a área dele sai da seção, via `sincronizar_secoes()`.
	"""
	if categoria == "Escotista":
		return None
	if categoria == "Dirigente":
		candidatas = AREAS_DIRIGENTE
	else:
		candidatas = AREAS_APOIO

	disponiveis = [a for a in candidatas if a in areas_existentes]
	return random.choice(disponiveis) if disponiveis else None


def _funcoes_internas_para(
	area: str | None,
	funcoes_por_area: dict[str, list[str]],
	todos_os_pares: list[tuple[str, str]] | None = None,
) -> list[dict]:
	funcoes = funcoes_por_area.get(area or "") or []
	if not funcoes:
		return []

	hoje = date.today()
	inicio_atual = hoje - timedelta(days=random.randint(90, 900))
	escolhida = random.choice(funcoes)
	# A área vai na linha: a mesma função pode valer em várias, então só a linha
	# sabe onde a pessoa exerce.
	linhas = [{"funcao": escolhida, "area": area, "principal": 1, "data_inicio": inicio_atual}]

	# Parte das pessoas carrega uma função antiga: é o que dá histórico para o
	# painel de detalhes mostrar mais de uma linha e um período já encerrado.
	anteriores = [par for par in (todos_os_pares or []) if par != (escolhida, area)]
	if anteriores and random.random() < 0.4:
		funcao_anterior, area_anterior = random.choice(anteriores)
		fim_anterior = inicio_atual - timedelta(days=random.randint(1, 60))
		linhas.append(
			{
				"funcao": funcao_anterior,
				"area": area_anterior,
				"principal": 0,
				"data_inicio": fim_anterior - timedelta(days=random.randint(365, 1095)),
				"data_fim": fim_anterior,
			}
		)
	return linhas


def seed_associados(por_combinacao: int, extras: int) -> list[str]:
	"""
	Cria a matriz {status x status_no_grupo x categoria} + extras.

	Cobertura mínima: 1 por combinação garantida.
	"""
	statuses = ["Válido", "Vencido", "Desconhecido"]
	statuses_grupo = ["Ativo", "Inativo"]
	categorias = ["Beneficiário", "Dirigente", "Escotista", "Contribuinte", "Pais/Responsáveis"]
	# autoname = field:cpf — usa CPF como name diretamente
	areas_existentes = set(all_names("Unidade Organizacional"))

	# Funções internas disponíveis por área, para o organograma não nascer sem cargo.
	# A fonte é o vínculo M:N da área, não mais um campo na função.
	ativas = set(frappe.get_all("Funcao Voluntario", filters={"ativa": 1}, pluck="name"))
	funcoes_por_area: dict[str, list[str]] = {}
	todos_os_pares: list[tuple[str, str]] = []
	for linha in frappe.get_all(
		"Funcao da Area",
		filters={"parenttype": "Unidade Organizacional"},
		fields=["parent", "funcao"],
	):
		if linha.funcao not in ativas:
			continue
		funcoes_por_area.setdefault(linha.parent, []).append(linha.funcao)
		todos_os_pares.append((linha.funcao, linha.parent))

	created = 0
	names = []

	# Matriz de cenários
	combos = [(s, sg, c) for s in statuses for sg in statuses_grupo for c in categorias]

	def _create_one(status, status_grupo, categoria, ramo=None):
		nonlocal created
		# Tenta até 5 vezes para evitar colisão de CPF/registro únicos
		cpf = None
		expected_name = None
		for _ in range(5):
			cpf_try = fake_cpf()
			h = cpf_hash(cpf_try)
			if not frappe.db.exists("Associado", h):
				cpf, expected_name = cpf_try, h
				break
		if not cpf:
			# Todos colidiram — pula este combo
			return None
		# Registro único: usa últimos 6 dígitos do hash p/ garantir unicidade
		registro_unique = expected_name[-6:].upper()
		hoje = date.today()
		validade = hoje + timedelta(days=180) if status == "Válido" else hoje - timedelta(days=60)
		idade = random.randint(7, 21) if categoria == "Beneficiário" else random.randint(25, 60)
		if ramo:
			ramo_efetivo = ramo
		elif categoria == "Beneficiário":
			ramo_efetivo = random.choice([r[0] for r in RAMO_FAIXAS])
		elif categoria == "Escotista":
			# Escotista sem ramo não renderiza o badge de ramo no organograma.
			ramo_efetivo = random.choice(RAMOS_DE_SECAO)
		else:
			ramo_efetivo = "Não se aplica"

		area_efetiva = _area_para(categoria, ramo_efetivo, areas_existentes)
		funcoes_internas = _funcoes_internas_para(area_efetiva, funcoes_por_area, todos_os_pares)
		doc = frappe.get_doc(
			{
				"doctype": "Associado",
				"cpf": cpf,
				"nome_completo": fake.name(),
				"sexo": random.choice(["Masculino", "Feminino"]),
				"data_de_nascimento": fake_data_nascimento_para_idade(idade),
				"etnia": random.choice(["Branca", "Parda", "Preta"]),
				"religiao": "Católica",
				"estado_civil": "Solteiro" if categoria == "Beneficiário" else "Casado",
				"status": status,
				"validade_registro": validade,
				"tipo_registro": random.choice(["Definitivo", "Provisório"]),
				"status_no_grupo": status_grupo,
				"anos_afastamento": random.randint(0, 3) if status_grupo == "Inativo" else 0,
				"registro": registro_unique,
				"registro_isento": "Não",
				"email": fake.email(),
				"telefone": fake_telefone(),
				"id_escoteiros": fake.numerify("########"),
				"cep_residencia": fake_cep(),
				"numero_residencia": random.randint(1, 9999),
				"historico_no_grupo": _historico_para(status_grupo),
				"pais_divorciados": "Não",
				"tipo_guarda": "Compartilhada" if categoria == "Beneficiário" else "-",
				"nome_responsavel_1": fake.name() if categoria == "Beneficiário" else "",
				"telefone_responsavel_1": fake_telefone() if categoria == "Beneficiário" else "",
				"email_responsavel_1": fake.email() if categoria == "Beneficiário" else "",
				"cpf_responsavel_1": fake_cpf() if categoria == "Beneficiário" else "",
				"guardiao_legal_responsavel_1": 1 if categoria == "Beneficiário" else 0,
				"categoria": categoria,
				"ramo": ramo_efetivo,
				"funcoes_internas": funcoes_internas,
				"funcao": "Beneficiário" if categoria == "Beneficiário" else fake.job()[:30],
				"secao": SECAO_POR_RAMO.get(ramo_efetivo, ""),
				"eleito": "Não",
				"valor_contribuicao": 60.0 if categoria == "Beneficiário" else 0,
				"status_cobranca": "Ativo"
				if categoria == "Beneficiário" and status_grupo == "Ativo"
				else "Inativo",
				"inicio_do_pagamento": date(hoje.year, 1, 1) if categoria == "Beneficiário" else None,
				"email_cobranca": fake.email() if categoria == "Beneficiário" else "",
				"telefone_cobranca": fake_telefone() if categoria == "Beneficiário" else "",
			}
		)
		try:
			doc.insert(ignore_permissions=True)
			created += 1
			return doc.name
		except Exception as e:
			print(f"  ⚠️  Associado: {e}")
			return None

	for combo in combos:
		for _ in range(por_combinacao):
			nm = _create_one(*combo)
			if nm:
				names.append(nm)

	# extras: predominantemente beneficiários ativos válidos (cenário comum)
	for _ in range(extras):
		nm = _create_one("Válido", "Ativo", "Beneficiário")
		if nm:
			names.append(nm)

	print(f"  → {created} Associado (matriz {len(combos)} combinações x {por_combinacao} + {extras} extras)")
	return names


def seed_responsavel_vinculo(
	responsavel_names: list[str], associado_names: list[str], novo_associado_names: list[str]
):
	"""Cria vínculos entre responsáveis e beneficiários (associados E novos associados)."""
	if not responsavel_names:
		return
	created = 0
	# Vínculos com Associados
	pairs = list(zip(responsavel_names[:10], associado_names[:10], strict=False))
	for resp, assoc in pairs:
		# Idempotência: checar se o par já existe
		if frappe.db.exists(
			"Responsavel Vinculo",
			{"responsavel": resp, "beneficiario_associado": assoc},
		):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Responsavel Vinculo",
					"responsavel": resp,
					"beneficiario_associado": assoc,
					"é_guardiao_legal": 1,
					"primeiro_responsavel": 1,
					"tipo_guarda": random.choice(["Compartilhada", "Unilateral"]),
					"pais_divorciados": random.choice([0, 1]),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Responsavel Vinculo (assoc): {e}")
	# Vínculos com Novos Associados (cenário pré-cadastro)
	for resp, novo in list(zip(responsavel_names[10:15], novo_associado_names[:5], strict=False)):
		if frappe.db.exists(
			"Responsavel Vinculo",
			{"responsavel": resp, "beneficiario_novo_associado": novo},
		):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Responsavel Vinculo",
					"responsavel": resp,
					"beneficiario_novo_associado": novo,
					"é_guardiao_legal": 1,
					"primeiro_responsavel": 1,
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Responsavel Vinculo (novo): {e}")
	print(f"  → {created} Responsavel Vinculo")


# ===========================================================================
# Calendários e fluxo de recepção
# ===========================================================================


def seed_calendarios(n: int):
	created = 0
	for i in range(n):
		offset_days = random.randint(-180, 180)
		inicio = date.today() + timedelta(days=offset_days)
		safe_insert(
			{
				"doctype": "Calendario",
				"id": f"cal-{2025 + i // 12}-{(i % 12) + 1:02d}-{i:03d}",
				"atividade": random.choice(
					[
						"Reunião regular",
						"Acampamento",
						"Atividade externa",
						"Cerimônia de Promessa",
						"Reunião de pais",
					]
				),
				"inicio": f"{inicio} 14:00:00",
				"termino": f"{inicio} 18:00:00",
				"local": random.choice(["Sede", "Parque Municipal", "Acampamento Norte"]),
				"secao": random.choice(["Alcateia", "Tropa", "Clã"]),
				"nivel": random.choice(["Local", "Regional", "Nacional"]),
				"sem_atividade": 0,
				"abertura_geral": random.choice([0, 1]),
			}
		)
		created += 1
	print(f"  → {created} Calendario")


def seed_calendarios_simulados(n: int):
	created = 0
	for i in range(n):
		offset = random.randint(0, 365)
		inicio = date.today() + timedelta(days=offset)
		safe_get_or_create(
			"Calendario Simulado",
			filters={"atividade": f"Simulação {i}"},
			defaults={
				"inicio": f"{inicio} 09:00:00",
				"termino": f"{inicio} 17:00:00",
				"secao": random.choice(["Alcateia", "Tropa"]),
				"local": "Sede",
				"nivel": "Local",
				"conciliado": 0,
				"sem_atividade": 0,
			},
		)
		created += 1
	print(f"  → {created} Calendario Simulado")


def seed_agenda_visitas(novo_associado_names: list[str], n: int):
	if not novo_associado_names:
		return
	created = 0
	for i in range(min(n, len(novo_associado_names))):
		jovem = novo_associado_names[i]
		if frappe.db.exists("Agenda de Visitas", {"jovem": jovem}):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Agenda de Visitas",
					"jovem": jovem,
					"data_da_visita": date.today() + timedelta(days=random.randint(-30, 30)),
					"visita_confirmada": random.choice([0, 1]),
					"ramo": random.choice(["Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"]),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Agenda de Visitas: {e}")
	print(f"  → {created} Agenda de Visitas")


def seed_fila_de_espera(novo_associado_names: list[str]):
	"""Move alguns Novos Associados para a fila de espera."""
	if not novo_associado_names:
		return
	created = 0
	for novo in novo_associado_names[:5]:
		if frappe.db.exists("Fila de Espera", {"associado": novo}):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Fila de Espera",
					"associado": novo,
					"ramo": random.choice(["Filhotes", "Lobinho", "Escoteiro"]),
					"dt_inclusao_fila": frappe.utils.now(),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Fila de Espera: {e}")
	print(f"  → {created} Fila de Espera")


def seed_pesquisa_novos_associados(responsavel_names: list[str], n: int):
	"""autoname = field:responsavel — então um por responsável."""
	if not responsavel_names:
		return
	created = 0
	nps_options = [str(i) for i in range(11)]
	for resp in responsavel_names[:n]:
		if frappe.db.exists("Pesqusa de Novos Associados", resp):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Pesqusa de Novos Associados",
					"responsavel": resp,
					"visao_sobre_movimento": fake.sentence(),
					"espera_encontrar_movimento": fake.sentence(),
					"chamou_atencao_uel": fake.sentence(),
					"nps_recepcao": random.choice(nps_options),
					"pontos_fortes_recepcao": fake.sentence(),
					"melhoria_recepcao": fake.sentence(),
					"data_resposta": date_range(meses_atras=6),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Pesqusa de Novos Associados: {e}")
	print(f"  → {created} Pesqusa de Novos Associados")


def seed_resposta_manifestacao_interesse(n: int):
	created = 0
	for _ in range(n):
		try:
			frappe.get_doc(
				{
					"doctype": "Resposta Manifestacao de Interesse",
					"nome_do_jovem": fake.name(),
					"data_de_nascimento_do_jovem": str(fake_data_nascimento_ramo("Lobinho")),
					"cpf_do_jovem": fake_cpf(),
					"nome_do_responsavel": fake.name(),
					"email_do_responsavel": fake.email(),
					"celular_do_responsavel": fake_telefone(),
					"cpf_do_responsavel": fake_cpf(),
					"data_e_horario_de_resposta": frappe.utils.now(),
					"dados_confirmados": random.choice([0, 1]),
					"aceite_lgpd": 1,
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Resposta Manifestacao: {e}")
	print(f"  → {created} Resposta Manifestacao de Interesse")


# ===========================================================================
# Logs / Métricas / Transparência
# ===========================================================================


def seed_log_importacao(n: int):
	created = 0
	for _ in range(n):
		total = random.randint(10, 200)
		erros = random.randint(0, total // 10)
		try:
			frappe.get_doc(
				{
					"doctype": "Log Importacao de Associados",
					"data_importacao": frappe.utils.now(),
					"arquivo_origem": f"associados_{random.randint(1, 100)}.csv",
					"sucesso": 1 if erros == 0 else 0,
					"total_registros": total,
					"registros_criados": total - erros - 5,
					"registros_atualizados": 5,
					"registros_sem_alteracao": 0,
					"total_erros": erros,
					"detalhes_resultado": f"Importação processou {total} registros.",
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Log Importacao: {e}")
	print(f"  → {created} Log Importacao de Associados")


def seed_metrica_mensal(n: int):
	created = 0
	for i in range(n):
		mes = first_of_month(-i)
		if frappe.db.exists("Metrica Mensal de Associados", {"mes_referencia": mes}):
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "Metrica Mensal de Associados",
					"mes_referencia": mes,
					"qt_ativos_uel": random.randint(40, 120),
					"qt_evasao": random.randint(0, 5),
					"qt_novos": random.randint(0, 8),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Metrica Mensal: {e}")
	print(f"  → {created} Metrica Mensal de Associados")


def seed_transparencia(n: int):
	"""Documentos de transparência. Como `arquivo` é Attach reqd, geramos URL stub."""
	created = 0
	tipos = [
		"Parecer trimestral da comissão fiscal",
		"Parecer anual da comissão fiscal",
	]
	for i in range(n):
		try:
			frappe.get_doc(
				{
					"doctype": "Transparencia",
					"tipo_arquivo": tipos[i % len(tipos)],
					"arquivo": "/files/stub.pdf",
					"ano_referencia": 2024 + i % 3,
					"data_de_atualização": date.today(),
					"publicado": 1,
					"title": f"Documento de Transparência {i + 1}",
					"trimestre_referencia": str((i % 4) + 1),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Transparencia: {e}")
	print(f"  → {created} Transparencia")


# ===========================================================================
# Singles do módulo Gris (configurações)
# ===========================================================================


def seed_singles_gris(creds: dict):
	# Configuracoes LLM
	cfg = get(creds, "gris", "configuracoes_llm", default={}) or {}
	if cfg.get("api_key"):
		set_single(
			"Configuracoes LLM", {"api_key": cfg["api_key"], "modelo": cfg.get("modelo") or "gpt-4o-mini"}
		)
		print("  → Configuracoes LLM atualizado")

	# Configuracoes WhatsApp
	cfg = get(creds, "gris", "configuracoes_whatsapp", default={}) or {}
	if cfg.get("api_key") and cfg.get("url_api"):
		try:
			payload = {
				"habilitar_integracao": 0,  # safe default em seed
				"url_api": cfg.get("url_api") or "https://exemplo.evolution.api",
				"api_key": cfg["api_key"],
				"nome_instancia": cfg.get("nome_instancia") or "gris-dev",
			}
			telefone_contato = (cfg.get("telefone_contato") or "").strip()
			if telefone_contato:
				payload["telefone_contato"] = telefone_contato
			set_single("Configuracoes WhatsApp", payload)
			print("  → Configuracoes WhatsApp atualizado")
		except Exception as e:
			print(f"  ⚠️  Configuracoes WhatsApp: {e}")

	# Configuracoes Backup Google Drive
	cfg = get(creds, "gris", "configuracoes_backup_google_drive", default={}) or {}
	if cfg.get("service_account_json") or cfg.get("backup_folder_id"):
		try:
			set_single(
				"Configuracoes Backup Google Drive",
				{
					"enable_backup": int(cfg.get("enabled", 0)),
					"shared_drive_id": cfg.get("shared_drive_id") or "",
					"backup_folder_id": cfg.get("pasta_destino_id") or "stub-folder-id",
					"service_account_json": cfg.get("service_account_json") or "{}",
					"retention_days": int(cfg.get("retention_days", 30)),
					"include_public_files": 1,
					"include_private_files": 0,
					"notification_email": cfg.get("notification_email") or "",
					"notify_on_success": 0,
				},
			)
			print("  → Configuracoes Backup Google Drive atualizado")
		except Exception as e:
			print(f"  ⚠️  Configuracoes Backup Google Drive: {e}")

	# Configuracoes Google Workspace (depende de drives_compartilhados table — pula se vazio)
	cfg = get(creds, "gris", "configuracoes_google_workspace", default={}) or {}
	if cfg.get("service_account_json"):
		try:
			set_single(
				"Configuracoes Google Workspace",
				{
					"habilitar_integracao": 0,
					"dominio_institucional": cfg.get("domain") or "example.com",
					"dias_expiracao_acesso_restrito": 90,
					"service_account_json": cfg["service_account_json"],
				},
			)
			print("  → Configuracoes Google Workspace atualizado")
		except Exception as e:
			print(f"  ⚠️  Configuracoes Google Workspace: {e}")

	# Configuracoes de Feriados
	cfg = get(creds, "gris", "configuracoes_feriados", default={}) or {}
	set_single(
		"Configuracoes de Feriados",
		{
			"feriadosapi_key": cfg.get("feriadosapi_key") or "stub-key",
			"codigo_municipio_ibge": "3550308",  # São Paulo
		},
	)
	print("  → Configuracoes de Feriados atualizado")

	# Configuracoes de Associados
	resp = first_name("Associado", {"categoria": "Dirigente"})
	values = {"criar_usuarios": 0}
	if resp:
		values["responsavel_atualizacao"] = resp
	set_single("Configuracoes de Associados", values)
	print("  → Configuracoes de Associados atualizado")

	# Configuracoes de Projetos
	set_single(
		"Configuracoes de Projetos",
		{"habilitar_pastas_projetos_drive": 0, "pasta_projetos_id": "stub-projetos"},
	)
	print("  → Configuracoes de Projetos atualizado")

	# Configuracoes de Recepcao (vários inteiros)
	set_single(
		"Configuracoes de Recepcao",
		{
			"dados_para_registro_enviados": 7,
			"registro_criado_no_paxtu": 14,
			"pesquisa_de_novos_associados_respondida": 30,
			"registro_definitivo_efetivado": 14,
			"ficha_medica_preenchida": 14,
			"id_escoteiros_criado": 7,
			"boleto_definitivo_gerado": 3,
			"boleto_provisorio_gerado": 3,
			"intervalo_provisorio_definitivo": 60,
			"registro_provisorio_efetivado": 7,
			"reuniao_de_acolhida_realizada": 14,
			"valor_registro_provisorio": 50.0,
			"valor_registro_definitivo": 150.0,
			"valor_carteirinha": 25.0,
			"dias_aviso_seguimento_provisorio": 20,
		},
	)
	print("  → Configuracoes de Recepcao atualizado")

	# Definicao da UEL
	set_single(
		"Definicao da UEL",
		{
			"nome_da_uel": "Grupo Escoteiro Professora Inah de Mello",
			"numeral": 47,
			"cnpj": fake.cnpj(),
			"rua": "Rua Exemplo",
			"numero": "100",
			"bairro": "Centro",
			"cep": fake_cep(),
			"tipo_uel": "Grupo Escoteiro",
			"regiao": "SP",
			"telefone": fake_telefone(),
			"site": "https://exemplo.org.br",
			"dia_de_atividade": "Sábado",
			"horário_de_início": "14:00:00",
			"horário_de_término": "18:00:00",
		},
	)
	print("  → Definicao da UEL atualizado")

	# Vagas
	set_single(
		"Vagas",
		{
			"limite_de_vagas_filhotes": 12,
			"idade_minima_filhotes": 5,
			"idade_maxima_filhotes": 6,
			"idade_transicao_filhotes": 6.5,
			"limite_de_vagas_lobinho": 24,
			"idade_minima_lobinho": 7,
			"idade_maxima_lobinho": 10,
			"idade_transicao_lobinho": 10.5,
			"limite_de_vagas_escoteiro": 32,
			"idade_minima_escoteiro": 11,
			"idade_maxima_escoteiro": 14,
			"idade_transicao_escoteiro": 14.5,
			"limite_de_vagas_senior": 24,
			"idade_minima_senior": 15,
			"idade_maxima_senior": 17,
			"idade_transicao_senior": 17.5,
			"limite_de_vagas_pioneiro": 16,
			"idade_minima_pioneiro": 18,
			"idade_maxima_pioneiro": 21,
			"idade_transicao_pioneiro": 21.5,
		},
	)
	print("  → Vagas atualizado")


# ===========================================================================
# Orquestrador do módulo Gris
# ===========================================================================


def seed_gris_core(creds: dict, n: dict) -> dict:
	"""
	Popula o módulo Gris.

	Retorna um dict com nomes criados (responsavel_names, associado_names, novo_associado_names)
	para uso por outros módulos.
	"""
	print("[gris_core]")
	seed_habilidades(n["habilidade"])
	seed_unidades_organizacionais()
	seed_funcoes_voluntario(n["funcao_voluntario"])
	seed_feriados(n["feriados"])

	responsavel_names = seed_responsaveis(n["responsavel"])
	novo_associado_names = seed_novos_associados(n["novo_associado_por_ramo"])
	associado_names = seed_associados(n["associado_por_combinacao"], n["associado_extras"])

	# Mesmo caminho da importação do Paxtu: as seções viram áreas aqui.
	from gris.api.gestao_adultos.secoes import sincronizar_secoes

	sincronizar_secoes()
	seed_responsaveis_de_area(associado_names)
	seed_responsavel_vinculo(responsavel_names, associado_names, novo_associado_names)
	seed_calendarios(n["calendario"])
	seed_calendarios_simulados(n["calendario_simulado"])
	seed_agenda_visitas(novo_associado_names, n["agenda_visitas"])
	seed_fila_de_espera(novo_associado_names)
	seed_pesquisa_novos_associados(responsavel_names, n["pesquisa_novos_associados"])
	seed_resposta_manifestacao_interesse(n["resposta_manifestacao_interesse"])
	seed_log_importacao(n["log_importacao"])
	seed_metrica_mensal(n["metrica_mensal"])
	seed_transparencia(n["transparencia"])

	seed_singles_gris(creds)

	return {
		"responsavel_names": responsavel_names,
		"associado_names": associado_names,
		"novo_associado_names": novo_associado_names,
	}
