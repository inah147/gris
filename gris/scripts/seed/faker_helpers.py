"""Helpers de geração de dados falsos com Faker pt_BR (seed fixo p/ reprodutibilidade)."""

import hashlib
import random
import re
from datetime import date, timedelta

from faker import Faker

# Instância única — seed fixo garante que a mesma execução produz os mesmos dados.
# Para variar, mude SEED ou chame fake.seed_instance(novo_seed) externamente.
SEED = 42
fake = Faker("pt_BR")
fake.seed_instance(SEED)
Faker.seed(SEED)
random.seed(SEED)


def reset_seed(seed: int = SEED):
	"""Reseta toda a randomicidade ao seed fixo. Idempotência entre execuções."""
	fake.seed_instance(seed)
	Faker.seed(seed)
	random.seed(seed)


# Mapeamento idade -> ramo escoteiro (referência: limites do DocType Vagas)
RAMO_FAIXAS = [
	("Filhotes", 5, 6),
	("Lobinho", 7, 10),
	("Escoteiro", 11, 14),
	("Sênior", 15, 17),
	("Pioneiro", 18, 21),
]


def fake_cpf() -> str:
	"""CPF formatado pelo Faker pt_BR (já válido)."""
	return fake.cpf()


def cpf_hash(cpf: str) -> str:
	"""Hash MD5 do CPF — replica padrão usado em Associado/Novo Associado/Responsavel."""
	cpf_clean = re.sub(r"\D", "", cpf or "")
	return hashlib.md5(cpf_clean.encode("utf-8")).hexdigest()


def fake_telefone() -> str:
	"""Celular brasileiro no formato +55 (XX) 9XXXX-XXXX."""
	ddd = random.choice(["11", "21", "31", "41", "47", "51", "61", "71", "81"])
	num = fake.numerify("9####-####")
	return f"+55 ({ddd}) {num}"


def fake_cep() -> str:
	return fake.postcode()


def fake_data_nascimento_para_idade(idade: int) -> date:
	"""Gera data de nascimento aleatória que resulta em ~`idade` anos hoje."""
	hoje = date.today()
	ano_nasc = hoje.year - idade
	# escolhe dia/mês aleatório, garantindo idade exata
	mes = random.randint(1, 12)
	# evita Feb-29; usa dia 1-28 pra simplicidade
	dia = random.randint(1, 28)
	return date(ano_nasc, mes, dia)


def fake_data_nascimento_ramo(ramo: str) -> date:
	"""Data de nascimento aleatória dentro da faixa etária do ramo."""
	for nome, idade_min, idade_max in RAMO_FAIXAS:
		if nome == ramo:
			idade = random.randint(idade_min, idade_max)
			return fake_data_nascimento_para_idade(idade)
	# fallback: adulto
	return fake_data_nascimento_para_idade(random.randint(25, 50))


def fake_data_nascimento_adulto() -> date:
	return fake_data_nascimento_para_idade(random.randint(22, 60))


def random_choice(opts):
	return random.choice(opts)


def random_weighted(opts_weights: dict):
	"""Sorteia chave do dict {opcao: peso}."""
	keys = list(opts_weights.keys())
	weights = list(opts_weights.values())
	return random.choices(keys, weights=weights, k=1)[0]


def date_range(meses_atras: int, meses_a_frente: int = 0) -> date:
	"""Data aleatória dentro do intervalo [hoje - meses_atras, hoje + meses_a_frente]."""
	hoje = date.today()
	dias_atras = meses_atras * 30
	dias_a_frente = meses_a_frente * 30
	delta = random.randint(-dias_atras, dias_a_frente) if dias_atras > 0 else random.randint(0, dias_a_frente)
	return hoje + timedelta(days=delta)


def first_of_month(months_offset: int) -> date:
	"""Primeiro dia do mês com offset (negativo = passado, positivo = futuro)."""
	hoje = date.today()
	ano = hoje.year
	mes = hoje.month + months_offset
	while mes <= 0:
		mes += 12
		ano -= 1
	while mes > 12:
		mes -= 12
		ano += 1
	return date(ano, mes, 1)
