# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Vocabulário compartilhado do módulo Manutenção.

Fonte única para o formulário de solicitação, a validação do DocType, a página
de acompanhamento e a tela de gestão. Qualquer opção nova entra aqui **e** no
`options` do Select correspondente em `solicitacao_de_manutencao.json` — o teste
`test_opcoes_do_doctype_batem_com_as_constantes` guarda esse pareamento.
"""

from __future__ import annotations

DOCTYPE = "Solicitacao de Manutencao"

# Quem organiza a fila: define prioridade, data prevista e quem executa. O papel
# já existia para a área de manutenção de Compras, e é a mesma equipe.
ROLE_GESTOR = "Gestor de Manutencao"

# ───────────────────────────── andamento ─────────────────────────────

# Toda solicitação nova entra aqui, até alguém da gestão olhar.
STATUS_RECEBIDA = "Recebida"
# Avaliada e com lugar na fila: é o que aparece em "Próximas manutenções".
STATUS_PLANEJADA = "Planejada"
STATUS_EM_ANDAMENTO = "Em andamento"
# Começou, mas parou à espera de compra, doação ou de alguém que saiba fazer.
STATUS_AGUARDANDO = "Aguardando material"
STATUS_CONCLUIDA = "Concluída"
STATUS_NAO_SERA_FEITA = "Não será feita"

STATUS: tuple[str, ...] = (
	STATUS_RECEBIDA,
	STATUS_PLANEJADA,
	STATUS_EM_ANDAMENTO,
	STATUS_AGUARDANDO,
	STATUS_CONCLUIDA,
	STATUS_NAO_SERA_FEITA,
)

STATUS_FINAIS: tuple[str, ...] = (STATUS_CONCLUIDA, STATUS_NAO_SERA_FEITA)
STATUS_ABERTOS: tuple[str, ...] = tuple(s for s in STATUS if s not in STATUS_FINAIS)
# "Aguardando material" conta como em execução: o trabalho começou e a pessoa
# que pediu quer saber que alguém está nele, não que voltou para a fila.
STATUS_EM_EXECUCAO: tuple[str, ...] = (STATUS_EM_ANDAMENTO, STATUS_AGUARDANDO)

# ───────────────────────────── prioridade ─────────────────────────────

PRIORIDADE_BAIXA = "Baixa"
PRIORIDADE_MEDIA = "Média"
PRIORIDADE_ALTA = "Alta"
PRIORIDADE_URGENTE = "Urgente"

PRIORIDADES: tuple[str, ...] = (
	PRIORIDADE_BAIXA,
	PRIORIDADE_MEDIA,
	PRIORIDADE_ALTA,
	PRIORIDADE_URGENTE,
)

# Peso para ordenar a fila: maior vem primeiro.
PESO_PRIORIDADE: dict[str, int] = {p: i for i, p in enumerate(PRIORIDADES, start=1)}

# ───────────────────── o que quem pede informa ─────────────────────

URGENCIA_PODE_ESPERAR = "Pode esperar"
URGENCIA_ATRAPALHA = "Atrapalha as atividades"
URGENCIA_RISCO = "Risco à segurança"

URGENCIAS: tuple[str, ...] = (URGENCIA_PODE_ESPERAR, URGENCIA_ATRAPALHA, URGENCIA_RISCO)

# Prioridade sugerida na abertura, a partir do que a pessoa contou. A gestão
# ajusta depois; "Urgente" fica reservada para decisão de quem organiza a fila.
PRIORIDADE_POR_URGENCIA: dict[str, str] = {
	URGENCIA_PODE_ESPERAR: PRIORIDADE_BAIXA,
	URGENCIA_ATRAPALHA: PRIORIDADE_MEDIA,
	URGENCIA_RISCO: PRIORIDADE_ALTA,
}

CATEGORIA_OUTRO = "Outro"

CATEGORIAS: tuple[str, ...] = (
	"Elétrica e iluminação",
	"Hidráulica e banheiros",
	"Portas, janelas e fechaduras",
	"Telhado e estrutura",
	"Pintura",
	"Móveis e marcenaria",
	"Equipamentos",
	"Limpeza e jardinagem",
	CATEGORIA_OUTRO,
)

# ───────────────────────────── limites ─────────────────────────────

TITULO_MAX = 140
LOCAL_MAX = 140
DESCRICAO_MAX = 3000
RESPONSAVEL_MAX = 140
TEXTO_INTERNO_MAX = 3000

# Freio contra envio repetido (duplo clique, script). Ninguém precisa abrir mais
# do que isso numa hora; um mutirão de vistoria pode pedir à gestão que cadastre.
LIMITE_ENVIOS_POR_HORA = 10

# Quanto tempo uma manutenção concluída continua visível no acompanhamento.
DIAS_CONCLUIDAS_VISIVEIS = 30
