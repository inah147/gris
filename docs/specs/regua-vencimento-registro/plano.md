# Plano técnico — Régua de vencimento do registro

> Spec: [spec.md](spec.md) · Textos: [mensagens.md](mensagens.md)

## 1. Ponto de partida

| Peça | Hoje | Depois |
|---|---|---|
| `gris/api/associados_vencimento_notificacoes.py` | Marcos 30/7/0. Não envia nada: `getdate(None)` devolve hoje. Sem interruptor, sem `contexto`, ignora `status_no_grupo`. | Reescrito como a régua da spec. O caminho do hook e o botão manual continuam os mesmos. |
| `Associado` | `data_notificacao_vencimento_30_dias`, `_7_dias` e `data_notificacao_vencimento` | Saem do JSON (a coluna fica). Entram `regua_validade_referencia`, `regua_ultimo_marco`, `regua_ultimo_envio` e `regua_chefe_ultimo_marco`. |
| `Configuracoes de Associados` | 3 campos | Ganha a aba "Régua de vencimento" com o geral, o corte, o intervalo, o grupo, os 9 interruptores e os 9 modelos. |
| `Log de Mensagem` | Só aponta para `Novo Associado` | Ganha o Link `associado` e três tipos de destinatário. |
| `gris/utils/chefes.py` | Chefes por seção, só os `name`; por ramo, com telefone | Ganha `contatos_chefes_por_secao`: só chefes ativos, uma consulta. |

## 2. Decisões técnicas

| Tema | Decisão |
|---|---|
| Quando cada marco sai | Função pura `marco_devido`. O marco é calculado a partir de `d` e do último marco enviado, não pela igualdade exata de dias. Assim, um dia perdido é recuperado sem acumular atraso. |
| Carimbos | Ficam no próprio `Associado`, com `update_modified=False`, e são gravados só depois do envio síncrono confirmado (`enviar_texto(..., enqueue=False)`), com um commit por associado. É o padrão de `enviar_cobranca`. |
| Fila | O cron das 9h só enfileira `executar_regua` na fila `long`, com timeout de 3600 s. A fila única do WhatsApp espaça os envios em 4 a 6 s. |
| Interruptores | Leitura crua do `tabSingles`, como em `_mensagem_habilitada`: o campo ausente conta como ligado. O geral é a exceção e lê 0 quando ausente, para a régua não ser ligada sem querer. |
| Modelos | Substituição com `re.sub(r"\{(\w+)\}")` sobre um dicionário fechado, sem `str.format` e sem Jinja. A validação no `validate` do Single recusa variável desconhecida e `{{`/`{%`. |
| Rodapé | É a constante `ASSINATURA_AUTOMATICA`, anexada pelo código depois de `texto_ja_renovado`, fora dos campos editáveis. |
| Chefes | `_candidatos_a_chefe(apenas_ativos=True)` uma vez por rodada. O casamento é por seção normalizada, com o ramo como reserva (`chefes_entre_candidatos`). Chefe sem telefone fica de fora. |
| Resumo mensal | Roda dentro da mesma rodada diária. O carimbo `AAAA-MM` em `resumo_mensal_enviado_em` evita repetir no mês e recupera um dia 1 perdido. |
| Botão manual | Usa os modelos e o marco "natural" de `d`, sem carimbo, e funciona com a régua desligada. Mantém o aviso aos gestores quando já venceu, como fazia antes. |

## 3. Etapas

Cada etapa é um commit na branch `feat/regua-vencimento-registro`.

### 3.1 Spec

Este diretório.

### 3.2 Schema e patch

- **`configuracoes_de_associados.json`**: nova Tab Break "Régua de vencimento do registro".
  - Seção "Geral":
    - `regua_vencimento_ativa` (Check, padrão 0)
    - `cobrar_vencidos_desde` (Date)
    - `intervalo_recorrente_dias` (Int, padrão 3)
    - `grupo_chefes_whatsapp` (Select)
    - `instrucoes_renovacao` (Small Text)
    - `texto_ja_renovado` (Small Text)
    - `resumo_mensal_enviado_em` (Data, read-only)
  - Três seções de mensagens, uma para cada público: "Associado ou responsável", "Grupo de chefes" e
    "Chefe de seção". Cada mensagem tem um Check `msg_venc_*` (padrão 1) e um Long Text `modelo_venc_*`
    com `depends_on` no Check.
- **`associado.json`**: seção recolhida "Régua de vencimento" logo depois de `validade_registro`, com os
  quatro campos read-only. Os três `data_notificacao_*` saem do JSON.
- **`log_de_mensagem.json`**: Link `associado`; novas opções em `destinatario_tipo`: "Associado",
  "Responsável do associado" e "Chefe de seção".
- **Patch** `gris.patches.preparar_regua_de_vencimento`:
  - grava os textos padrão nos modelos vazios, em `texto_ja_renovado` e em `instrucoes_renovacao`;
  - liga os 9 `msg_venc_*` e põe o intervalo em 3;
  - não toca no geral nem no corte.

### 3.3 Modelos

Novo arquivo `gris/api/associados_vencimento_modelos.py`.

- **`MODELOS_PADRAO`, `VARIAVEIS_POR_MODELO`, `TEXTO_JA_RENOVADO_PADRAO`, `INSTRUCOES_RENOVACAO_PADRAO` e
  `ASSINATURA_AUTOMATICA`**: os textos padrão, as variáveis aceitas por modelo e o rodapé fixo.
- **`variaveis_desconhecidas(campo, texto) -> list[str]`** e **`validar_configuracoes(doc)`**: chamadas
  no `validate` de `ConfiguracoesdeAssociados`.
- **`modelo_configurado(campo) -> str`**: o texto do Single, ou o padrão quando o campo está vazio.
- **`substituir(texto, valores) -> str`**: troca as variáveis, apaga as que estão vazias e compacta as
  linhas em branco.
- **`com_rodape(corpo) -> str`**: anexa `texto_ja_renovado` e a assinatura.
- **Endpoints whitelisted** (System Manager): `pre_visualizar_modelo(campo, texto)` e
  `modelo_padrao(campo)`.

### 3.4 Régua do associado e do chefe

Arquivo `gris/api/associados_vencimento_notificacoes.py`.

- **`marco_devido(d, ultimo_marco, ultimo_envio, hoje, validade, corte, intervalo)`** e
  **`marco_do_chefe(d, ultimo_marco, validade, corte)`**: funções puras.
- **`estado_vigente(associado)`**: zera o estado quando `regua_validade_referencia != validade_registro`.
- **`resolver_destinatario(associado, links, contatos, hoje)`**: menor → responsáveis →
  `telefone_responsavel_1` → `telefone`; adulto → `telefone`.
- **`enviar_lembretes_vencimento_registro_associados()`** (cron): confere o geral e enfileira
  `executar_regua`.
- **`executar_regua()`** chama, nesta ordem:
  1. `_avisar_associados`;
  2. `_avisar_chefes`;
  3. `_enviar_resumo_mensal`.
  - Cada passo grava métricas, e o resumo final junta os três.
- **`notificar_vencimento_manual`**: reescrita sobre os modelos.
- **`gris/utils/whatsapp.py`**: `_registrar_log` grava `contexto["associado"]`; o doctype entra em
  `DOCTYPES_COM_SELECT_DE_GRUPO`.
- **`gris/utils/chefes.py`**: `_candidatos_a_chefe(apenas_ativos=False)` e
  `contatos_chefes_por_secao(beneficiarios)`.

### 3.5 Desk

- **`configuracoes_de_associados.js`**:
  - carrega as opções de `grupo_chefes_whatsapp` com
    `listar_grupos_whatsapp_para_select({doctype: "Configuracoes de Associados"})`;
  - botão "Modelos" com o diálogo "Pré-visualizar / Restaurar padrão" por modelo;
  - lista as variáveis aceitas na descrição de cada modelo.
- **`associado.js`**: a confirmação do botão "Avisar Vencimento" passa a citar o modelo.

### 3.6 Testes, lint e evidências

`gris/tests/test_associados_vencimento_notificacoes.py` e `gris/tests/test_associados_vencimento_modelos.py`.

## 4. Implantação

1. Merge e deploy. O patch prepara os textos, e a régua continua desligada.
2. O administrativo confirma `instrucoes_renovacao` e revisa os textos usando a pré-visualização.
3. Escolhem o grupo de chefes e a data de corte. Sugestão: o primeiro dia do mês da implantação, para
   não disparar a mensagem recorrente para os 169 que já estavam vencidos.
4. Ligam a régua. A primeira rodada das 9h já manda os marcos devidos e o resumo do mês.

## 5. Matriz de validação

| CA | Teste |
|---|---|
| 01.1 | `TestReguaDoAssociado.test_geral_desligado_nao_envia_nada` |
| 01.2 | `TestReguaDoAssociado.test_interruptor_do_marco_suspende_so_o_marco`, `TestAvisoAosChefes.test_interruptor_do_marco_do_chefe`, `TestResumoMensal.test_interruptor_desligado` |
| 01.3 | `TestReguaDoAssociado.test_interruptor_ausente_conta_como_ligado` |
| 01.4 | `TestModelos.test_patch_prepara_textos_e_mantem_geral_desligado` |
| 01.5 | `TestModelos.test_geral_ligado_sem_corte_e_recusado` |
| 02.1–02.5 | `TestMarcoDevido` (tabela de dias, marco perdido, recorrente, d > 30) |
| 02.6 | `TestReguaDoAssociado.test_carimba_depois_do_envio`, `test_falha_no_envio_nao_carimba` |
| 02.7 | `TestReguaDoAssociado.test_segunda_rodada_no_dia_nao_reenvia` |
| 03.1 | `TestReguaDoAssociado.test_consulta_so_ativos` |
| 03.2 | `TestMarcoDevido.test_validade_nova_recomeca` |
| 03.3 | `TestMarcoDevido.test_corte`, `TestMarcoDoChefe.test_corte` |
| 04.1–04.4 | `TestDestinatario` |
| 05.1 | `TestMarcoDoChefe` |
| 05.2–05.6 | `TestAvisoAosChefes` |
| 06.1–06.6 | `TestResumoMensal` |
| 07.1–07.6 | `TestModelos` |
| 08.1 | `TestReguaDoAssociado.test_contexto_do_log`, `TestRegistroDoLog.test_grava_associado` |
| 08.2 | `TestReguaDoAssociado.test_metricas` |
| 09.1–09.2 | `TestAvisoManual` |

Além dos testes de unidade, há uma rodada no dev.gris com a Evolution simulada. Os textos de cada
mensagem são salvos em `docs/evidencias/regua-vencimento-registro/`, com nomes fictícios.

## 6. Riscos

- **Rajada:** 76 validades caem no mesmo dia. A fila única espaça os envios, o job roda na fila `long`, e
  os chefes recebem tudo consolidado em uma mensagem por dia.
- **Renovação percebida tarde:** o GRIS só fica sabendo da renovação na importação do Paxtu. É por isso
  que o rodapé de "já renovado" cita a atualização do Paxtu.
- **Seção em texto livre:** a comparação normaliza o nome e usa o ramo como reserva. Beneficiário sem
  chefe entra só no resumo mensal, em "Sem seção" ou na seção dele.
- **Chefe inativo:** `apenas_ativos=True` filtra `status_no_grupo`.
