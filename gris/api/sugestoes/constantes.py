# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Vocabulario compartilhado do modulo Sugestoes e Problemas.

Fonte unica para formulario, validacao do DocType, endpoints do portal e o sync
com Gestao de Tarefas. Qualquer opcao nova entra aqui **e** no `options` do
Select correspondente em `sugestao_ou_problema.json` — o teste
`test_opcoes_do_doctype_batem_com_as_constantes` guarda esse pareamento.
"""

from __future__ import annotations

TIPO_PROBLEMA = "Problema"
TIPO_FUNCIONALIDADE = "Nova funcionalidade"

TIPOS: tuple[str, ...] = (TIPO_PROBLEMA, TIPO_FUNCIONALIDADE)

COLUNA_PROBLEMAS = "Problemas reportados"
COLUNA_FUNCIONALIDADES = "Solicitações de funcionalidades"
COLUNA_SELECIONADO = "Selecionado para desenvolvimento"
COLUNA_EM_DESENVOLVIMENTO = "Em desenvolvimento"
# Desenvolvimento pronto e entregue, esperando conferencia de quem pediu (ou de
# quem tria) antes de virar "Concluído" — que e o que dispara o aviso de
# conclusao por WhatsApp. Sem esta coluna, "pronto" e "conferido" eram o mesmo
# estado e o aviso saia antes de alguem ter olhado.
COLUNA_VALIDAR = "Validar"
COLUNA_CONCLUIDO = "Concluído"
COLUNA_NAO_SERA_FEITO = "Não será feito"

# Ordem das colunas no kanban de /sugestoes/acompanhamento.
COLUNAS: tuple[str, ...] = (
	COLUNA_PROBLEMAS,
	COLUNA_FUNCIONALIDADES,
	COLUNA_SELECIONADO,
	COLUNA_EM_DESENVOLVIMENTO,
	COLUNA_VALIDAR,
	COLUNA_CONCLUIDO,
	COLUNA_NAO_SERA_FEITO,
)

# As duas primeiras colunas sao de triagem por tipo: uma submissao nova cai na
# coluna do seu tipo, e so depois anda pelas colunas de status.
COLUNA_INICIAL_POR_TIPO: dict[str, str] = {
	TIPO_PROBLEMA: COLUNA_PROBLEMAS,
	TIPO_FUNCIONALIDADE: COLUNA_FUNCIONALIDADES,
}

COLUNAS_DE_TRIAGEM: frozenset[str] = frozenset({COLUNA_PROBLEMAS, COLUNA_FUNCIONALIDADES})

PRIORIDADE_URGENTE = "Urgente"
PRIORIDADE_ALTA = "Alta"
PRIORIDADE_MEDIA = "Média"
PRIORIDADE_BAIXA = "Baixa"

# Da mais urgente para a menos: a **posicao** de cada rotulo nesta tupla e o
# numero gravado em `prioridade_peso`, e e por ele que o quadro ordena. Ordenar
# pelo texto do Select colocaria "Alta, Baixa, Média, Urgente" — alfabetico, sem
# relacao com urgencia. Inserir um rotulo no meio muda o peso dos seguintes;
# `gris.patches.backfill_prioridade_sugestoes` reescreve os pesos no migrate.
PRIORIDADES: tuple[str, ...] = (
	PRIORIDADE_URGENTE,
	PRIORIDADE_ALTA,
	PRIORIDADE_MEDIA,
	PRIORIDADE_BAIXA,
)

# Quem abre a solicitacao nao escolhe a urgencia — se escolhesse, tudo chegaria
# urgente. Toda submissao entra no meio da fila e quem tria ajusta depois.
PRIORIDADE_PADRAO = PRIORIDADE_MEDIA

MODULO_NOVO = "Novo módulo"
MODULO_OUTRO = "Outro / não sei"

# Espelha os rotulos de primeiro nivel de `SIDEBAR_STRUCTURE` em
# `gris.api.portal_access`, mais os destinos que nao tem pagina propria.
MODULOS: tuple[str, ...] = (
	"Início",
	"Associados",
	"Novos Associados",
	"Financeiro",
	"Calendário",
	"Gestão de Adultos",
	"Insígnias e Distintivos",
	"Projetos",
	"Gestão de Tarefas",
	"Festas",
	"Painel do Responsável",
	"Transparência",
	"Sugestões e Problemas",
	"Acesso e login",
	"Aparência / PWA",
	MODULO_OUTRO,
	MODULO_NOVO,
)

# `Novo módulo` so faz sentido pedindo funcionalidade: nao da para relatar um bug
# em algo que ainda nao existe.
MODULOS_POR_TIPO: dict[str, tuple[str, ...]] = {
	TIPO_PROBLEMA: tuple(m for m in MODULOS if m != MODULO_NOVO),
	TIPO_FUNCIONALIDADE: MODULOS,
}

ROLE_DESENVOLVEDOR = "Desenvolvedor"

# Quem enxerga o quadro. Submeter e' liberado a qualquer usuario autenticado,
# mas acompanhar exige este papel — concedido automaticamente a todo Associado.
# Nao usamos o papel "All" do Frappe: ele inclui Website User, que aqui sao os
# responsaveis, e exporia o quadro interno a eles.
ROLE_ACOMPANHAMENTO = "Acompanhamento de Sugestoes"

TITULO_MAX = 140
DESCRICAO_MAX = 10_000

# Campos do trabalho de desenvolvimento. O limite e o do `Data` do Frappe (140):
# nome de branch e URL de pull request cabem folgados, e cortar antes evita um
# erro de banco no save.
BRANCH_MAX = 140
PULL_REQUEST_MAX = 140

# Esquemas aceitos na URL do pull request. Guardar `javascript:` num campo que a
# tela renderiza como link seria XSS armazenado; a lista fechada corta isso na
# entrada, alem de recusar o engano de colar um titulo no lugar do link.
PULL_REQUEST_ESQUEMAS: tuple[str, ...] = ("https://", "http://")

# Teto contra loop acidental de script, nao freio de uso legitimo: quem esta
# testando o sistema e acha oito problemas numa tarde passa sem esbarrar.
LIMITE_ENVIOS_POR_HORA = 20

BOARD_DESENVOLVIMENTO_TITULO = "Desenvolvimento do GRIS"

# Status de `Gestao de Tarefas` (ver TASK_STATUS_OPTIONS no controller da tarefa).
TAREFA_NAO_INICIADO = "Nao iniciado"
TAREFA_EM_ANDAMENTO = "Em andamento"
TAREFA_ATRASADO = "Atrasado"
TAREFA_VALIDAR = "Validar"
TAREFA_CONCLUIDO = "Concluido"
TAREFA_CANCELADO = "Cancelado"

STATUS_TAREFA_POR_COLUNA: dict[str, str] = {
	COLUNA_PROBLEMAS: TAREFA_NAO_INICIADO,
	COLUNA_FUNCIONALIDADES: TAREFA_NAO_INICIADO,
	COLUNA_SELECIONADO: TAREFA_NAO_INICIADO,
	COLUNA_EM_DESENVOLVIMENTO: TAREFA_EM_ANDAMENTO,
	COLUNA_VALIDAR: TAREFA_VALIDAR,
	COLUNA_CONCLUIDO: TAREFA_CONCLUIDO,
	COLUNA_NAO_SERA_FEITO: TAREFA_CANCELADO,
}

# Caminho inverso, usado quando o desenvolvedor mexe na tarefa em "Minhas tarefas".
# `Atrasado` fica de fora de proposito: e derivado pelo cron das 03:00
# (`validar_tarefas_atrasadas`) e nao deve empurrar a sugestao de coluna sozinho
# durante a madrugada.
COLUNA_POR_STATUS_TAREFA: dict[str, str] = {
	TAREFA_NAO_INICIADO: COLUNA_SELECIONADO,
	TAREFA_EM_ANDAMENTO: COLUNA_EM_DESENVOLVIMENTO,
	TAREFA_VALIDAR: COLUNA_VALIDAR,
	TAREFA_CONCLUIDO: COLUNA_CONCLUIDO,
	TAREFA_CANCELADO: COLUNA_NAO_SERA_FEITO,
}


def coluna_inicial(tipo: str) -> str:
	"""Coluna de triagem para uma submissao nova."""
	return COLUNA_INICIAL_POR_TIPO.get((tipo or "").strip(), COLUNA_PROBLEMAS)


def peso_prioridade(prioridade: str) -> int:
	"""Numero por onde o banco ordena a urgencia. Menor = mais urgente.

	Um valor desconhecido (registro antigo, campo em branco) cai no peso do
	padrao, para nunca fabricar uma urgencia que ninguem definiu.
	"""
	rotulo = (prioridade or "").strip()
	if rotulo not in PRIORIDADES:
		rotulo = PRIORIDADE_PADRAO
	return PRIORIDADES.index(rotulo)


def modulos_para_tipo(tipo: str) -> tuple[str, ...]:
	"""Modulos aceitos para um tipo. Usado pelo form e revalidado no servidor."""
	return MODULOS_POR_TIPO.get((tipo or "").strip(), MODULOS)
