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
| `categorizar_transacoes` ✎ | Categoriza até 200 transações por chamada | Gestor Financeiro |
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

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `listar_contribuicoes` | Contribuições por associado, status e mês (ou intervalo) | Gestor/Visualizador Contribuição Mensal |
| `resumo_inadimplencia` | Consolidado do mês: quantidade e valor por status, % de inadimplência e lista de devedores | Gestor/Visualizador Contribuição Mensal |
| `marcar_contribuicoes_pagas` ✎ | Marca até 200 pagamentos como 'Pago' | Gestor Contribuição Mensal |
| `atualizar_cobranca_associado` ✎ | Valor da contribuição, situação da cobrança e contatos de cobrança | Gestor Contribuição Mensal |
| `gerar_contribuicoes_do_mes` ✎ | Cria os registros do mês para os beneficiários ativos (idempotente) | Gestor Contribuição Mensal |

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

**Contribuições**
- *"Como está a inadimplência de março?"* → `resumo_inadimplencia`
- *"Quem está atrasado há mais de dois meses?"* → `listar_contribuicoes` com intervalo e `status='Atrasado'`
- *"Baixa o pagamento desses três associados"* → `marcar_contribuicoes_pagas`
- *"Sobe a contribuição da Ana para R$ 75 a partir de agora"* → `atualizar_cobranca_associado`

**Recepção**
- *"Quem está travado no funil e em qual etapa?"* → `funil_recepcao`, depois `listar_novos_associados` com `somente_atrasados=true`
- *"Quem ainda não fez a ficha médica?"* → `listar_novos_associados` com `etapa_pendente='ficha_medica_preenchida'`
- *"Marca a reunião de acolhida da Ana como feita"* → `obter_novo_associado` + `atualizar_etapa_recepcao`
- *"Que sábados estão livres para o Lobinho? Agenda dia 14 para o João"* → `datas_disponiveis_visita` + `agendar_visita`
- *"Abriu vaga no Lobinho — quem é o próximo da fila?"* → `listar_fila_espera` + `chamar_da_fila_espera`
- *"Como está o NPS da recepção?"* → `nps_recepcao`

**Orçamento**
- *"Como está a execução do orçamento deste ano?"* → `comparar_previsto_realizado`
- *"Cria o orçamento de 2027 com as mesmas linhas de 2026 e 8% a mais em manutenção"* → `obter_previsao_orcamentaria` + `criar_previsao_orcamentaria`

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
- As credenciais ficam apenas na máquina que roda a ponte. Nunca comite
  `api_secret` no repositório.

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
   `contribuicoes`, `contas_fixas`, `orcamento`, `recepcao`, `visitas`, `geral`)
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

# camada do app (dentro do bench)
for modulo in registry ferramentas http contribuicoes conciliacao orcamento recepcao visitas; do
  bench --site <seu-site> run-tests --app gris --module gris.tests.test_mcp_$modulo
done

# regra do funil de recepção, compartilhada com o portal
bench --site <seu-site> run-tests --app gris --module gris.tests.test_recepcao_funil
```

## Diagnóstico rápido

| Sintoma | Causa provável |
|---|---|
| Claude não mostra nenhuma ferramenta do GRIS | Ponte não conseguiu falar com o site — peça `diagnostico_conexao` |
| `[CONEXAO] Credenciais recusadas` | `GRIS_API_KEY`/`GRIS_API_SECRET` errados ou usuário desativado |
| `Endpoint não encontrado (HTTP 404)` | Site ainda não está na versão com `gris.api.mcp` |
| `[PERMISSAO_NEGADA]` | Usuário da API não tem o papel exigido — rode `quem_sou_eu` |
| `[VALIDACAO]` na conciliação | A transação já está conciliada com outra — use `desfazer_conciliacao` |
| Ferramenta de escrita sumiu | `GRIS_MCP_SOMENTE_LEITURA` está ativo |
