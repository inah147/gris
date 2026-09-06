# Ponte MCP do GRIS (stdio)

Servidor MCP que expõe as ferramentas do GRIS ao Claude. **Sem dependências
além da biblioteca padrão** — só Python 3.10+.

Documentação completa (ferramentas, instalação, segurança):
[../MCP_CLAUDE.md](../MCP_CLAUDE.md).

## Configuração

| Variável | Obrigatória | Descrição |
|---|---|---|
| `GRIS_URL` | sim | URL base do site (ex.: `https://gris.gepim.com.br`) |
| `GRIS_API_KEY` | sim | API key do usuário do GRIS |
| `GRIS_API_SECRET` | sim | API secret do usuário do GRIS |
| `GRIS_MCP_SOMENTE_LEITURA` | não | `1` esconde e bloqueia as ferramentas que gravam dados |
| `GRIS_MCP_TIMEOUT` | não | Timeout HTTP em segundos (padrão: `30`) |

Gere a API key/secret no Desk: `/app/user/<email>` → **API Access** →
**Generate Keys**.

## Registrar no Claude Code

O repositório traz um `.mcp.json` na raiz que já registra esta ponte como
servidor de projeto — abrir o Claude Code no repo basta, e as credenciais vêm
das variáveis de ambiente acima. Sem elas a ponte sobe mesmo assim, expondo só
`diagnostico_conexao`.

Para registrar manualmente (fora do repo, ou em outro cliente):

```bash
claude mcp add gris \
  --env GRIS_URL=https://<seu-site> \
  --env GRIS_API_KEY=<api_key> \
  --env GRIS_API_SECRET=<api_secret> \
  -- python3 "$(pwd)/gris_mcp.py"
```

## Testar na mão

```bash
export GRIS_URL=https://<seu-site> GRIS_API_KEY=... GRIS_API_SECRET=...

printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"quem_sou_eu","arguments":{}}}' \
  | python3 gris_mcp.py
```

Logs vão para `stderr`; `stdout` é exclusivo do protocolo MCP.

## Testes automatizados

```bash
python3 -m unittest discover -s tests
```

Um servidor HTTP local finge ser o site do GRIS, cobrindo o caminho completo:
mensagem MCP → chamada HTTP autenticada → resposta MCP.
