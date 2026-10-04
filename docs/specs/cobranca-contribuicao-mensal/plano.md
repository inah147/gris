# Plano técnico — Cobrança da contribuição mensal pelo link do GRIS

> Origem: os slides "Fluxo" e "Envio de link" do fluxo de contribuição mensal, comparados com o
> que o código faz hoje (04/10/2026). Este plano fecha as diferenças.

## 1. Visão geral

O WhatsApp deixa de levar o link da InfinitePay e passa a levar sempre o mesmo link do GRIS,
um por beneficiário. A página desse link mostra o mês a mês e é ela que entrega o link da
InfinitePay, já com o valor do dia. É isso que resolve o "novo link no dia 11" do slide: o
link enviado não muda, o valor cobrado sim.

```
dia 1, 9h   job emite a cobrança do mês ──► WhatsApp: gris.../contribuicao/<hash>
                                                          │
vencimento  lembrete do dia                               ▼
dia seguinte  mês vira Atrasado + acréscimo      página pública (sem login)
              aviso de atraso                     ├─ meses pagos / a pagar, com valor
+7, +14…    lembretes semanais até o fim do mês   ├─ "Realizar pagamento" ─► link InfinitePay
                                                  │     (reaproveita ou emite com o valor atual)
webhook InfinitePay ─► baixa no extrato           └─ "Acessar comprovante" (meses pagos por link)
                     ─► WhatsApp de confirmação
mês seguinte  o ciclo recomeça; atrasados entram na mesma página e no mesmo pagamento
```

## 2. Decisões

| Tema | Decisão |
|---|---|
| Hash do link | Fixo por beneficiário; o gestor pode regenerar. |
| Acréscimo de atraso | Automático no dia seguinte ao vencimento; vale até o mês ser pago. O gestor ainda pode editar o valor. |
| Não pagou até o fim do mês | Segue automático: no dia 1 seguinte sai a mensagem normal e a página cobra tudo o que está em aberto. |
| Entrada do novato | Só respeitar a carência na geração mensal. O aviso do dia 20 ao financeiro fica fora. |
| Link antigo pago após o vencimento, pelo valor antigo | Quita o mês, marca como pago em atraso e sinaliza ao gestor. |
| Atrasados existentes na implantação | Sem acréscimo retroativo: só meses que vencerem a partir da data configurada. |
| Vencimento | Continua no próximo dia útil; a mensagem mostra a data real. |
| Família com mais de um beneficiário | Um link e uma mensagem por beneficiário, como hoje. |
| Pagamento por PIX direto ou baixa manual | Não gera comprovante nem mensagem de confirmação. |

## 3. Limites da InfinitePay

A API de checkout só cria link (`POST /links`) e consulta pagamento (`POST /payment_check`),
além do webhook. O valor é fixado na criação. Não há como editar, cancelar ou expirar um link,
e a documentação não diz se ele expira sozinho nem se aceita dois pagamentos. Consequências:

- "Aumentar o valor" é sempre emitir um link novo; o antigo continua pagável.
- O link da InfinitePay não pode circular fora da página (ver 5.3 e 6.1).
- O webhook precisa tratar o pagamento que chega pelo valor antigo (ver 4.3).

A confirmar por e-mail com a InfinitePay (parcerias@cloudwalk.io): validade do link e segundo
pagamento do mesmo link.

A documentação atual usa `https://api.checkout.infinitepay.io/links`; o código usa
`https://api.infinitepay.io/invoices/public/checkout/links`
(`cobranca_infinitepay.py`). Conferir na etapa 3 se o endereço antigo segue aceito.

## 4. Etapas

Cada etapa é um PR próprio e pode ir para produção sozinha.

### 4.1 Etapa 1 — Carência na geração mensal

Arquivo: `gris/api/financeiro/monthly_payments.py`.

- `generate_monthly_payments` pula o associado cujo início do pagamento é posterior ao mês de
  referência. O início sai de `resolver_inicio_do_pagamento`
  (`gris/api/financeiro/contribuicoes.py`): `inicio_do_pagamento` do cadastro ou ingresso mais
  a carência do tipo de registro (provisório 2 meses, definitivo 1).
- As datas de ingresso vêm de `get_datas_de_ingresso` numa consulta só, e os parâmetros de
  `get_parametros`.
- Sem ingresso e sem início no cadastro, o registro continua sendo gerado, como hoje.
- `definir_pagamento` (tela e MCP) não muda: o gestor pode criar o mês à mão.
- Script somente leitura em `gris/scripts/` que lista os `Pagamento Contribuicao Mensal` já
  gerados dentro da carência, para o financeiro decidir o que apagar. Nada é apagado
  automaticamente.

Testes: provisório e definitivo dentro e fora da carência; início manual prevalece; sem
ingresso continua gerando.

### 4.2 Etapa 2 — Acréscimo automático

Arquivos: `monthly_payments.py`, DocTypes `Pagamento Contribuicao Mensal` e
`Configuracoes Contribuicao Mensal`.

- Novo campo `acrescimo_atraso` (Currency, somente leitura) no `Pagamento Contribuicao Mensal`.
  O `valor` passa a ser base mais acréscimo; o campo existe para a página dizer quanto é o
  acréscimo e para o gestor conseguir desfazer.
- Novo campo `acrescimo_automatico_desde` (Date) em `Configuracoes Contribuicao Mensal`. Vazio
  desliga o acréscimo automático. Meses de referência anteriores a ele nunca recebem acréscimo.
- `update_status_monthly_payment`:
  - passa a tratar qualquer mês "Em Aberto" cujo vencimento já passou, não só o corrente;
  - ao marcar "Atrasado", soma `ParametrosContribuicao.acrescimo_atraso` ao `valor` e grava em
    `acrescimo_atraso`, se o mês está dentro da data configurada;
  - só age na transição "Em Aberto" → "Atrasado", então rodar de novo não soma duas vezes.
- A tela do contribuinte mostra o acréscimo ao lado do valor do mês.

Testes: transição aplica o acréscimo uma vez; mês anterior à data configurada não recebe;
valor próprio no cadastro recebe o mesmo acréscimo; mês antigo em aberto é alcançado.

### 4.3 Etapa 2b — Baixa: pago em atraso e link antigo

Arquivos: `gris/api/financeiro/cobranca_contribuicao.py`,
`gris/financeiro/doctype/transacao_extrato_geral/transacao_extrato_geral.py`.

- `_competencias_da_baixa` calcula `em_atraso` pela situação do mês na hora do pagamento
  (`status == "Atrasado"` ou `atrasou`), não pelo que o item da cobrança guardou na emissão.
- `_upsert_pagamento_contribuicao_mensal` nunca rebaixa `atrasou` de 1 para 0.
- Pagamento menor que o devido (link emitido antes do vencimento, pago depois):
  - o mês é quitado e fica com `atrasou = 1`;
  - novo campo `diferenca_nao_cobrada` (Currency) no `Pagamento Contribuicao Mensal` guarda
    quanto faltou;
  - a tela do contribuinte e a lista de cobranças do mês mostram o aviso "pago R$ X a menos
    pelo link antigo";
  - `frappe.log_error` registra a cobrança e o associado.

Testes: link do dia 1 pago no dia 20 fica como pago em atraso; link de R$ 60 pago quando o
mês vale R$ 70 quita, grava a diferença e aparece no resumo.

### 4.4 Etapa 3 — Página pública `/contribuicao/<hash>`

Arquivos novos: `gris/www/contribuicao/index.{py,html,css,js}`,
`gris/api/financeiro/contribuicao_publica.py`. Alterados: `Associado` (DocType), `hooks.py`,
`cobranca_contribuicao.py`, `gris/www/financeiro/contribuicao.{py,html,js}`.

**Token**

- Campo `token_contribuicao` no `Associado`: Data, único, somente leitura, `permlevel` 3.
- `obter_token(associado)` gera com `frappe.generate_hash(length=32)` no primeiro uso.
- `regenerar_token(associado)`, restrito ao Gestor Contribuição Mensal, invalida o link antigo.
- Rota em `website_route_rules`: `/contribuicao/<token>` → `contribuicao`.

**Página** (seguir as skills `frappe-web-portal` e `gris-brand-guide`)

- Sem login, sem sidebar, com a logo do grupo. Token inválido devolve 404 com a mesma mensagem
  de página inexistente.
- Lê de `pagamentos_contribuicao.apurar_associados`, a mesma apuração da tela do financeiro.
- Mostra: nome do beneficiário; mês a mês dos últimos 12 meses, do mais recente ao mais
  antigo, com situação, valor e acréscimo; total pendente. Meses "Não gerado" não aparecem.
- Três estados do topo, como no slide:
  - em aberto dentro do prazo: texto com a data de vencimento e botão "Realizar pagamento";
  - vencido: texto com o acréscimo e botão "Realizar pagamento";
  - tudo pago: confirmação e "Acessar comprovante".
- Nenhum dado de contato (telefone, e-mail, CPF, responsável) aparece na página.

**Pagamento**

- Endpoint `iniciar_pagamento(token)`: `allow_guest=True`, só POST.
- `cobranca_vigente(associado)` em `cobranca_contribuicao.py`: se a cobrança pendente tem as
  mesmas competências e os mesmos valores do que está em aberto agora, devolve o link dela;
  senão chama `emitir_cobranca` e a anterior vira "Substituída".
- `emitir_cobranca` ganha `herdar_de`: a cobrança reemitida copia `origem`, `mes_emissao`,
  `ultimo_envio_whatsapp` e `lembretes_enviados` da substituída, para o job não reenviar a
  mensagem do dia 1 nem reiniciar os lembretes.
- `redirect_url` da cobrança aponta para a própria página. Ao voltar da InfinitePay, a página
  confere o status no padrão de `gris/www/festas/convite_confirmado.js`.

**Segurança**

- `no_cache`, `<meta name="robots" content="noindex">` e `Referrer-Policy: no-referrer`, para
  o token não vazar no `Referer` ao sair para a InfinitePay.
- Limite de requisições por IP na página e no endpoint (`frappe.rate_limiter`).
- O endpoint não aceita parâmetro além do token: competências e valores vêm da apuração.
- `# nosemgrep` com justificativa nos `allow_guest`, como nos endpoints públicos existentes.

**Tela do gestor**

- Tela do contribuinte: "Copiar link da família" e "Regenerar link".

Testes: token inválido dá 404; página não expõe contato; reaproveita link quando nada mudou;
reemite quando o valor mudou; reemissão herda os carimbos; e2e da página nos três estados.

### 4.5 Etapa 4 — Mensagens e lembretes

Arquivos: `cobranca_contribuicao.py`, `cobranca_contribuicao_automatica.py`, DocTypes
`Configuracoes Contribuicao Mensal` e `Cobranca Infinitepay`.

- Mensagens passam a levar o link do GRIS, nunca o da InfinitePay:
  - cobrança do mês: beneficiário, data real do vencimento e aviso de que o valor sobe depois;
    quando há meses atrasados, diz quantos e o total;
  - lembrete do vencimento: "vence hoje";
  - aviso de atraso: valor novo com o acréscimo;
  - lembrete semanal.
- Calendário dos lembretes da cobrança do mês:

| Quando | Mensagem | Controle |
|---|---|---|
| Dia do vencimento | lembrete do vencimento | novo Check `lembrete_vencimento_enviado` na cobrança |
| Vencimento + 1 | aviso de atraso (1º lembrete) | `lembretes_enviados` |
| Vencimento + 1 + 7·(n−1) | n-ésimo lembrete | `lembretes_enviados < max_lembretes` |

- Os lembretes continuam valendo só para a cobrança do mês corrente; na virada do mês o ciclo
  recomeça com a mensagem do dia 1.
- Configuração: novo Check `lembrete_no_vencimento` (padrão ligado);
  `dias_lembrete_apos_vencimento` passa a ser o intervalo entre lembretes (padrão 7);
  `max_lembretes` padrão 3. Patch ajusta os valores de quem está com os padrões antigos.
- A regra atual segue: lembrete não sai se o mês foi quitado por outro meio.
- `resumo_cobrancas_do_mes` mostra o lembrete do vencimento junto dos demais.

Testes: cada mensagem sai no dia certo e uma vez só; nada depois do fim do mês; mensagens não
contêm o domínio da InfinitePay.

### 4.6 Etapa 5 — Comprovante

Arquivos: `cobranca_contribuicao.py`, DocType `Cobranca Infinitepay`, página pública.

- Depois de `lancar_baixa`, enfileira o envio da confirmação no WhatsApp com
  `enqueue_after_commit`, para a falha do WhatsApp não derrubar o webhook.
- Novo campo `comprovante_enviado_em` (Datetime) na cobrança: o envio acontece uma vez.
- A mensagem leva os meses quitados e o link do GRIS.
- A página mostra "Acessar comprovante" nos meses pagos por link, usando o `receipt_url` da
  cobrança depois de validado. `_is_safe_receipt_url` sai de
  `gris/api/festas/convite_confirmado.py` para um utilitário comum.

Testes: confirmação sai uma vez; falha do WhatsApp não desfaz a baixa; `receipt_url` inseguro
não vira link.

### 4.7 Etapa 6 — Alinhamento e documentação

- `gris/www/responsavel/contribuicoes.py` passa a usar `pagamentos_contribuicao`, a mesma
  apuração da tela do financeiro e da página pública, e o botão de pagar leva à página pública
  em vez do link da InfinitePay.
- Ferramentas MCP de cobrança (`gris/api/mcp/contribuicoes.py`): descrições e retornos passam
  a falar do link do GRIS. Atualizar `MCP_CLAUDE.md`.
- Evidências (prints da página e das mensagens) em `docs/evidencias/`.

## 5. Implantação

1. Etapas 1 e 2b podem entrar a qualquer momento: não mudam o que a família vê.
2. Etapa 2 entra com `acrescimo_automatico_desde` vazio. O financeiro define o mês de início
   depois de avisar as famílias.
3. Etapas 3 e 4 entram juntas no começo de um mês, antes do job do dia 1, para a primeira
   mensagem do mês já levar o link do GRIS.
4. Etapa 5 depois que a página estiver em uso.

Em cada PR: `gris-test contribuicao` e `gris-lint`.

## 6. Riscos

### 6.1 Link antigo da InfinitePay
Quem abriu o checkout antes do vencimento e paga depois, pela aba antiga, paga o valor antigo.
Não há como impedir pela API. O tratamento é o da etapa 2b: quita e sinaliza ao gestor.

### 6.2 Token no link
Quem tem o link vê o nome do beneficiário e a situação dos pagamentos. A página não expõe
contato, o token tem 32 caracteres e o gestor pode regenerá-lo.

### 6.3 Meses já gerados dentro da carência
A etapa 1 só evita os novos. Os existentes dependem do script de conferência e da decisão do
financeiro; enquanto não forem tratados, entram na cobrança de quem tiver a cobrança ativada.

## 7. Fora do escopo

- Aviso do dia 20 ao financeiro com quem começa a pagar no mês seguinte.
- Escolha de quais meses pagar na página: o botão paga tudo o que está em aberto.
- Comprovante para pagamento por PIX direto ou baixa manual.
- Acréscimo retroativo sobre os atrasados existentes.
