"""Seed do módulo Gestão de Adultos (Entrevista por Competências)."""

import random

import frappe

from ..faker_helpers import fake


def seed_entrevistas(n: int):
	"""
	Cria entrevistas vinculadas a Associados Dirigentes/Escotistas.

	Os campos q_ce_*, q_di_*, q_es_* têm opções dinâmicas vindas do fixture
	"Mapeamento de perguntas e respostas da entrevista". Usamos respostas
	desse mapeamento como valores válidos.
	"""
	# Pega respostas válidas do mapeamento (fixture). Se vazio, usa stubs.
	respostas = frappe.get_all(
		"Mapeamento de perguntas e respostas da entrevista",
		fields=["resposta"],
		limit=20,
		pluck="resposta",
	)
	respostas = [r for r in respostas if r] or [
		"Gosta de trabalhar com educação de jovens e crianças",
		"Quer fazer algo para melhorar a comunidade",
		"Tem afinidade com o método escoteiro",
	]

	# Candidatos: associados não-beneficiários ativos
	candidatos = frappe.get_all(
		"Associado",
		filters={
			"status_no_grupo": "Ativo",
			"categoria": ["in", ["Dirigente", "Escotista", "Colaboradores"]],
		},
		limit=n,
		pluck="name",
	)
	if not candidatos:
		# fallback: qualquer ativo
		candidatos = frappe.get_all("Associado", filters={"status_no_grupo": "Ativo"}, limit=n, pluck="name")
	if not candidatos:
		print("  → 0 Entrevista por Competencias (sem associados)")
		return

	created = 0
	for assoc in candidatos[:n]:
		# Idempotência: 1 entrevista por associado neste seed
		if frappe.db.exists("Entrevista por Competencias", {"associado": assoc}):
			continue
		# Monta payload com respostas aleatórias para cada bloco
		payload = {
			"doctype": "Entrevista por Competencias",
			"associado": assoc,
			"funcao_atual": fake.job()[:30],
			"profissao": fake.job()[:30],
			"formacao": random.choice(["Ensino superior completo", "Especialização completa"]),
			"hobbies_e_interesses": fake.sentence(),
			"motivo_da_entrevista": random.choice(
				["Ingresso", "Retorno", "Permanência", "Alteração de função"]
			),
			"resumo": fake.paragraph(),
			"observacoes": fake.sentence(),
			"data_da_ultima_atualizacao": frappe.utils.now(),
			"alertas": [
				{
					"pergunta": "Existe alguma situação que mereça atenção?",
					"resposta": fake.sentence(),
					"motivo_do_alerta": "Resposta inconsistente",
				}
			],
		}
		# Preenche q_* com respostas aleatórias (Select sem options aceita qualquer valor)
		for prefix, count in [("q_ce_", 5), ("q_di_", 8), ("q_es_", 11)]:
			for i in range(1, count + 1):
				payload[f"{prefix}{i}"] = random.choice(respostas)
				payload[f"obs_{prefix}{i}"] = fake.sentence() if random.random() < 0.3 else ""

		# Pontuações são calculadas pelo controller? Setamos valores razoáveis.
		payload.update(
			{
				"pontuacao_dirigente_administrativo_financeiro": random.randint(0, 50),
				"pontuacao_dirigente_gestao_institucional": random.randint(0, 50),
				"pontuacao_dirigente_metodos_educativos": random.randint(0, 50),
				"pontuacao_ramo_lobinho": random.randint(0, 30),
				"pontuacao_ramo_escoteiro": random.randint(0, 30),
				"pontuacao_ramo_senior": random.randint(0, 30),
				"pontuacao_ramo_pioneiro": random.randint(0, 30),
			}
		)

		try:
			frappe.get_doc(payload).insert(ignore_permissions=True)
			created += 1
		except Exception as e:
			print(f"  ⚠️  Entrevista por Competencias (associado={assoc}): {e}")
	print(f"  → {created} Entrevista por Competencias")


def seed_adultos(_creds: dict, n: dict):
	print("[adultos]")
	seed_entrevistas(n["entrevista"])
