"""Seed do módulo Gestão de Projetos (cobre os 6 status do ciclo de Projeto)."""

import random
from datetime import date, timedelta

import frappe

from ..faker_helpers import fake, fake_telefone
from ..safe_insert import all_names

PROJETO_STATUSES = [
	"Rascunho",
	"Em aprovacao",
	"Aprovado",
	"Em execucao",
	"Concluido",
	"Cancelado",
]

TAREFA_STATUSES = ["Nao iniciado", "Em andamento", "Atrasado", "Concluido", "Cancelado"]


def _build_projeto_data(status: str, idx: int) -> dict:
	"""Monta payload de Projeto para um status, com child tables consistentes."""
	# Coordenador: associado ativo válido beneficiário não funciona — coordenador deve ser dirigente/escotista geralmente.
	# Usamos o primeiro associado disponível como coordenador.
	associados = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo"},
		limit=10,
		pluck="name",
	)
	if not associados:
		return None
	coord = associados[0]

	# ODS Projeto (fixture)
	ods_disponiveis = all_names("ODS Projeto", limit=5)

	hoje = date.today()

	# Envolvidos: coordenador (Associado) + 1-2 outros associados
	envolvidos = [
		{
			"tipo_pessoa": "Associado",
			"associado": coord,
			"nome": frappe.db.get_value("Associado", coord, "nome_completo") or "Coordenador",
			"email": frappe.db.get_value("Associado", coord, "email") or "coord@example.org",
			"telefone": frappe.db.get_value("Associado", coord, "telefone") or fake_telefone(),
			"funcao": "Coordenador(a)",
			"coordenador": 1,
			"padrinho_orientador": 0,
			"aprovador": 0,
			"permite_remover": 0,
			"participa_avaliacao": 1,
		}
	]
	for outro in associados[1:3]:
		envolvidos.append(
			{
				"tipo_pessoa": "Associado",
				"associado": outro,
				"nome": frappe.db.get_value("Associado", outro, "nome_completo") or fake.name(),
				"email": frappe.db.get_value("Associado", outro, "email") or fake.email(),
				"telefone": frappe.db.get_value("Associado", outro, "telefone") or fake_telefone(),
				"funcao": "Membro da equipe",
				"coordenador": 0,
				"padrinho_orientador": 0,
				"aprovador": 0,
				"permite_remover": 1,
				"participa_avaliacao": 1,
			}
		)

	# ODS table (Table MultiSelect)
	ods_rows = (
		[{"ods": ods_disponiveis[0]}] if ods_disponiveis else []
	)

	objetivos = [
		{
			"objetivo": fake.sentence(nb_words=8),
			"metrica_de_sucesso": fake.sentence(nb_words=6),
		}
		for _ in range(2)
	]

	cronograma = [
		{
			"data_inicio": hoje,
			"data_termino": hoje + timedelta(days=15),
			"tarefa": "Planejamento",
		},
		{
			"data_inicio": hoje + timedelta(days=16),
			"data_termino": hoje + timedelta(days=45),
			"tarefa": "Execução",
		},
	]

	recursos = [{"recurso": r} for r in ["Material de campo", "Transporte", "Alimentação"]]
	riscos = [
		{"risco": "Chuva no dia da atividade", "mitigacao": "Plano B coberto"},
		{"risco": "Baixa adesão", "mitigacao": "Comunicação antecipada"},
	]
	reunioes = [
		{
			"data_hora": frappe.utils.now(),
			"descricao": "Reunião de alinhamento inicial",
			"pauta": "Definir escopo e responsáveis",
			"ata": "Equipe alinhada com cronograma",
		}
	]
	# Comentários revisão só fazem sentido se o projeto passou por aprovação
	comentarios = []
	if status in {"Em aprovacao", "Aprovado", "Em execucao", "Concluido"}:
		comentarios.append(
			{
				"aprovador": "Diretor Presidente",
				"aprovador_tipo": "Associado",
				"aprovador_associado": coord,
				"aprovador_email": fake.email(),
				"data_da_revisao": frappe.utils.now(),
				"etapa_aprovacao": "Aprovacao inicial",
				"tipo_revisao": "Aprovacao",
				"comentarios": fake.sentence(),
				"resolvido": 1,
			}
		)

	return {
		"doctype": "Projeto",
		"nome_do_projeto": f"[Seed] Projeto {status} #{idx}",
		"coordenador": coord,
		"status": status,
		"data_de_inicio": hoje,
		"data_de_termino": hoje + timedelta(days=60),
		"tipo_padrinho_ou_orientador": "Associado",
		"padrinho_associado": associados[1] if len(associados) > 1 else None,
		"justificativa": fake.paragraph(),
		"alinhamento_com_escotismo": fake.paragraph(),
		"competencias": "Trabalho em equipe, Resolução de problemas",
		"especialidade": "Acampamento, Pioneiria",
		"observacoes_e_comentarios": "",
		"reunioes": reunioes,
		"envolvidos": envolvidos,
		"objetivos": objetivos,
		"ods": ods_rows,
		"cronograma": cronograma,
		"recursos": recursos,
		"riscos": riscos,
		"comentarios_revisao_aprovacao": comentarios,
	}


def _seed_tarefas_para_projeto(projeto_name: str) -> int:
	"""Semeia tarefas independentes (Gestao de Tarefas) no board do projeto."""
	board_name = frappe.db.get_value("Projeto", projeto_name, "board_tarefas")
	if not board_name:
		return 0

	hoje = date.today()
	created = 0
	for i, ts in enumerate(TAREFA_STATUSES[:3]):
		try:
			frappe.get_doc(
				{
					"doctype": "Gestao de Tarefas",
					"board": board_name,
					"data_inicio": hoje + timedelta(days=i * 5),
					"prazo": hoje + timedelta(days=i * 5 + 10),
					"data_entrega": hoje + timedelta(days=i * 5 + 8) if ts == "Concluido" else None,
					"descricao": fake.sentence(),
					"responsavel": "",
					"status": ts,
					"observacoes": "",
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"    ⚠️  Tarefa do projeto {projeto_name}: {e}")
	return created


def seed_projetos(por_status: int) -> dict[str, list[str]]:
	"""Cria `por_status` projetos para CADA um dos 6 status. Retorna dict {status: [names]}."""
	created = 0
	tarefas_created = 0
	by_status: dict[str, list[str]] = {}
	for status in PROJETO_STATUSES:
		by_status[status] = []
		for i in range(por_status):
			data = _build_projeto_data(status, i)
			if not data:
				continue
			# Idempotência: pelo nome_do_projeto
			existing = frappe.db.exists("Projeto", {"nome_do_projeto": data["nome_do_projeto"]})
			if existing:
				by_status[status].append(existing)
				tarefas_created += _seed_tarefas_para_projeto(existing)
				continue
			try:
				doc = frappe.get_doc(data)
				doc.flags.ignore_validate = False
				# Suprimir enfileiramento de criação de pasta no Drive durante seed
				doc.flags.skip_drive_folder_creation = True
				doc.insert(ignore_permissions=True)
				by_status[status].append(doc.name)
				created += 1
				tarefas_created += _seed_tarefas_para_projeto(doc.name)
			except Exception as e:
				print(f"  ⚠️  Projeto status={status}: {e}")
	print(f"  → {created} Projeto (x {len(PROJETO_STATUSES)} status) + {tarefas_created} tarefas")
	return by_status


def seed_avaliacao_projeto(projetos_concluidos: list[str]):
	"""Cria avaliação completa para projetos concluídos."""
	created = 0
	for projeto_name in projetos_concluidos:
		if frappe.db.exists("Avaliacao de Projeto", {"projeto": projeto_name}):
			continue
		# Avaliador deve ser o `nome` de um envolvido com participa_avaliacao=1
		envolvidos = frappe.get_all(
			"Envolvido no Projeto",
			filters={"parent": projeto_name, "participa_avaliacao": 1},
			fields=["nome", "email"],
			order_by="idx asc",
		)
		if not envolvidos:
			print(f"  ⚠️  Projeto {projeto_name} sem envolvidos para avaliação — pulando")
			continue
		coord_envolvido = envolvidos[0]
		try:
			frappe.get_doc(
				{
					"doctype": "Avaliacao de Projeto",
					"projeto": projeto_name,
					"status": "Concluida",
					"avaliacoes_individuais": [
						{
							"avaliador": coord_envolvido["nome"],
							"email": coord_envolvido.get("email") or fake.email(),
							"token": frappe.generate_hash(length=20),
							"resultado_projeto": str(random.randint(7, 10)),
							"satisfacao_colaboracao": str(random.randint(7, 10)),
							"objetivos_atingidos": fake.sentence(),
							"muito_bom": fake.sentence(),
							"pontos_melhoria": fake.sentence(),
							"avaliacao_concluida": 1,
						}
					],
					"avaliacao_geral": round(random.uniform(7, 10), 1),
					"satisfacao_dos_participantes": round(random.uniform(7, 10), 1),
					"objetivos_atingidos": [
						{
							"objetivo": "Promover trabalho em equipe",
							"objetivo_atingido": "Completamente",
						},
						{
							"objetivo": "Desenvolver liderança",
							"objetivo_atingido": "Parcialmente",
							"porque_nao_foi_atingido": "Tempo limitado",
						},
					],
					"o_que_funcionou_bem_na_dinamica_da_equipe": fake.paragraph(),
					"o_que_nao_funcionou_na_dinamica_da_equipe": fake.paragraph(),
					"maior_aprendizado_gerado": fake.paragraph(),
					"impacto_gerado_para_comunidade": fake.paragraph(),
				}
			).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Avaliacao de Projeto: {e}")
	print(f"  → {created} Avaliacao de Projeto")


def seed_projetos_modulo(_creds: dict, n: dict):
	print("[projetos]")
	by_status = seed_projetos(n["projeto_por_status"])
	seed_avaliacao_projeto(by_status.get("Concluido", []))
