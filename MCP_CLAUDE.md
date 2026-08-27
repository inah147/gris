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
DocTypes do Frappe (Associado, Transacao Extrato Geral, ...)
```

O catálogo de ferramentas vive **no servidor** (`gris/api/mcp/registry.py`).
A ponte local não conhece regra de negócio: ela só traduz protocolo. Isso
significa que uma ferramenta nova aparece no Claude assim que o site é
atualizado — sem mexer na máquina de quem usa.

## Ferramentas disponíveis

| Ferramenta | O que faz | Papéis |
|---|---|---|
| `quem_sou_eu` | Mostra usuário conectado, papéis e ferramentas liberadas | qualquer usuário autenticado |
| `listar_associados` | Lista associados com filtros (ramo, seção, área, status) e busca por nome/CPF/e-mail | Gestor de Associados, Visualizador Associados |
| `obter_associado` | Ficha completa por CPF, com responsáveis, contribuição e histórico | Gestor de Associados, Visualizador Associados |
| `atualizar_associado` | Grava campos do associado (lista fechada de campos editáveis) | Gestor de Associados |
| `estatisticas_associados` | Totais por ramo, categoria, seção e status | + Visualizador de Métricas de Associados |
| `listar_unidades_organizacionais` | Unidades organizacionais e hierarquia | Gestor/Visualizador Associados, Gestor da UEL |
| `listar_transacoes` | Extrato com filtros de período, categoria, carteira, revisão e `sem_categoria` | Gestor Financeiro, Visualizador Financeiro |
| `listar_opcoes_financeiras` | Valores válidos: categorias, centros de custo, carteiras, instituições, contas fixas | Gestor Financeiro, Visualizador Financeiro |
| `categorizar_transacoes` | Categoriza até 200 transações por chamada (categoria, centro de custo, ordinária/extraordinária, descrição reduzida, revisada) | Gestor Financeiro |
| `resumo_financeiro` | Totais de crédito/débito por período, agrupados por categoria, centro de custo ou carteira | Gestor Financeiro, Visualizador Financeiro |
| `diagnostico_conexao` | Local da ponte: testa URL, credenciais e conectividade | — |

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

- *"Quantos associados ativos temos por ramo?"* → `estatisticas_associados`
- *"Lista os lobinhos com registro vencido"* → `listar_associados`
- *"Atualiza o telefone da associada do CPF 123.456.789-00 para (11) 98888-7777"* → `obter_associado` + `atualizar_associado`
- *"Mostra as transações de janeiro que ainda estão sem categoria"* → `listar_transacoes` com `sem_categoria=true`
- *"Categoriza essas cinco transações como Doações, centro de custo Sede, e marca como revisadas"* → `listar_opcoes_financeiras` + `categorizar_transacoes`
- *"Fecha o resumo de fevereiro por centro de custo"* → `resumo_financeiro`

Peça sempre para o Claude **confirmar antes de gravar** — as ferramentas de
escrita retornam o antes/depois de cada campo alterado, o que facilita revisar.

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
- **Auditoria**: toda execução de ferramenta que grava dados gera um registro
  no logger `gris_mcp` com usuário, ferramenta e argumentos.
- **Descrição bruta do extrato** continua restrita ao `Gestor Financeiro`,
  igual à página `/financeiro/extrato`.
- As credenciais ficam apenas na máquina que roda a ponte. Nunca comite
  `api_secret` no repositório.

## Adicionar uma ferramenta nova

1. Escolha o módulo (`gris/api/mcp/associados.py`, `financeiro.py`, `geral.py`)
   ou crie um novo e registre-o em `MODULOS_DE_FERRAMENTAS`.
2. Decore a função com `@ferramenta(...)`, declarando `parametros`
   (JSON Schema simplificado), `roles` e `somente_leitura`.
3. Escreva o handler retornando um `dict` serializável.
4. Cubra com teste em `gris/tests/test_mcp_ferramentas.py`.

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
bench --site <seu-site> run-tests --app gris --module gris.tests.test_mcp_registry
bench --site <seu-site> run-tests --app gris --module gris.tests.test_mcp_ferramentas
bench --site <seu-site> run-tests --app gris --module gris.tests.test_mcp_http
```

## Diagnóstico rápido

| Sintoma | Causa provável |
|---|---|
| Claude não mostra nenhuma ferramenta do GRIS | Ponte não conseguiu falar com o site — peça `diagnostico_conexao` |
| `[CONEXAO] Credenciais recusadas` | `GRIS_API_KEY`/`GRIS_API_SECRET` errados ou usuário desativado |
| `Endpoint não encontrado (HTTP 404)` | Site ainda não está na versão com `gris.api.mcp` |
| `[PERMISSAO_NEGADA]` | Usuário da API não tem o papel exigido — rode `quem_sou_eu` |
| Ferramenta de escrita sumiu | `GRIS_MCP_SOMENTE_LEITURA` está ativo |
