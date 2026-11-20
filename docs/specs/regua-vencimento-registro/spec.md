# Spec — Régua de comunicação do vencimento do registro

> Status: em implementação · Branch: `feat/regua-vencimento-registro` · Plano técnico:
> [plano.md](plano.md) · Textos: [mensagens.md](mensagens.md)

## 1. Problema

O registro escoteiro vence uma vez por ano. Quem passa da validade não pode participar das
atividades, mas hoje ninguém avisa:

- O job diário `enviar_lembretes_vencimento_registro_associados` existe, mas não envia nada:
  `getdate(None)` devolve a data de hoje, então quem nunca foi avisado parece "já avisado hoje".
  A correção chegou a ser feita e foi revertida.
- O job não tem interruptor, não olha se a pessoa ainda está ativa no grupo, não grava no
  Log de Mensagem a quem a mensagem foi e não avisa os chefes de seção.
- Para o chefe, só resta descobrir o vencimento na hora da atividade.

Em 19/11/2026, no dev.gris, 169 dos 276 associados ativos estavam vencidos. As validades se
concentram em duas datas: 02/11, com 76, e 07/03, com 70.

## 2. Objetivo

Uma régua de mensagens de WhatsApp sobre o vencimento do registro, configurável em
**Configurações de Associados**, com três frentes:

1. **Associado ou família:** aviso antes, no dia e depois do vencimento, até renovar ou sair do
   grupo.
2. **Grupo de chefes de seção:** todo início de mês, a lista dos beneficiários que vencem no mês,
   por seção.
3. **Chefe de seção:** aviso direto sobre os beneficiários da própria seção, antes e logo depois
   do vencimento.

## 3. Escopo

### Dentro

| Envio | Para quem | Quando | Interruptor | Modelo |
|---|---|---|---|---|
| 30 dias antes | associado ou responsável | validade − 30 | `msg_venc_30` | `modelo_venc_30` |
| 7 dias antes | associado ou responsável | validade − 7 | `msg_venc_7` | `modelo_venc_7` |
| 1 dia antes | associado ou responsável | validade − 1 | `msg_venc_1` | `modelo_venc_1` |
| No dia | associado ou responsável | validade | `msg_venc_0` | `modelo_venc_0` |
| Recorrente | associado ou responsável | validade + N, + 2N… (N = 3) | `msg_venc_recorrente` | `modelo_venc_recorrente` |
| Resumo do mês | grupo de chefes de seção | dia 1 | `msg_venc_grupo_mensal` | `modelo_venc_grupo_mensal` |
| Chefe, 30 dias | chefe da seção do beneficiário | validade − 30 | `msg_venc_chefe_30` | `modelo_venc_chefe_30` |
| Chefe, 7 dias | chefe da seção do beneficiário | validade − 7 | `msg_venc_chefe_7` | `modelo_venc_chefe_7` |
| Chefe, vencido | chefe da seção do beneficiário | validade + 1 | `msg_venc_chefe_pos` | `modelo_venc_chefe_pos` |

Além da tabela:

- Um interruptor geral, `regua_vencimento_ativa`, liga e desliga a régua inteira.
- Todos os textos podem ser editados na tela de configurações.

### Fora (desta versão)

- **Aviso ao papel "Gestor de Associados" no dia do vencimento.** Existia no job antigo, mas
  nunca chegou a sair.
- **Confirmação de renovação.** O GRIS só sabe que houve renovação quando a importação do Paxtu
  traz a validade nova, então não há mensagem de "recebemos sua renovação".
- **Envio por e-mail.**
- **Histórico de envios na tela do Associado.** O registro fica no Log de Mensagem, ligado ao
  associado.

## 4. Definições

- **d:** dias até o vencimento, `validade_registro − hoje`. É negativo depois que o registro
  venceu.
- **Ativo:** `Associado.status_no_grupo = "Ativo"`.
- **Menor:** quem ainda não fez 18 anos, contados pela `data_de_nascimento`. Beneficiário sem
  data de nascimento conta como menor; qualquer outra categoria sem a data conta como adulto.
- **Corte:** `cobrar_vencidos_desde`. Validades anteriores a esta data não recebem nada a partir
  do dia do vencimento.
- **Validade de referência:** a validade a que os carimbos de envio se referem. Se a
  `validade_registro` mudar, a régua recomeça do zero.

## 5. Requisitos funcionais

Cada critério de aceite (CA) tem um teste correspondente na
[matriz do plano](plano.md#5-matriz-de-validação).

### RF-01 — Interruptores

- **CA-01.1** Com `regua_vencimento_ativa = 0`, o job diário não envia nada. O resumo do job
  registra "Régua de vencimento desligada nas configurações de associados."
- **CA-01.2** Cada um dos nove `msg_venc_*` desmarcado suspende só o seu envio; os outros seguem
  saindo.
- **CA-01.3** Um `msg_venc_*` que nunca foi gravado no `tabSingles` conta como ligado.
- **CA-01.4** Num site novo, ou logo depois do patch, o interruptor geral fica desligado e os
  nove individuais ficam ligados.
- **CA-01.5** Salvar as configurações com o geral ligado e sem data de corte é recusado, com a
  mensagem pedindo a data.

### RF-02 — Régua do associado

- **CA-02.1** Os marcos têm a ordem `30 → 7 → 1 → 0 → recorrente`. Um marco está devido quando:
  30 com d ≤ 30, 7 com d ≤ 7, 1 com d ≤ 1, 0 com d ≤ 0, e recorrente com d ≤ −N.
- **CA-02.2** Em cada rodada sai no máximo uma mensagem por associado: a do marco devido mais
  adiantado, e só se ele vier depois do último já enviado. Exemplo: com validade importada já a
  5 dias do vencimento, sai só a de 7 dias, que mostra a data real. A de 30 dias não sai.
- **CA-02.3** Cada um dos marcos 30, 7, 1 e 0 sai no máximo uma vez para cada validade de
  referência.
- **CA-02.4** O recorrente sai com d ≤ −N e, além disso, pelo menos N dias depois do último
  envio. Assim, com N = 3, sai em d = −3, −6, −9…
- **CA-02.5** Com d > 30 nada sai.
- **CA-02.6** Os carimbos (`regua_validade_referencia`, `regua_ultimo_marco`,
  `regua_ultimo_envio`) só são gravados depois que o envio é confirmado. Um envio que falhou não
  carimba, e o associado é tentado de novo na rodada seguinte.
- **CA-02.7** Rodar o job duas vezes no mesmo dia não manda nada a mais.

### RF-03 — Quando a régua para

- **CA-03.1** Associado Inativo não recebe nada, e nenhum carimbo dele é alterado.
- **CA-03.2** Se a `validade_registro` mudar para uma data diferente da validade de referência,
  a régua recomeça. Uma validade nova a mais de 30 dias não manda nada.
- **CA-03.3** Validade anterior ao corte não recebe os marcos 0 e recorrente, nem o aviso de
  vencido ao chefe. Os marcos 30, 7 e 1 já ficaram no passado.

### RF-04 — Destinatário

- **CA-04.1** Para o menor, o destinatário é o primeiro que tiver telefone nesta ordem: o
  responsável vinculado que é guardião legal, o primeiro responsável vinculado, o
  `telefone_responsavel_1` do associado e, por fim, o `telefone` do próprio associado.
- **CA-04.2** O adulto recebe no próprio `telefone`.
- **CA-04.3** Sem telefone, o associado é pulado. A métrica `sem_telefone` é incrementada e nada
  é carimbado.
- **CA-04.4** Na mensagem, `{registro_de}` vira "seu registro escoteiro" quando quem recebe é o
  próprio associado, e "o registro escoteiro de Ana" quando é o responsável.

### RF-05 — Aviso direto ao chefe de seção

- **CA-05.1** Entram só os Beneficiários ativos. Os marcos são 30 (d ≤ 30), 7 (d ≤ 7) e vencido
  (d ≤ −1, com validade a partir do corte), cada um no máximo uma vez para cada validade de
  referência, e sai só o mais adiantado que estiver devido.
- **CA-05.2** Os chefes de uma seção são encontrados pela regra de `gris/utils/chefes.py`: a
  seção é comparada sem acento nem maiúsculas, e quando a seção não tem chefe, vale o ramo.
  Chefe sem telefone é descartado.
- **CA-05.3** Cada chefe recebe no máximo uma mensagem por dia, mesmo quando há vários
  beneficiários, marcos e seções. A mensagem tem um bloco para cada par de marco e seção.
- **CA-05.4** Quando a seção tem dois chefes, os dois recebem.
- **CA-05.5** O carimbo do beneficiário (`regua_chefe_ultimo_marco`) é gravado se ao menos um
  chefe recebeu.
- **CA-05.6** Um beneficiário cuja seção não tem chefe localizado conta na métrica `sem_chefe` e
  não é carimbado.

### RF-06 — Resumo mensal ao grupo de chefes

- **CA-06.1** Na primeira rodada do mês, sai uma mensagem para o grupo
  `grupo_chefes_whatsapp` com os Beneficiários ativos cuja validade cai no mês corrente.
- **CA-06.2** Os beneficiários são agrupados pela seção normalizada, exibida com a primeira
  grafia encontrada. As seções vêm em ordem alfabética, com "Sem seção" por último, e dentro de
  cada seção a ordem é por data e depois por nome.
- **CA-06.3** O título de cada seção menciona os chefes dela, com `@número` no texto e o número
  no campo `mencionar`.
- **CA-06.4** Depois do envio, `resumo_mensal_enviado_em` guarda o mês (`AAAA-MM`). Uma nova
  rodada no mesmo mês não manda de novo.
- **CA-06.5** Mês sem nenhum vencimento não gera mensagem, mas o mês é carimbado mesmo assim.
- **CA-06.6** Sem grupo configurado, nada sai e o resumo do job explica o motivo.

### RF-07 — Modelos de mensagem

- **CA-07.1** Os nove textos são campos editáveis em Configurações de Associados, e cada um
  aceita só as variáveis listadas para ele (ver [mensagens.md](mensagens.md)).
- **CA-07.2** Salvar um modelo com uma variável fora da lista é recusado, com a mensagem
  dizendo qual variável e quais são as permitidas.
- **CA-07.3** As variáveis são trocadas por substituição simples. Nenhuma expressão é avaliada:
  `{x.__class__}` e `{{ frappe }}` aparecem no texto como foram escritos e são recusados no save.
- **CA-07.4** Modelo vazio usa o texto padrão do código.
- **CA-07.5** Toda mensagem termina com o aviso de "já renovado" (`texto_ja_renovado`, editável)
  e com a linha fixa "🤖 _Esta é uma mensagem automática do GRIS._". A linha fixa não é
  editável e nenhum modelo consegue tirá-la.
- **CA-07.6** A tela tem "Pré-visualizar", que renderiza o modelo com dados fictícios e com o
  rodapé, e "Restaurar padrão".

### RF-08 — Rastreabilidade

- **CA-08.1** Todo envio cria um `Log de Mensagem` com `associado`, `assunto` e
  `destinatario_tipo`: "Associado", "Responsável do associado", "Chefe de seção" ou "Grupo de
  chefes de seção".
- **CA-08.2** O Monitor de Jobs mostra quantos foram avaliados, quantos enviados e quantos
  pulados, cada motivo numa métrica: `sem_telefone`, `sem_chefe`, `desativado` e `falhas_no_envio`.

### RF-09 — Aviso manual

- **CA-09.1** O botão "Avisar Vencimento" na ficha do Associado manda na hora o modelo do marco
  atual, mesmo com a régua desligada, e não grava carimbo.
- **CA-09.2** Com o registro a mais de 30 dias do vencimento, o botão usa o modelo de 30 dias,
  com os dias reais.
- **CA-09.3** Quando o registro já venceu, o botão continua avisando os usuários com o papel
  "Gestor de Associados", como fazia antes.

## 6. Requisitos não funcionais

- **Volume.** O job agendado só enfileira o trabalho, que roda na fila `long`. O envio passa pela
  fila única do WhatsApp, com 4 a 6 segundos entre mensagens. Os destinatários são lidos de uma
  vez, sem consulta dentro do laço.
- **Falhas isoladas.** A falha de um associado não interrompe os demais, e cada associado é
  gravado (commit) separadamente.
- **Permissões.** Só System Manager edita as configurações, e os endpoints de pré-visualização
  também exigem o papel.
- **LGPD.** O Log de Mensagem guarda o texto enviado, como as outras mensagens já guardam.
