# Plano — OAuth no MCP do GRIS

Plano de execução para trocar a autenticação da integração MCP de **API key**
por **OAuth**, de modo que ela possa ser cadastrada como *connector* na conta do
Claude e passe a valer no Desktop, no claude.ai e em sessões remotas de uma vez
só — sem `claude mcp add` em cada máquina.

O levantamento do que existe e do que falta está em
[MCP_CLAUDE.md](MCP_CLAUDE.md#oauth-o-que-falta-para-virar-connector); este
arquivo não repete o diagnóstico, só organiza a execução.

## Resultado esperado

- Um `OAuth Client` no site atende o cliente MCP da Anthropic.
- O connector é cadastrado uma vez na conta e aparece nas três superfícies.
- A ponte stdio e o `claude mcp add` continuam funcionando (nada é removido
  neste plano — ver *Não-objetivos*).

## Fase 0 — A verificação que define o escopo

**Antes de escrever código.** Verificar se o cadastro de connector customizado
do claude.ai aceita **Client ID e Client Secret preenchidos à mão**.

| Resposta | Consequência |
|---|---|
| Aceita | A Fase 5 não existe. Basta um `OAuth Client` cadastrado no Desk. |
| Não aceita | A Fase 5 entra, e o esforço total aproximadamente dobra. |

Enquanto essa resposta não vier, as Fases 1 a 4 seguem válidas nos dois
cenários — não há motivo para esperar por ela para começar.

## Fase 1 — Metadados de descoberta e desafio de autenticação (concluída)

Módulo novo: `gris/api/mcp/oauth.py`. Só camada de protocolo; nenhuma regra de
negócio, no mesmo espírito de `gris/api/mcp/http.py`.

1. **`/.well-known/oauth-protected-resource`** (RFC 9728) — declara o recurso
   protegido e aponta o authorization server (o próprio site).
2. **`/.well-known/oauth-authorization-server`** (RFC 8414) — espelha o que
   `frappe.integrations.oauth2.openid_configuration` já devolve e **acrescenta**
   o que falta lá: `code_challenge_methods_supported` (sem ele o cliente não
   descobre que há PKCE), `grant_types_supported`,
   `token_endpoint_auth_methods_supported` e `scopes_supported`.
   Não alterar o `openid-configuration` do Frappe — os caminhos novos são do
   app, e mexer no do framework quebraria outros consumidores.
3. **`WWW-Authenticate` no 401** — numa chamada ao MCP sem token válido,
   responder `401` com
   `WWW-Authenticate: Bearer resource_metadata="<url do item 1>"`.

**Roteamento**: `gris/hooks.py` ainda não declara `website_redirects`; adicionar
o hook mapeando os dois caminhos `.well-known` para os métodos whitelisted do
módulo novo — é o mesmo mecanismo que o Frappe usa para o
`openid-configuration` (`frappe/hooks.py`).

**Header**: `frappe/app.py` expõe o hook `after_request`, que roda no `finally`
do ciclo de requisição (portanto também nas respostas de erro) e recebe o objeto
de resposta. É o ponto certo para acrescentar o `WWW-Authenticate`. **Restringir
ao caminho do MCP** — não faz sentido anunciar o recurso protegido em toda
resposta 401 do site.

**Validação**: testes em `gris/tests/test_mcp_oauth.py` cobrindo o conteúdo dos
dois documentos de descoberta (incluindo o anúncio de PKCE) e a presença do
header no 401 do endpoint MCP.

**Feito**: `gris/api/mcp/oauth.py` implementa os três itens;
`website_redirects` e `after_request` cadastrados em `gris/hooks.py`;
`gris-test test_mcp_oauth` e `gris-lint` limpos. O 403 que `is_whitelisted`
devolve pra Guest sem `Authorization` (o `validate_auth` só levanta 401
quando já existe um header `Bearer` malformado ou inválido) também vira 401
com o header — as duas situações são a mesma falta de credencial válida.

## Fase 2 — Cliente e escopo (validação de código concluída; cadastro é manual)

- Criar um escopo dedicado (ex. `gris.mcp`) em vez de reaproveitar `all`. O
  `validate_bearer_token` do Frappe confere o escopo do token contra os escopos
  do `OAuth Client`, então o escopo estreito de fato limita o token.
- Cadastrar o `OAuth Client` com `redirect_uri` **estrita** (sem curinga).
- Usuário do cliente com os papéis mínimos da tarefa. Vale lembrar o que o
  levantamento apontou: o provider do Frappe carrega o cliente sem conferir o
  `client_secret`, então **o PKCE é a única proteção real do fluxo** — a
  `redirect_uri` estrita deixa de ser higiene e vira controle de segurança.

**Validação**: um token emitido com o escopo novo autentica; um token com escopo
fora da lista do cliente não autentica.

**Feito**: `ESCOPO_MCP = "gris.mcp"` já definido em `gris/api/mcp/oauth.py` e
usado nos metadados da Fase 1. `TestEscopoDedicadoRestringeOToken` em
`gris/tests/test_mcp_oauth.py` prova a restrição contra o caminho real de
`validate_oauth`/`validate_bearer_token`: token com o escopo do cliente
autentica, token com escopo fora da lista (total ou parcialmente) não.

**Falta**: o cadastro em si do `OAuth Client` — de teste (Fase 3) e de
produção (Fase 4) — é uma ação no Desk, não código; não há fixture porque
o registro carrega segredo. Ver *Atenção ao registrar o cliente* em
MCP_CLAUDE.md para o que preencher.

## Fase 3 — Fluxo ponta a ponta local

Rodar o Authorization Code + PKCE completo contra `test.localhost`, do
`authorize` até uma chamada `tools/list` autenticada por Bearer. Confirmar que a
descoberta encadeia sozinha: `401` → metadados do recurso → metadados do
authorization server → autorização → token.

**Critério de pronto da fase**: o encadeamento funciona sem nenhuma URL
digitada à mão.

## Fase 4 — Produção e cadastro do connector

1. Deploy do app com as Fases 1 e 2.
2. Cadastrar o `OAuth Client` de produção (não reaproveitar o de teste).
3. Cadastrar o connector na conta e validar nas três superfícies.
4. Atualizar `MCP_CLAUDE.md`: instalação por connector como caminho
   recomendado, mantendo stdio e HTTP+header como alternativas.

**Atenção**: produção tem dados reais de associados, incluindo menores. O
primeiro cadastro deve usar um cliente de papéis mínimos, e só depois ampliar se
a tarefa exigir.

## Fase 5 — Dynamic Client Registration (condicional)

Só existe se a Fase 0 disser que o cadastro manual não serve. Implementa o
`registration_endpoint` (RFC 7591) e o anuncia nos metadados da Fase 1.

Ponto sensível: DCR permite que **qualquer um** registre um cliente no site.
Não subir sem decidir a política de proteção (restrição por `redirect_uri`,
token de registro, ou aprovação manual).

## Riscos

| Risco | Mitigação |
|---|---|
| Fase 0 responder "não aceita" tarde e reabrir o escopo | Verificar antes da Fase 1; as Fases 1–4 valem nos dois casos |
| `WWW-Authenticate` vazar para todo 401 do site | Restringir o `after_request` ao caminho do MCP e testar um 401 de outra rota |
| Divergência entre a revisão da spec MCP implementada e a que o cliente espera | `gris/api/mcp/http.py` declara `2025-06-18`; confirmar a revisão alvo na Fase 0 |
| Escopo `all` num cliente exposto à internet | Fase 2 antes da Fase 4 — não cadastrar connector com `all` |

## Não-objetivos

- Remover a ponte stdio ou o `claude mcp add`: continuam suportados.
- Alterar o catálogo de ferramentas, as regras de papel ou `gris/api/mcp/registry.py`.
- Alterar `gris/api/mcp/http.py`: já está provado que o endpoint aceita Bearer
  sem mudança (`gris/tests/test_mcp_oauth.py`).
- Mexer no provider OAuth do Frappe. O que falta é acrescentado pelo app.

## Critério de pronto

- Connector cadastrado e funcionando nas três superfícies.
- Descoberta encadeando sem URL digitada à mão.
- Cliente de produção com escopo dedicado e `redirect_uri` estrita.
- `gris-test` e `gris-lint` limpos.
- `MCP_CLAUDE.md` atualizado.
