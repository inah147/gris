# Acessar o GRIS pelo Claude (MCP)

Integração que permite conversar com o Claude e, na mesma conversa, **consultar
associados, categorizar transações e atualizar dados** no GRIS — sem sair do
chat e sem abrir exceção de segurança: tudo passa pelo usuário do Frappe,
com os mesmos papéis e permissões do portal.

## Como funciona

```
Claude (Code / Desktop)
        │  protocolo MCP (stdio)
        ▼
mcp_server/gris_mcp.py          ponte fina, sem dependências externas
        │  HTTPS + token de API
        ▼
gris.api.mcp.endpoints          catálogo, autorização e validação
        │
        ▼
serviços do app (gris.api.financeiro, gris.api.recepcao, ...)
        │
        ▼
DocTypes do Frappe (Associado, Transacao Extrato Geral, Novo Associado, ...)
```

O catálogo de ferramentas vive **no servidor** (`gris/api/mcp/registry.py`).
A ponte local não conhece regra de negócio: ela só traduz protocolo. Isso
significa que uma ferramenta nova aparece no Claude assim que o site é
atualizado — sem mexer na máquina de quem usa.

## Ferramentas disponíveis

### Associados

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_associados` | Lista associados com filtros (ramo, seção, área, status) e busca por nome/CPF/e-mail | Gestor de Associados, Visualizador Associados |
| `obter_associado` | Ficha completa por CPF, com responsáveis, contribuição e histórico | Gestor de Associados, Visualizador Associados |
| `atualizar_associado` ✎ | Grava campos do associado (lista fechada de campos editáveis) | Gestor de Associados |
| `estatisticas_associados` | Totais por ramo, categoria, seção e status | + Visualizador de Métricas de Associados |
| `listar_unidades_organizacionais` | Unidades organizacionais e hierarquia | Gestor/Visualizador Associados, Gestor da UEL |

### Extrato e categorização

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_transacoes` | Extrato com filtros de período, categoria, carteira, revisão e `sem_categoria` | Gestor Financeiro, Visualizador Financeiro |
| `listar_opcoes_financeiras` | Valores válidos: categorias, centros de custo, carteiras, instituições, contas fixas | Gestor Financeiro, Visualizador Financeiro |
| `categorizar_transacoes` ✎ | Categoriza até 200 transações por chamada; define o `beneficiario` que liga a contribuição mensal ao associado | Gestor Financeiro |
| `resumo_financeiro` | Totais de crédito/débito por período, agrupados por categoria, centro de custo ou carteira | Gestor Financeiro, Visualizador Financeiro |
| `serie_financeira` | Séries dos últimos 12 meses do painel (entradas x saídas, por categoria/centro/tipo, contribuições, inadimplência) | Gestor Financeiro, Visualizador Financeiro |

### Conciliação

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_pendentes_conciliacao` | Transações de Sistema ainda não conciliadas com a planilha | Gestor Financeiro |
| `sugerir_candidatos_conciliacao` | Candidatos de planilha para uma pendência (valor ±R$1, data ±5 dias), ordenados | Gestor Financeiro |
| `conciliar_transacoes` ✎ | Vincula o par, define quem conta no total e categoriza o mantido | Gestor Financeiro |
| `marcar_sem_duplicata` ✎ | Resolve a pendência que não tem par na planilha | Gestor Financeiro |
| `desfazer_conciliacao` ✎ | Desfaz o vínculo e devolve os dois registros aos totais | Gestor Financeiro |

### Contribuições mensais

A apuração voltou a ser a do DocType `Pagamento Contribuicao Mensal`: um
registro por associado e mês, com status (Pago/Em Aberto/Atrasado), valor e —
quando pago — a transação do extrato que quitou (`transacao_extrato`). Sem
carência de registro, valor de atraso escalonado ou crédito retroativo: o que
está gravado no registro é o que a tela e o MCP mostram. Um mês sem registro
ainda gerado aparece como "Não gerado".

A tela (`/financeiro/contribuicoes` e `/financeiro/contribuicao`) lê e edita
os mesmos registros — trocar status e vincular a transação certa também
funciona por lá, além do MCP.

Uma transação pode quitar mais de um mês num único pagamento (ex.: R$ 70 do mês
em atraso + R$ 60 do mês em dia). Isso fica declarado no campo "Meses cobertos
por esta transação" da própria transação (tela do extrato no Desk); ao salvar,
um Pagamento Contribuicao Mensal é criado/atualizado por mês declarado,
vinculado a ela. `competencias_transacao`/`definir_competencias_transacao`
leem e escrevem esse detalhamento.

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `resumo_contribuicoes` | Recebido, esperado, adimplência e pendências de cadastro no período, a partir dos registros de cobrança | Gestor/Visualizador Contribuição Mensal |
| `apuracao_contribuicoes` | Situação de cada contribuinte: esperado, recebido, saldo e situação (Atrasado, Em Aberto, Pago, Não gerado); filtra por situação, pendência e ação de cadastro | Gestor/Visualizador Contribuição Mensal |
| `extrato_contribuicoes_associado` | Transações de contribuição atribuídas a um associado no período (evidência do extrato, ao lado do mês a mês) | Gestor/Visualizador Contribuição Mensal |
| `listar_contribuicoes_nao_vinculadas` | Contribuições que entraram na conta e ainda não têm associado | Gestor/Visualizador Contribuição Mensal |
| `atualizar_cobranca_associado` ✎ | Valor da contribuição, situação da cobrança e contatos de cobrança | Gestor Contribuição Mensal |
| `competencias_transacao` | Meses declarados numa transação que quita mais de um mês | Gestor/Visualizador Contribuição Mensal |
| `definir_competencias_transacao` ✎ | Declara os meses e o valor de cada um numa transação (mês atrasado + mês em dia, por exemplo); a soma precisa bater com o valor da transação | Gestor Contribuição Mensal |
| `listar_pagamentos_contribuicao_mensal` | Registros de cobrança (`Pagamento Contribuicao Mensal`), com a transação que quitou cada um | Gestor/Visualizador Contribuição Mensal |
| `atualizar_pagamento_contribuicao_mensal` ✎ | Ajusta status, valor, atraso e vínculo com a transação de um registro existente (por `name`) | Gestor Contribuição Mensal |
| `definir_pagamento_mensal` ✎ | Cria ou atualiza o pagamento de um mês por associado + mês (AAAA-MM) — não precisa do `name`, serve para meses "Não gerado" | Gestor Contribuição Mensal |

### Contas fixas

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_contas_fixas` | Despesas recorrentes com valor, vencimento e custo mensal somado | Gestor Financeiro, Visualizador Financeiro |
| `listar_pagamentos_contas_fixas` | Pagamentos por conta, status e mês | Gestor Financeiro, Visualizador Financeiro |
| `marcar_contas_fixas_pagas` ✎ | Marca até 100 pagamentos como 'Pago' | Gestor Financeiro |

### Previsão orçamentária

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_previsoes_orcamentarias` | Previsões cadastradas com totais previstos | Gestor Financeiro, Visualizador Financeiro |
| `obter_previsao_orcamentaria` | Uma previsão com todos os itens | Gestor Financeiro, Visualizador Financeiro |
| `comparar_previsto_realizado` | Previsto x realizado do período: desvios, execução e quebra por categoria/centro | Gestor Financeiro, Visualizador Financeiro |
| `criar_previsao_orcamentaria` ✎ | Cria a previsão, opcionalmente já com itens | Gestor Financeiro |
| `atualizar_previsao_orcamentaria` ✎ | Dados gerais da previsão (título, período, status, centro) | Gestor Financeiro |
| `salvar_item_previsao` ✎ | Cria ou atualiza um item de receita/despesa | Gestor Financeiro |
| `excluir_item_previsao` ✎ | Remove um item de previsão não encerrada | Gestor Financeiro |

### Recepção (funil de novos associados)

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_novos_associados` | Funil com progresso das etapas; filtra por status, ramo, responsável, etapa pendente e `somente_atrasados` | Recepcao |
| `obter_novo_associado` | Ficha completa: contato, etapas com data estimada, visita e responsáveis legais | Recepcao |
| `funil_recepcao` | Panorama: por status, ramo e responsável, quantos atrasados e quais etapas travam | Recepcao |
| `atualizar_etapa_recepcao` ✎ | Marca/desmarca uma etapa (com os mesmos efeitos de status do portal) | Recepcao |
| `atualizar_novo_associado` ✎ | Status do funil, ramo pretendido e responsável de recepção | Recepcao |
| `comentar_novo_associado` ✎ | Comentário interno no registro | Recepcao |
| `enviar_para_fila_espera` ✎ | Move para a fila de espera do ramo | Recepcao |
| `listar_fila_espera` | Fila por ramo, na ordem de entrada, com posição | Recepcao |
| `chamar_da_fila_espera` ✎ | Tira da fila e devolve ao início do funil | Recepcao |
| `listar_respostas_pesquisa_recepcao` | Respostas da pesquisa de novas famílias | Recepcao |
| `obter_resposta_pesquisa_recepcao` | Uma resposta completa, com textos abertos e beneficiários | Recepcao |
| `nps_recepcao` | NPS consolidado e série por período | Recepcao |

### Agenda de visitas

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_visitas` | Visitas por período, ramo e confirmação | Recepcao |
| `datas_disponiveis_visita` | Sábados livres nos próximos 60 dias para o ramo (ou para remarcar uma visita) | Recepcao |
| `agendar_visita` ✎ | Agenda a primeira visita em data disponível | Recepcao |
| `atualizar_visita` ✎ | Confirmar, desconfirmar, remarcar ou cancelar | Recepcao |

### Insígnias e distintivos

Fluxo: Solicitada -> Comprada -> Recebida -> Entregue (com Cancelada como saída
até o recebimento). Quem só solicita enxerga apenas os próprios pedidos; gestão
de métodos e financeiro enxergam a fila completa.

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_catalogo_insignias` | Catálogo de distintivos/insígnias com tipo, ramo e valor unitário de referência | Equipe/Gestor de Metodos, Gestor Financeiro |
| `salvar_item_catalogo_insignias` ✎ | Cria ou edita um item do catálogo | Gestor de Metodos |
| `alternar_item_catalogo_insignias` ✎ | Ativa ou inativa um item (não há exclusão) | Gestor de Metodos |
| `listar_solicitacoes_insignias` | Lista solicitações com resumo por status; filtra por status, ramo e solicitante | Equipe/Gestor de Metodos, Gestor Financeiro |
| `obter_solicitacao_insignias` | Ficha completa: itens, beneficiários, linha do tempo e o que o usuário pode fazer | Equipe/Gestor de Metodos, Gestor Financeiro |
| `criar_solicitacao_insignias` ✎ | Abre uma solicitação com uma lista de itens; o valor unitário sempre vem do catálogo | Equipe/Gestor de Metodos |
| `registrar_compra_insignias` ✎ | Financeiro registra a compra de uma solicitação 'Solicitada' | Gestor Financeiro |
| `registrar_recebimento_insignias` ✎ | Financeiro confirma que o material chegou ao grupo | Gestor Financeiro |
| `registrar_entrega_insignias` ✎ | Confirma a entrega ao solicitante (pelo próprio ou pela gestão) | Equipe/Gestor de Metodos, Gestor Financeiro |
| `cancelar_solicitacao_insignias` ✎ | Cancela um pedido ainda não recebido | Equipe/Gestor de Metodos, Gestor Financeiro |

### Sugestões e Problemas

Quadro interno de feedback (`/sugestoes/acompanhamento`). Comentar dispara
aviso por WhatsApp para quem abriu a solicitação e para o responsável pelo
desenvolvimento (quando há um e não é quem comentou) — mesmo hook usado pelo
portal e pelo Desk, então vale para os três caminhos.

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_sugestoes` | Lista o quadro com filtros de status, tipo, módulo, responsável, pendência de esclarecimento e busca por título | Acompanhamento de Sugestoes, Desenvolvedor |
| `obter_sugestao` | Ficha completa: descrição, linha do tempo, branch, pull request e comentários | Acompanhamento de Sugestoes, Desenvolvedor |
| `atualizar_sugestao` ✎ | Move de coluna, reclassifica o tipo, aloca responsável ou reescreve a descrição | Desenvolvedor |
| `assumir_sugestao` ✎ | Pega a demanda: aloca, move para "Em desenvolvimento" e grava a branch, num passo só | Desenvolvedor |
| `pedir_esclarecimento` ✎ | Pergunta sobre a demanda e marca o card como aguardando resposta de quem abriu | Desenvolvedor |
| `registrar_pull_request` ✎ | Grava no card o link do PR que entrega a solicitação | Desenvolvedor |
| `comentar_sugestao` ✎ | Comenta na solicitação e dispara o aviso por WhatsApp | Acompanhamento de Sugestoes, Desenvolvedor |

#### Levar uma demanda do quadro até o pull request

O ciclo que essas ferramentas fecham, quando o Claude trabalha uma solicitação:

1. `listar_sugestoes` com `status='Selecionado para desenvolvimento'` e
   `sem_responsavel=true` — o que está liberado para pegar.
2. `obter_sugestao` — descrição e conversa até aqui.
3. **Se a demanda não está clara**, `pedir_esclarecimento`: a pergunta vira
   comentário, quem abriu recebe por WhatsApp e o card fica marcado como
   *Aguardando esclarecimento* (badge no quadro). A marca cai sozinha quando
   essa pessoa responde, então `listar_sugestoes` com
   `aguardando_esclarecimento=false` mostra o que já pode voltar para a fila.
4. **Se está clara**, `assumir_sugestao` com a `branch` do trabalho: aloca,
   move o card e cria a tarefa espelho em "Minhas tarefas" de uma vez. Assumir
   por cima de outro responsável é recusado sem `forcar=true`, para duas
   sessões não trabalharem na mesma coisa sem saber.
5. Abrir o PR e chamar `registrar_pull_request` com a URL — o link passa a
   aparecer no dialog do card, para quem abriu acompanhar a entrega.
6. Depois do merge, `atualizar_sugestao` com `status='Concluído'` dispara o
   aviso de conclusão para quem pediu.

### Usuários e papéis

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_usuarios` | Usuários do sistema com seus papéis; filtra por busca (nome/e-mail) ou por um papel exato | System Manager (auditoria de acesso) |
| `listar_papeis` | Papéis (roles) cadastrados, para descobrir o nome exato antes de usar `listar_usuarios` com `papel` | System Manager (auditoria de acesso) |

### Apoio

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `quem_sou_eu` | Mostra usuário conectado, papéis e ferramentas liberadas | qualquer usuário autenticado |
| `diagnostico_conexao` | Local da ponte: testa URL, credenciais e conectividade | — |

As ferramentas marcadas com ✎ gravam dados e aceitam `simular=true` (veja
[Simulação](#simulação-dry-run)). Continuam só pelo portal: **desistência de
novo associado** (apaga registros e anonimiza o login do responsável, por LGPD),
exclusão de previsão inteira, cadastro de contas fixas e importação de extratos
— operações irreversíveis, raras ou que dependem de upload de arquivo.

`System Manager` enxerga todas as ferramentas, seguindo o mesmo critério de
`gris.api.portal_access.user_has_access`.

## Instalação

### 1. Atualizar o site

O código novo fica em `gris/api/mcp/`. Não há mudança de schema — basta
atualizar o app e reiniciar:

```bash
cd ~/frappe-bench/apps/gris && git pull
bench --site <seu-site> clear-cache && bench restart
```

Ambiente local (WSL2 + Frappe Manager): siga
[.claude/skills/gris-ambiente-local/SKILL.md](.claude/skills/gris-ambiente-local/SKILL.md).

### 2. Gerar as credenciais de API

No Desk, abra o usuário que vai ser usado pela integração
(`/app/user/<email>`) → seção **API Access** → **Generate Keys**. Guarde a
`api_secret` (só aparece uma vez) e copie a `api_key`.

> Use um usuário com exatamente os papéis que você quer que o Claude possa
> exercer. Para um acesso só de leitura, um usuário com
> `Visualizador Associados` + `Visualizador Financeiro` já resolve.

### 3. Registrar o servidor no Claude Code

```bash
claude mcp add gris \
  --env GRIS_URL=https://<seu-site> \
  --env GRIS_API_KEY=<api_key> \
  --env GRIS_API_SECRET=<api_secret> \
  -- python3 /caminho/para/gris/mcp_server/gris_mcp.py
```

Confira com `claude mcp list` e, no chat, peça: *"use a ferramenta
quem_sou_eu do GRIS"*.

### 3b. Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "gris": {
      "command": "python3",
      "args": ["/caminho/para/gris/mcp_server/gris_mcp.py"],
      "env": {
        "GRIS_URL": "https://seu-site",
        "GRIS_API_KEY": "sua_api_key",
        "GRIS_API_SECRET": "seu_api_secret"
      }
    }
  }
}
```

No Windows com o código dentro do WSL2:

```json
{
  "mcpServers": {
    "gris": {
      "command": "wsl.exe",
      "args": [
        "-e", "bash", "-lc",
        "GRIS_URL=https://seu-site GRIS_API_KEY=chave GRIS_API_SECRET=segredo python3 /home/<usuario>/gris/mcp_server/gris_mcp.py"
      ]
    }
  }
}
```

### 3c. Alternativa sem processo local (transporte HTTP)

Para clientes que suportam servidor MCP remoto com header:

```bash
claude mcp add --transport http gris \
  https://<seu-site>/api/method/gris.api.mcp.http.mcp \
  --header "Authorization: token <api_key>:<api_secret>"
```

O endpoint responde JSON-RPC puro (sem SSE) e usa exatamente o mesmo catálogo
e as mesmas permissões da ponte stdio.

### 3d. Claude Code na web (sessão remota)

O repositório já traz um `.mcp.json` na raiz que registra a ponte como servidor
**de projeto**: qualquer sessão do Claude Code aberta neste repo — local ou na
web — enxerga o servidor `gris` sem `claude mcp add`. O arquivo não guarda
segredo nenhum: ele só referencia as variáveis de ambiente.

Sem as variáveis definidas, a ponte ainda sobe e expõe apenas
`diagnostico_conexao` — nada quebra numa sessão que não precisa de produção.

Para uma sessão da web falar com o site, o **ambiente** precisa de duas coisas,
configuradas em claude.ai/code → ambiente:

1. **Variáveis de ambiente**: `GRIS_URL`, `GRIS_API_KEY`, `GRIS_API_SECRET`
   (e `GRIS_MCP_SOMENTE_LEITURA=1` quando a sessão só precisa consultar).
   Defina-as ali, nunca no chat nem em arquivo versionado.
2. **Política de rede**: o host do site (ex.: `gris.gepim.com.br`) precisa estar
   liberado no egresso do ambiente. Sem isso o proxy recusa a conexão com
   `403 / connect_rejected` antes de qualquer autenticação.

As duas valem a partir da **próxima** sessão: o container é provisionado no
início da sessão, então uma sessão já aberta não enxerga a mudança.

> Sessão remota fala com **produção**: dados reais de associados, incluindo
> menores. Prefira um usuário de API com os papéis mínimos e
> `GRIS_MCP_SOMENTE_LEITURA=1`, e só relaxe para escrita quando a tarefa
> realmente exigir gravação.

## Uso no dia a dia

Exemplos de pedidos que funcionam bem:

**Associados**
- *"Quantos associados ativos temos por ramo?"* → `estatisticas_associados`
- *"Lista os lobinhos com registro vencido"* → `listar_associados`
- *"Atualiza o telefone da associada do CPF 123.456.789-00 para (11) 98888-7777"* → `obter_associado` + `atualizar_associado`

**Extrato**
- *"Mostra as transações de janeiro que ainda estão sem categoria"* → `listar_transacoes` com `sem_categoria=true`
- *"Categoriza essas cinco como Doações, centro de custo Sede, e marca como revisadas"* → `listar_opcoes_financeiras` + `categorizar_transacoes`
- *"Compara os gastos deste ano com o anterior por centro de custo"* → `serie_financeira` / `resumo_financeiro`

**Conciliação** — o fluxo em que o modelo mais agrega:
1. `listar_pendentes_conciliacao` traz o que o sistema registrou e a planilha ainda não casou;
2. `sugerir_candidatos_conciliacao` devolve os candidatos por valor e data;
3. o Claude lê as descrições ("PIX RECEBIDO M S SILVA" x "Contribuição Ago/Mariana Silva") e propõe o par;
4. você confirma e ele chama `conciliar_transacoes` — ou `marcar_sem_duplicata` quando não há par.

**Recepção**
- *"Quem está travado no funil e em qual etapa?"* → `funil_recepcao`, depois `listar_novos_associados` com `somente_atrasados=true`
- *"Quem ainda não fez a ficha médica?"* → `listar_novos_associados` com `etapa_pendente='ficha_medica_preenchida'`
- *"Marca a reunião de acolhida da Ana como feita"* → `obter_novo_associado` + `atualizar_etapa_recepcao`
- *"Que sábados estão livres para o Lobinho? Agenda dia 14 para o João"* → `datas_disponiveis_visita` + `agendar_visita`
- *"Abriu vaga no Lobinho — quem é o próximo da fila?"* → `listar_fila_espera` + `chamar_da_fila_espera`
- *"Como está o NPS da recepção?"* → `nps_recepcao`

**Contribuições**
- *"Como está a adimplência dos últimos 6 meses?"* → `resumo_contribuicoes`
- *"Quem está atrasado ou pagou parcial?"* → `apuracao_contribuicoes` com `com_pendencia=true`
- *"Quais contribuições caíram na conta sem dono?"* → `listar_contribuicoes_nao_vinculadas`, depois `categorizar_transacoes` com `beneficiario`
- *"Quem entrou no grupo e ainda não tem cobrança cadastrada?"* → `apuracao_contribuicoes` com `acao_cadastro='Cadastrar'`
- *"Sobe a contribuição da Ana para R$ 75"* → `atualizar_cobranca_associado`
- *"Esse Pix de R$ 130 foi o mês de julho atrasado (R$ 70) mais agosto em dia (R$ 60)"* → `definir_competencias_transacao` com `competencias=[{"mes":"2026-07","valor":70,"em_atraso":true},{"mes":"2026-08","valor":60,"em_atraso":false}]`
- *"Marca julho da Ana como pago e vincula à transação TX-0001"* → `definir_pagamento_mensal` com `associado`, `mes="2026-07"`, `status="Pago"`, `transacao_extrato="TX-0001"`

**Orçamento**
- *"Como está a execução do orçamento deste ano?"* → `comparar_previsto_realizado`
- *"Cria o orçamento de 2027 com as mesmas linhas de 2026 e 8% a mais em manutenção"* → `obter_previsao_orcamentaria` + `criar_previsao_orcamentaria`

**Insígnias e distintivos**
- *"Quais distintivos de progressão do Lobinho existem no catálogo?"* → `listar_catalogo_insignias` com `tipo` e `ramo`
- *"Abre uma solicitação para o Lobinho com 2 Distintivos de Progressão II para a Ana"* → `listar_catalogo_insignias` + `criar_solicitacao_insignias`
- *"O que está parado esperando compra?"* → `listar_solicitacoes_insignias` com `status='Solicitada'`
- *"Registra a compra da SOL-INS-2026-0001, paguei R$ 45 na Loja Escoteira"* → `obter_solicitacao_insignias` + `registrar_compra_insignias`
- *"Chegou o material da SOL-INS-2026-0001, marca como recebido"* → `registrar_recebimento_insignias`
- *"Já entreguei os distintivos para a Ana"* → `registrar_entrega_insignias`

**Sugestões e Problemas**
- *"O que está selecionado para desenvolvimento?"* → `listar_sugestoes` com `status='Selecionado para desenvolvimento'`
- *"Aloca a Ana na SUG-00012 e comenta que ela já pode começar"* → `atualizar_sugestao` com `responsavel` + `comentar_sugestao`
- *"Pega a SUG-00012 para você e trabalha na branch claude/sug-12"* → `assumir_sugestao` com `branch`
- *"O que está travado esperando resposta de quem pediu?"* → `listar_sugestoes` com `aguardando_esclarecimento=true`

**Usuários e papéis**
- *"Quem tem o papel Gestor de Metodos hoje?"* → `listar_usuarios` com `papel='Gestor de Metodos'`

## Segurança

- **Sem acesso guest.** Todo chamado exige API key/secret de um usuário real.
- **Dupla checagem de permissão**: papéis declarados por ferramenta e, além
  disso, as permissões de DocType do Frappe (`get_all` filtrado,
  `check_permission` antes de gravar).
- **Campos com lista fechada**: `atualizar_associado` e `categorizar_transacoes`
  só gravam campos explicitamente liberados; valores de `Select` e `Link` são
  validados contra o schema antes do save.
- **Modo somente leitura**: defina `GRIS_MCP_SOMENTE_LEITURA=1` no ambiente da
  ponte para esconder e bloquear todas as ferramentas de escrita.
- **Simulação (dry-run)**: toda ferramenta de escrita aceita `simular=true` e
  devolve o antes/depois sem gravar nada.
- **Auditoria**: toda execução de ferramenta que grava dados gera um registro
  no logger `gris_mcp` com usuário, ferramenta e argumentos.
- **Descrição bruta do extrato** continua restrita ao `Gestor Financeiro`,
  igual à página `/financeiro/extrato`.
- **Usuários e papéis de terceiros** só são consultáveis por `System Manager`
  (`listar_usuarios`, `listar_papeis`) — é dado sensível de acesso ao sistema.
- As credenciais ficam apenas na máquina que roda a ponte. Nunca comite
  `api_secret` no repositório.

## OAuth: o que falta para virar connector

Hoje a integração autentica por **API key** (`Authorization: token <key>:<secret>`),
o que obriga cada máquina a registrar a ponte. Um **connector customizado** na
conta do Claude cobriria Desktop, claude.ai e sessões remotas de uma vez só —
mas o cadastro de connector faz **descoberta OAuth**, não aceita header fixo.

### O endpoint não precisa mudar

`frappe/auth.py` (`validate_oauth`) já trata `Authorization: Bearer <token>`:
valida contra o DocType `OAuth Bearer Token`, confere os escopos e chama
`frappe.set_user()`. Como `gris.api.mcp.http.mcp` é um whitelist comum que roda
sob `frappe.session.user`, **um access token OAuth autentica exatamente como a
API key** — e as checagens de papel do `registry` continuam valendo.

Isso está coberto por `gris/tests/test_mcp_oauth.py`, que exercita o caminho
real de autenticação contra registros de verdade (token válido, revogado,
expirado e inexistente).

### O que o Frappe já entrega

| Peça | Onde |
|---|---|
| Authorization Code flow | `frappe/integrations/oauth2.py` — `authorize`, `get_token` |
| PKCE (`s256` e `plain`) | `frappe/oauth.py` — grava no `OAuth Authorization Code` e verifica na troca |
| Revogação e introspecção | `oauth2.py` — `revoke_token`, `introspect_token` |
| Descoberta OpenID | `oauth2.py:openid_configuration`, roteada em `frappe/hooks.py` |
| Cadastro de cliente | DocType `OAuth Client` (manual, pelo Desk) |

### O que já foi feito

`gris/api/mcp/oauth.py` implementa a camada de descoberta (Fase 1 do
[PLANO_OAUTH_MCP.md](PLANO_OAUTH_MCP.md)), coberta por
`gris/tests/test_mcp_oauth.py`:

1. **`/.well-known/oauth-protected-resource`** (RFC 9728) — roteado em
   `gris/hooks.py` (`website_redirects`) para `oauth_protected_resource`.
   Aponta o authorization server e o escopo dedicado (`gris.mcp`).
2. **`/.well-known/oauth-authorization-server`** (RFC 8414) — roteado do mesmo
   jeito para `oauth_authorization_server`, que chama o `openid_configuration`
   do Frappe (sem alterá-lo) e acrescenta o que ele não anuncia:
   `code_challenge_methods_supported`, `grant_types_supported`,
   `token_endpoint_auth_methods_supported` e `scopes_supported`.
3. **`WWW-Authenticate` no 401** — hook `after_request`
   (`anunciar_recurso_protegido`) restrito ao caminho do MCP. Cobre tanto o
   401 que `validate_auth` já levanta para um Bearer inválido/expirado/revogado
   quanto o 403 que `is_whitelisted` devolve pra Guest sem nenhum
   `Authorization` — as duas são a mesma falta de credencial válida, então as
   duas viram 401 com o header.

### O que falta

1. **Fase 0** — verificar se o cadastro de connector do claude.ai aceita
   Client ID/Secret preenchidos à mão. Se não aceitar, entra a Fase 5
   (**Dynamic Client Registration**, RFC 7591) — não existe endpoint
   `register`, e isso pode dobrar o esforço.
2. **Fase 2** — cadastrar o `OAuth Client` com o escopo `gris.mcp` e
   `redirect_uri` estrita (ver *Atenção ao registrar o cliente* abaixo).
3. **Fases 3–4** — rodar o fluxo ponta a ponta local e cadastrar o connector
   de produção.

### Atenção ao registrar o cliente

`frappe/oauth.py` (`authenticate_client`) **carrega o cliente pelo `client_id`
sem conferir o `client_secret`**. Na prática o provider trata todo cliente como
público, então o PKCE passa a ser a única proteção do fluxo: registre a
`redirect_uri` de forma estrita e não trate o secret como segunda barreira.
Prefira também um escopo dedicado no `OAuth Client` em vez de `all`.

## Simulação (dry-run)

Toda ferramenta que grava ganha automaticamente o parâmetro `simular` — o
registro injeta no schema, e o handler devolve o que mudaria sem tocar no banco:

```
"Categoriza como Doações as 40 transações de novembro sem categoria, mas simula primeiro"
→ categorizar_transacoes(ids=[...], categoria="Doações", simular=true)
→ {"simulacao": true, "atualizadas": 0, "previa": [{"id": "...", "alteracoes": {...}}]}
```

Validações de permissão, de campo Select e de existência de Link rodam também na
simulação — então um `simular=true` limpo é boa evidência de que a gravação vai
passar. Simulações não entram no log de auditoria (não alteram nada).

## Adicionar uma ferramenta nova

1. Escolha o módulo em `gris/api/mcp/` (`associados`, `financeiro`, `conciliacao`,
   `contribuicoes`, `contas_fixas`, `orcamento`, `recepcao`, `visitas`, `insignias`, `geral`)
   ou crie um novo e registre-o em `MODULOS_DE_FERRAMENTAS`.
2. Decore a função com `@ferramenta(...)`, declarando `parametros`
   (JSON Schema simplificado), `roles` e `somente_leitura`.
3. Escreva o handler retornando um `dict` serializável. Com
   `somente_leitura=False` o handler precisa aceitar `simular: bool = False` e
   devolver o antes/depois sem gravar quando for verdadeiro.
4. Reaproveite o serviço que já existe em `gris/api/...` em vez de reescrever a
   regra de negócio — as ferramentas desta integração são casca fina.
5. Cubra com teste em `gris/tests/test_mcp_*.py`.

```python
@ferramenta(
	nome="listar_carteiras",
	titulo="Listar carteiras",
	descricao="Lista as carteiras ativas com saldo.",
	parametros={"apenas_ativas": {"type": "boolean", "default": True}},
	roles=("Gestor Financeiro",),
)
def listar_carteiras(apenas_ativas: bool = True) -> dict:
	...
```

Nada precisa ser alterado na ponte local nem na configuração do Claude.

## Testes

```bash
# ponte stdio (não precisa de Frappe)
cd mcp_server && python3 -m unittest discover -s tests

# camada do app (dentro do bench; nas sessões web use `bench-gris`, montado pelo
# hook .claude/hooks/session-start.sh)
for modulo in registry ferramentas http oauth contribuicoes conciliacao orcamento recepcao visitas insignias geral sugestoes; do
  bench --site <seu-site> run-tests --module gris.tests.test_mcp_$modulo
done

# regra do funil de recepção, compartilhada com o portal
bench --site <seu-site> run-tests --module gris.tests.test_recepcao_funil
```

## Diagnóstico rápido

| Sintoma | Causa provável |
|---|---|
| Claude não mostra nenhuma ferramenta do GRIS | Ponte não conseguiu falar com o site — peça `diagnostico_conexao` |
| `[CONEXAO] Credenciais recusadas` | `GRIS_API_KEY`/`GRIS_API_SECRET` errados ou usuário desativado |
| `Endpoint não encontrado (HTTP 404)` | Site ainda não está na versão com `gris.api.mcp` |
| Sessão da web: conexão recusada antes de autenticar (`403`, `connect_rejected`) | Host do site não liberado na política de rede do ambiente — veja [3d](#3d-claude-code-na-web-sessão-remota) |
| `[PERMISSAO_NEGADA]` | Usuário da API não tem o papel exigido — rode `quem_sou_eu` |
| `[VALIDACAO]` na conciliação | A transação já está conciliada com outra — use `desfazer_conciliacao` |
| Ferramenta de escrita sumiu | `GRIS_MCP_SOMENTE_LEITURA` está ativo |
