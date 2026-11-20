# Mensagens — régua de vencimento do registro

> Parte da [spec](spec.md). Estes são os **textos padrão**. Cada um pode ser editado em
> **Configurações de Associados › Régua de vencimento do registro**. Se o campo ficar vazio, vale
> o texto padrão.

## Como a mensagem é montada

```
[modelo editável, com as variáveis já trocadas]

[texto "já renovado" — editável em texto_ja_renovado]

🤖 _Esta é uma mensagem automática do GRIS._        ← fixo, não editável
```

- Variáveis no formato `{nome}`. Cada modelo aceita só as variáveis da sua tabela. Uma variável
  fora da lista bloqueia o save.
- Não há código no texto: `{x.__class__}` ou `{{ ... }}` não são avaliados. São recusados no save.
- Uma variável que fica vazia, como `{contato_duvidas}` sem administrativo configurado, some.
  As linhas em branco que sobram são compactadas.
- `*negrito*` e `_itálico_` são formatação do próprio WhatsApp.

### Rodapé

Texto padrão de `texto_ja_renovado`:

```
_Se o registro já foi renovado, pode desconsiderar esta mensagem: a renovação aparece no GRIS na próxima atualização do Paxtu._
```

Seguido sempre da linha fixa:

```
🤖 _Esta é uma mensagem automática do GRIS._
```

### Instruções de renovação

`instrucoes_renovacao` vira a variável `{como_renovar}`. Texto padrão, **a confirmar com o
administrativo**:

```
A renovação é feita pelo Paxtu (paxtu.escoteiros.org.br).
```

## 1. Associado ou responsável

### Variáveis

| Variável | Exemplo (adulto) | Exemplo (responsável de menor) |
|---|---|---|
| `{primeiro_nome_destinatario}` | Carlos | Mariana |
| `{nome_associado}` | Carlos Pereira | Ana Souza |
| `{primeiro_nome_associado}` | Carlos | Ana |
| `{registro_de}` | seu registro escoteiro | o registro escoteiro de Ana |
| `{data_vencimento}` | 02/11/2027 | 02/11/2027 |
| `{dias_restantes}` | 30 | 30 |
| `{dias_vencido}` | 0 | 0 |
| `{numero_registro}` | 1234567-8 | 1234567-8 |
| `{como_renovar}` | (instruções de renovação) | (idem) |
| `{contato_duvidas}` | Dúvidas sobre a renovação? Fale com a Joana, do administrativo, pelo telefone +55 11 91234-5678. | (idem) |

`{contato_duvidas}` usa o responsável administrativo de Configurações de Recepção. Sem ele, ou sem
telefone, a variável fica vazia.

### 30 dias antes — `modelo_venc_30`

```
Olá, {primeiro_nome_destinatario}!

Passando para lembrar que {registro_de} vence em *{data_vencimento}*, daqui a {dias_restantes} dias.

Com o registro em dia, a participação nas atividades e o seguro escoteiro continuam garantidos. {como_renovar}

{contato_duvidas}
```

### 7 dias antes — `modelo_venc_7`

```
Olá, {primeiro_nome_destinatario}!

Falta uma semana: {registro_de} vence em *{data_vencimento}*.

Para não ficar de fora das atividades, faça a renovação nos próximos dias. {como_renovar}

{contato_duvidas}
```

### 1 dia antes — `modelo_venc_1`

```
Olá, {primeiro_nome_destinatario}!

Amanhã, *{data_vencimento}*, vence {registro_de}. Ainda dá tempo de renovar hoje. {como_renovar}

{contato_duvidas}
```

### No dia — `modelo_venc_0`

```
Olá, {primeiro_nome_destinatario}!

Hoje, *{data_vencimento}*, vence {registro_de}. Sem a renovação, a participação nas atividades fica suspensa. {como_renovar}

{contato_duvidas}
```

### A cada 3 dias depois de vencer — `modelo_venc_recorrente`

```
Olá, {primeiro_nome_destinatario}!

Lembrete: {registro_de} está vencido desde *{data_vencimento}* (há {dias_vencido} dias). Enquanto não for renovado, a participação nas atividades fica suspensa. {como_renovar}

{contato_duvidas}
```

### Exemplo renderizado (responsável, 7 dias)

```
Olá, Mariana!

Falta uma semana: o registro escoteiro de Ana vence em *09/11/2027*.

Para não ficar de fora das atividades, faça a renovação nos próximos dias. A renovação é feita pelo Paxtu (paxtu.escoteiros.org.br).

Dúvidas sobre a renovação? Fale com a Joana, do administrativo, pelo telefone +55 11 91234-5678.

_Se o registro já foi renovado, pode desconsiderar esta mensagem: a renovação aparece no GRIS na próxima atualização do Paxtu._

🤖 _Esta é uma mensagem automática do GRIS._
```

## 2. Resumo mensal ao grupo de chefes — `modelo_venc_grupo_mensal`

### Variáveis

| Variável | Exemplo |
|---|---|
| `{mes}` | dezembro de 2026 |
| `{quantidade}` | 3 |
| `{lista_por_secao}` | ver abaixo |

`{lista_por_secao}` é montada pelo código. Cada seção traz no título as menções aos seus chefes:

```
*Alcateia Seeonee* @5511988887777
• 05/12 — Ana Souza
• 18/12 — Bruno Lima

*Tropa Escoteira Anhanguera* @5511977776666
• 30/12 — Carla Dias
```

### Texto padrão

```
📋 *Registros de beneficiários que vencem em {mes}*

{lista_por_secao}

Total: {quantidade}. As famílias recebem os lembretes automáticos; vale reforçar nas atividades.
```

## 3. Chefe de seção (mensagem direta)

Cada chefe recebe **no máximo uma mensagem por dia**. A mensagem é montada assim:

```
Olá, {primeiro_nome_chefe}!                 ← fixo

[bloco de cada marco e seção do dia, separados por linha em branco]

[rodapé]
```

### Variáveis dos blocos

| Variável | Exemplo |
|---|---|
| `{primeiro_nome_chefe}` | Rafael |
| `{secao}` | Alcateia Seeonee |
| `{quantidade}` | 2 |
| `{lista_beneficiarios}` | `• Ana Souza (Lobinho) — vence em 05/12/2026` (uma linha por beneficiário; no bloco de vencidos, "venceu em") |

### 30 dias antes — `modelo_venc_chefe_30`

```
📅 *{secao}: registros que vencem em cerca de 30 dias*
{lista_beneficiarios}
Vale lembrar as famílias nas próximas atividades.
```

### 7 dias antes — `modelo_venc_chefe_7`

```
⏳ *{secao}: registros que vencem na próxima semana*
{lista_beneficiarios}
```

### 1 dia depois — `modelo_venc_chefe_pos`

```
⚠️ *{secao}: registros vencidos*
{lista_beneficiarios}
Enquanto não regularizarem o registro, esses jovens não podem participar das atividades.
```

### Exemplo renderizado (dois marcos no mesmo dia)

```
Olá, Rafael!

📅 *Alcateia Seeonee: registros que vencem em cerca de 30 dias*
• Ana Souza (Lobinho) — vence em 19/12/2026
Vale lembrar as famílias nas próximas atividades.

⚠️ *Alcateia Seeonee: registros vencidos*
• Bruno Lima (Lobinho) — venceu em 18/11/2026
Enquanto não regularizarem o registro, esses jovens não podem participar das atividades.

_Se o registro já foi renovado, pode desconsiderar esta mensagem: a renovação aparece no GRIS na próxima atualização do Paxtu._

🤖 _Esta é uma mensagem automática do GRIS._
```
