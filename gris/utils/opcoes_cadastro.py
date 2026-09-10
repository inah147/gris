# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Listas de opções dos campos cadastrais, na ordem e na grafia do Paxtu.

O registro do associado é transcrito à mão do GRIS para o Paxtu. Quando uma lista daqui
diverge da de lá — na ordem, na grafia ou nos itens — quem transcreve precisa reescrever o
valor em vez de copiá-lo, e o texto livre vira ``coisa aleatória`` que não casa com nenhuma
opção do outro sistema.

Por isso as listas vivem aqui e não espalhadas pelos JSON dos DocTypes: ``Novo Associado`` e
``Responsavel`` guardam os mesmos conceitos e já divergiram entre si (``Nâo desejo informar``
com circunflexo num, ``Não`` no outro; ``Especialização`` em ordem trocada). O teste
``gris/tests/test_opcoes_cadastro.py`` reprova quando um JSON sai de sincronia com este
módulo — é ele que impede a divergência voltar.
"""

from __future__ import annotations

from gris.utils.phone_countries import get_phone_countries

# --------------------------------------------------------------------------------------
# Informações pessoais
# --------------------------------------------------------------------------------------

ETNIA = [
	"Amarela",
	"Branca",
	"Indígena",
	"Parda",
	"Preta",
	"Não desejo informar",
]

SEXO = ["Feminino", "Masculino"]

ESTADO_CIVIL = [
	"Não informado",
	"Solteiro(a)",
	"Casado(a)",
	"Divorciado(a)",
	"Viúvo(a)",
]

RELIGIAO = [
	"Não desejo informar",
	"Anglicana",
	"Afro-Brasileira",
	"Budismo",
	"Católica",
	"Espírita",
	"Espiritualista",
	"Evangélico/Pentecostal",
	"Hinduismo",
	"Islâmica",
	"Judaísmo",
	"Messiânica",
	"Mórmom (Jesus Cristo dos Santos dos Últimos Dias)",
	"Protestante",
	"Testemunha de Jeová",
	"Tradições Esotéricas",
	"Tradições Indígenas",
	"Xintoísmo",
	"Sem Religião",
]

# O Paxtu tem "Denominação" ao lado de "Religião", para a vertente dentro da religião
# declarada. A lista completa ainda não foi transcrita do Paxtu (o print do documento da
# Fernanda mostra o campo fechado); até lá o campo aceita as vertentes mais comuns e
# "Outra", que cobre o resto sem obrigar texto livre.
DENOMINACAO = [
	"Não se aplica",
	"Não desejo informar",
	"Assembleia de Deus",
	"Batista",
	"Congregação Cristã no Brasil",
	"Universal do Reino de Deus",
	"Luterana",
	"Metodista",
	"Presbiteriana",
	"Adventista do Sétimo Dia",
	"Outra",
]

# --------------------------------------------------------------------------------------
# Informações profissionais e acadêmicas
# --------------------------------------------------------------------------------------

# Ordem do Paxtu: "Não Informado" abre a lista, e "Especialização incompleta" vem antes de
# "completa" (o GRIS tinha as duas invertidas).
ESCOLARIDADE = [
	"Não Informado",
	"Ensino fundamental incompleto",
	"Ensino fundamental completo",
	"Ensino médio incompleto",
	"Ensino médio completo",
	"Ensino superior incompleto",
	"Ensino superior completo",
	"Especialização incompleta",
	"Especialização completa",
	"Mestrado incompleto",
	"Mestrado completo",
	"Doutorado incompleto",
	"Doutorado completo",
	"Pós doutorado incompleto",
	"Pós doutorado completo",
]

# A profissão é oferecida como lista fechada no formulário, mas continua ``Data`` no schema:
# a lista abaixo ainda está incompleta (o print do Paxtu corta em "Administrador(a)"), e um
# ``Select`` recusaria tanto uma profissão que existe no Paxtu e falta aqui quanto os cadastros
# antigos, gravados como texto livre. Quando a lista estiver completa, ela pode virar Select —
# junto de um patch que converta o que já está gravado.
#
# As duas entradas entre asteriscos ficam fixas no topo do seletor do Paxtu, fora da ordem
# alfabética — é assim que ele as exibe, e a transcrição precisa bater caractere a caractere.
PROFISSAO_DESTAQUE = [
	"* Estudante *",
	"* Outras Profissões *",
]

# Ordem alfabética, como no Paxtu. Lista parcial: o print do documento corta em
# "Administrador(a)". Completar a partir do seletor do Paxtu — "* Outras Profissões *"
# cobre o que ainda faltar aqui.
PROFISSAO_ALFABETICA = [
	"Açougueiro(a)",
	"Administrador(a)",
	"Advogado(a)",
	"Agricultor(a)",
	"Agrônomo(a)",
	"Analista de Sistemas",
	"Arquiteto(a)",
	"Artesão/Artesã",
	"Assistente Social",
	"Atendente",
	"Auxiliar Administrativo",
	"Bibliotecário(a)",
	"Biólogo(a)",
	"Bombeiro(a)",
	"Cabeleireiro(a)",
	"Comerciante",
	"Contador(a)",
	"Cozinheiro(a)",
	"Dentista",
	"Designer",
	"Economista",
	"Educador(a) Físico(a)",
	"Eletricista",
	"Empresário(a)",
	"Enfermeiro(a)",
	"Engenheiro(a)",
	"Farmacêutico(a)",
	"Fisioterapeuta",
	"Fotógrafo(a)",
	"Funcionário(a) Público(a)",
	"Jornalista",
	"Marceneiro(a)",
	"Mecânico(a)",
	"Médico(a)",
	"Motorista",
	"Nutricionista",
	"Pedagogo(a)",
	"Pedreiro(a)",
	"Professor(a)",
	"Programador(a)",
	"Psicólogo(a)",
	"Publicitário(a)",
	"Recepcionista",
	"Representante Comercial",
	"Secretário(a)",
	"Segurança",
	"Técnico(a) em Enfermagem",
	"Técnico(a) em Informática",
	"Vendedor(a)",
	"Veterinário(a)",
	"Vigilante",
	"Do lar",
	"Aposentado(a)",
	"Desempregado(a)",
]

PROFISSAO = PROFISSAO_DESTAQUE + PROFISSAO_ALFABETICA

# --------------------------------------------------------------------------------------
# Unidades da federação
# --------------------------------------------------------------------------------------

# (sigla, nome por extenso). A sigla é o valor gravado — é como o cadastro sempre guardou —
# e o nome por extenso é o rótulo, porque é assim que o Paxtu exibe o campo.
UF: list[tuple[str, str]] = [
	("AC", "Acre"),
	("AL", "Alagoas"),
	("AP", "Amapá"),
	("AM", "Amazonas"),
	("BA", "Bahia"),
	("CE", "Ceará"),
	("DF", "Distrito Federal"),
	("ES", "Espírito Santo"),
	("GO", "Goiás"),
	("MA", "Maranhão"),
	("MT", "Mato Grosso"),
	("MS", "Mato Grosso do Sul"),
	("MG", "Minas Gerais"),
	("PA", "Pará"),
	("PB", "Paraíba"),
	("PR", "Paraná"),
	("PE", "Pernambuco"),
	("PI", "Piauí"),
	("RJ", "Rio de Janeiro"),
	("RN", "Rio Grande do Norte"),
	("RS", "Rio Grande do Sul"),
	("RO", "Rondônia"),
	("RR", "Roraima"),
	("SC", "Santa Catarina"),
	("SP", "São Paulo"),
	("SE", "Sergipe"),
	("TO", "Tocantins"),
]

UF_SIGLAS = [sigla for sigla, _nome in UF]

# --------------------------------------------------------------------------------------
# Grafias antigas, para o patch de normalização
# --------------------------------------------------------------------------------------

# Valor gravado antes desta padronização -> valor canônico. Usado por
# ``gris.patches.normalizar_opcoes_cadastro``; o que não estiver aqui e não casar com
# nenhuma opção é registrado em log, nunca apagado.
GRAFIAS_ANTIGAS: dict[str, dict[str, str]] = {
	"etnia": {"Nâo desejo informar": "Não desejo informar"},
	"religiao": {"Evangélico/Petencostal": "Evangélico/Pentecostal"},
}

# Campos ``Select`` cujo ``options`` este módulo governa, por DocType. O teste de sincronia
# percorre exatamente estes pares — o que não está aqui (``sexo``, ``status``, ``ramo``) segue
# vivendo só no JSON, porque não é campo transcrito para o Paxtu.
# ``Responsavel.profissão`` tem o fieldname acentuado; é assim no schema desde a criação.
CAMPOS_SELECT_POR_DOCTYPE: dict[str, dict[str, list[str]]] = {
	"Novo Associado": {
		"etnia": ETNIA,
		"estado_civil": ESTADO_CIVIL,
		"religiao": RELIGIAO,
		"denominacao": DENOMINACAO,
		"escolaridade": ESCOLARIDADE,
		"uf_de_nascimento": UF_SIGLAS,
		"estado": UF_SIGLAS,
	},
	"Responsavel": {
		"estado_civil": ESTADO_CIVIL,
		"escolaridade": ESCOLARIDADE,
		"uf_de_nascimento": UF_SIGLAS,
		"estado": UF_SIGLAS,
	},
}

# Campo (sem acento, como o formulário o chama) -> lista canônica, para o patch de grafias.
LISTAS_POR_CAMPO: dict[str, list[str]] = {
	"etnia": ETNIA,
	"sexo": SEXO,
	"estado_civil": ESTADO_CIVIL,
	"religiao": RELIGIAO,
	"denominacao": DENOMINACAO,
	"escolaridade": ESCOLARIDADE,
	"profissao": PROFISSAO,
	"uf_de_nascimento": UF_SIGLAS,
	"estado": UF_SIGLAS,
}


def opcoes_do_doctype(valores: list[str]) -> str:
	"""Valor do atributo ``options`` de um Select, como o JSON do DocType espera.

	A opção vazia inicial é o que faz o Frappe deixar o campo em branco em vez de já escolher o
	primeiro item por conta própria — o Paxtu abre todos esses campos em "Selecione", e um
	valor escolhido sem querer é justamente o erro que este trabalho quer evitar.
	"""
	return "\n".join([""] + list(valores))


def itens_select(valores: list[str], placeholder: str = "Selecione...") -> list[dict]:
	"""Lista no formato ``[{"label", "value"}]`` que a macro ``select`` do design system usa."""
	itens = [{"label": placeholder, "value": ""}]
	itens.extend({"label": valor, "value": valor} for valor in valores)
	return itens


def itens_uf(placeholder: str = "Selecione...") -> list[dict]:
	"""UFs com o nome por extenso no rótulo e a sigla no valor."""
	itens = [{"label": placeholder, "value": ""}]
	itens.extend({"label": nome, "value": sigla} for sigla, nome in UF)
	return itens


def itens_paises(placeholder: str = "Selecione...") -> list[dict]:
	"""Países no formato que o Paxtu exibe (``BR - Brasil``), reusando a lista do phone-input.

	O valor gravado é o rótulo inteiro: é ele que a recepção copia para o Paxtu, e guardar só
	a sigla obrigaria a ficha a reconstruir o nome na hora de exibir.
	"""
	itens = [{"label": placeholder, "value": ""}]
	for pais in get_phone_countries():
		rotulo = f"{pais['iso']} - {pais['name']}"
		itens.append({"label": rotulo, "value": rotulo})
	return itens


def pais_brasil() -> str:
	"""Valor gravado para o Brasil — o padrão de quase todo cadastro do grupo."""
	return "BR - Brasil"
