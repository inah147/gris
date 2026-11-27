# Plano técnico — Assembleias de Grupo

> Spec: [spec.md](spec.md) · Textos: [textos.md](textos.md)

## 1. Ponto de partida

| Peça | Hoje | Depois |
|---|---|---|
| `Funcao Voluntario.diretoria` | Select `Eleita`/`Nomeada`, editado em `/administracao/funcoes`. O patch `marcar_funcoes_diretoria_eleita` já marca as três funções do estatuto | Sem mudança. É a fonte das funções da chapa |
| `Associado` | Sem equipe. O importador descarta a linha "Equipe:" do Paxtu | Ganha o campo `equipe`, que o importador passa a gravar |
| `Configuracoes de Comunicacao.link_papel_timbrado` | Validado, mas nenhum código o lê | Passa a ser o modelo de todos os documentos da assembleia |
| Grupo da Diretoria no WhatsApp | Não existe em nenhuma configuração | `Configuracoes de Assembleias.grupo_diretoria_whatsapp` |
| `Log de Mensagem.destinatario_tipo` | Sem um tipo para a Diretoria | Ganha "Grupo da diretoria" |
| Administração (portal) | Unidades, Funções e Documentos | Ganha Assembleias, com lista, configurações e página da assembleia |

## 2. Decisões técnicas

| Tema | Decisão |
|---|---|
| Papel | "Gestor de Assembleias". Fixture em `hooks.py`/`fixtures/role.json`, patch idempotente como `patches/criar_role_portaria.py`, `install.py` e `PAPEIS` em `semear_catalogo_de_acessos.py`. `pode_gerenciar_assembleias()` aceita também Gestor da UEL e System Manager |
| Permissões das páginas | `PAGE_ROLES` com os três papéis e a página em `STRICT_PORTAL_PAGES`. A página pública fica como `"Public"`, e os formulários como `"All"`, com o vínculo checado no endpoint |
| Criação e exclusão | `criar_assembleia(payload)` monta o doc com os padrões (`api/assembleias/padroes.py::preencher_padroes(doc, config)`) e dá `insert()`. Quem cria tem permissão de DocType, então não há `ignore_permissions`. `excluir_assembleia(name)` recusa com o edital publicado e, numa transação, apaga as candidaturas, as chapas e os assuntos com `delete_doc(..., ignore_permissions=True)`: quem gerencia não tem `delete` nos DocTypes de inscrição, que são de uso interno. Depois apaga a assembleia. O `on_trash` da `Assembleia` faz a mesma cascata para a exclusão pelo Desk |
| Pessoa | Pares `*_tipo` (Select Associado/Responsavel) + Dynamic Link, como em `Unidade Organizacional`. As opções de combobox generalizam `api/administracao/consultas.py::opcoes_de_responsavel` com `idade_minima` e `data_referencia`, numa consulta por DocType |
| Usuário → pessoa | Helper novo `pessoa_do_usuario(user)` em `api/assembleias/pessoas.py`: primeiro `acessos/permissoes.associado_do_usuario`, depois `responsavel_acesso.get_responsavel_do_usuario(incluir_vinculo_do_beneficiario=False)`. Associado tem precedência, porque o login é o `id_escoteiros`. Responsável e Associado da mesma pessoa compartilham o `name`, então a pessoa nunca é contada duas vezes |
| Registro ativo | `status == "Válido"` e `validade_registro >= data da assembleia`. O `status` sozinho pode estar desatualizado entre uma importação e outra |
| Votantes | Função pura `montar_votantes(regras, associados, data)` → `(linhas, avisos)` sobre dados lidos de uma vez: os associados ativos com categoria, ramo, equipe, nascimento, status e validade. `aplicar_lista(existentes, geradas)` preserva as linhas manuais e as removidas, com a chave `tipo_linha` + pessoa, ou `equipe` + ramo |
| Idade | Helper puro `idade_em_meses(nascimento, data)`. "6,5 anos" vira 78 meses, para não depender de float |
| Variáveis | `api/assembleias/textos.py`: `substituir(texto, valores)` por `re.sub(r"\{(\w+)\}")` num dicionário fechado (padrão da régua, sem `str.format` nem Jinja), `variaveis_desconhecidas(texto, permitidas)` e `valores_da_assembleia(doc)` |
| Prazos | Função pura `situacao_do_formulario(cargo, assembleia, regras, agora, contagens)` → `{aberto, motivo, fecha_em, reaberto}`. As contagens vêm de uma consulta agregada por cargo |
| Edital publicado | O `validate` da `Assembleia` compara com `get_doc_before_save()` e recusa a mudança nos campos travados e na pauta (menos `concluido` e `orientacao_conducao`) quando `edital_publicado` já era 1 |
| Autosave | `salvar_campos(assembleia, aba, campos, modified)`. Aceita só a whitelist de campos da aba (ata, checklist, condução) e recusa com `"conflito"`, como dado, quando o `modified` mudou: a tela recarrega em vez de sobrescrever. No front, debounce de 800 ms, indicador e `beforeunload` |
| IA | `solicitar_ata_ia(assembleia)` grava `ata_status_geracao = "Gerando"` e enfileira na fila `long` com `enqueue_after_commit`. A task chama `gris.api.llm.gerar_resposta_modelo` e grava `ata_texto` ou o erro amigável. A tela consulta `status_ata_ia`. O prompt é montado em `api/assembleias/ata_ia.py`: o modelo com as variáveis já resolvidas, os dados em lista e a instrução de manter `[A CONFIRMAR: …]` no que faltar. Vão só nomes, cargos e horários |
| Diretoria em exercício | `{diretor_presidente}` e o diretor financeiro saem da lotação em vigor (`Funcao do Associado` sem `data_fim`), com a função do presidente lida em `Configuracoes de Captacao.funcao_presidente` |
| Editor | `window.gris.editor` (ToastUI, markdown via `getMarkdown`) só para o "Texto da ata", que é conteúdo final, como em `www/projetos/projeto.js`. Textos do edital, orientações e modelo de ata são **modelos** com `{variáveis}` e `[MARCADORES]`: ficam em `textarea` com markdown simples, para o WYSIWYG não escapar colchetes nem reescrever as variáveis. A pauta editável é montada pelo JS comum (`criarEditorDePauta`), com selects gerados no mesmo markup da macro. Na leitura, `frappe.utils.markdown` |
| Documentos | Módulo novo, `api/google_workspace/assembleia_drive.py`. A pasta segue `festa_drive.create_festa_folder_async`, e o validador da pasta raiz é extraído para uma função comum em vez de copiado. O documento segue `recepcao_drive.gerar_declaracao_idoneidade`: copiar o timbrado, `batchUpdate`, `export` PDF e upload. O conteúdo é um markdown restrito, convertido por `gris/utils/docs_conteudo.py::markdown_para_requests(md, indice_inicial)` em `insertText`, `updateParagraphStyle` (títulos e alinhamento), `updateTextStyle` (negrito e itálico), `createParagraphBullets` (numeradas e com marcador) e `insertTable`. As tabelas são preenchidas de trás para frente, para os índices não andarem |
| Rascunho e final | Os links ficam na assembleia. Gerar de novo apaga os arquivos anteriores do mesmo tipo (`files().delete`), menos o edital "(publicado)". O download devolve os bytes do export (`response.type = "pdf"`) |
| Lembretes | Cron `0 9 * * *` → enfileira `lembrar_publicacao_edital` na fila `long`. `marco_do_edital(d, ultimo)` é uma função pura, com as janelas da spec. O envio é síncrono (`enviar_para_grupo(..., enqueue=False)`) e o carimbo (`lembrete_edital_marco` e `lembrete_edital_em`) só é gravado depois. Métricas no `job_logger` |

## 3. Modelo de dados

### 3.1 `Configuracoes de Assembleias` (Single, módulo Gris)

| Seção | Campos |
|---|---|
| Drive (só no Desk) | `habilitar_pastas_drive` (Check); `drive_compartilhado_assembleias` (Select, carregado como em Configurações de Festas); `pasta_assembleias_id` (Data, aceita ID ou link) |
| Edital | `dias_limite_edital` (Int, 30); `local_padrao` (Data); `cidade` (Data); `texto_topo_edital`, `texto_rodape_edital` (Long Text); `grupo_diretoria_whatsapp` (Select de grupos, entra em `DOCTYPES_COM_SELECT_DE_GRUPO`) |
| Pautas | `pauta_ordinaria`, `pauta_extraordinaria` (Table "Item Padrao de Pauta": `titulo`, `tem_votacao`, `finalidade`, `orientacao_conducao`); `orientacoes_gerais` (Long Text) |
| Materiais | `materiais` (Table "Material de Assembleia": `item`) |
| Quem vota | `voto_escotistas`, `voto_dirigentes`, `voto_demais_associados`, `exigir_registro_ativo`, `voto_jovens` (Check); `idade_minima_voto_jovem` (Int, 16); `voto_representado_por_responsavel` (Check); `idade_minima_representacao_meses` (Int, 78); `voto_por_matilha`, `voto_por_patrulha_escoteiro`, `voto_por_patrulha_senior` (Check, 0) |
| Prazos | `prazo_{mesa,diretoria,comissao_fiscal,delegado,assuntos_gerais}_unidade` (Select Sem limite/Dias/Horas) + `_valor` (Int); `manter_aberto_sem_candidatos` (Check, 1) |
| Vagas | `vagas_comissao_fiscal` (Int, 3); `suplentes_comissao_fiscal` (Int, 3); `associados_por_delegado` (Int, 50) |
| Ata | `modelo_ata` (Long Text) |

### 3.2 `Assembleia`

Naming `ASM-.YYYY.-.##`, `title_field` com o tipo e a data. Lida, escrita e excluída por Gestor de
Assembleias, Gestor da UEL e System Manager.

| Grupo | Campos |
|---|---|
| Visão geral | `data` (Date, única), `tipo` (Ordinária/Extraordinária), `local`, `hora_primeira_convocacao`, `hora_segunda_convocacao` (Time), `credenciamento_tipo` + `credenciamento`, `vagas_delegados` (Int), `pasta_drive_link`, `pasta_drive_erro` |
| Checklist | `checklist` (Table "Etapa do Checklist da Assembleia": `chave`, `fase`, `titulo`, `concluido`, `concluido_em`, `concluido_por`, `somente_eletiva`) |
| Edital | `edital_texto_topo`, `edital_texto_rodape`, `edital_incluir_links`, `data_publicacao_edital`, `edital_publicado`, `edital_publicado_em`, `edital_doc_link`, `edital_pdf_link` |
| Pauta | `pauta` (Table "Item da Pauta da Assembleia": `titulo`, `tem_votacao`, `finalidade`, `orientacao_conducao`, `concluido`) |
| Presença | `votantes` (Table "Votante da Assembleia": `nome`, `tipo_linha`, `pessoa_tipo`, `pessoa`, `ramo`, `equipe`, `origem` Automática/Manual, `removido`), `lista_gerada_em`, `lista_presenca_doc_link`, `lista_presenca_pdf_link` |
| Ata | `ata_hora_inicio`, `ata_hora_termino`, `ata_presentes` (Int), `presidente_tipo` + `presidente`, `secretario_tipo` + `secretario`, `anotacoes_secretario`, `ata_texto`, `ata_status_geracao`, `ata_erro_geracao`, `ata_doc_link`, `ata_pdf_link` |
| Controle | `lembrete_edital_marco` (Int), `lembrete_edital_em` (Date), ambos read-only |

### 3.3 Inscrições

| DocType | Campos | Restrições |
|---|---|---|
| `Candidatura de Assembleia` | `assembleia`, `cargo` (Presidente da mesa / Secretário da mesa / Delegado / Comissão Fiscal), `candidato_tipo` + `candidato`, `nome`, `registro`, `registro_ativo`, `biografia`, `motivacao`, `usuario`, `status` (Ativa/Retirada), `motivo_retirada` | Única por (assembleia, cargo, candidato) entre as ativas |
| `Chapa de Assembleia` | `assembleia`, `responsavel_usuario`, `responsavel_tipo` + `responsavel_pessoa`, `status`, `motivo_retirada`, `membros` (Table "Membro da Chapa": `funcao` Link Funcao Voluntario, `pessoa_tipo` + `pessoa`, `nome`, `registro`, `registro_ativo`, `biografia`, `motivacao`) | Uma função por linha; sem pessoa repetida na chapa ou em outra chapa ativa |
| `Assunto Geral de Assembleia` | `assembleia`, `conteudo`, `usuario`, `pessoa_tipo` + `pessoa`, `nome` | Até 2.000 caracteres |

### 3.4 DocTypes existentes

| DocType | Mudança |
|---|---|
| `Associado` | `equipe` (Data), perto de `secao` |
| `Log de Mensagem` | Opção "Grupo da diretoria" em `destinatario_tipo` |

## 4. Etapas

Cada etapa é um commit na branch `feat/assembleias`.

### 4.0 Spec

Este diretório.

### 4.1 Papel, schema e padrões

- O papel e os DocTypes de § 3.
- `gris/api/assembleias/constantes.py`: finalidades, cargos, chaves do checklist, idades de
  candidatura e os textos de [textos.md](textos.md), incluindo a orientação por finalidade.
- Patch `gris.patches.preparar_assembleias`:
  - cria o papel;
  - preenche as configurações vazias: textos, pautas, orientações, materiais, prazos, vagas,
    regra de voto, `local_padrao` (a partir do endereço em `Definicao da UEL`) e `cidade`.
- `ConfiguracoesdeAssembleias.validate`:
  - variáveis desconhecidas;
  - prazos;
  - M < N;
  - pasta raiz.

### 4.2 Lista, criação, exclusão e configurações (portal)

- `api/assembleias/permissoes.py`: `pode_gerenciar_assembleias`, `garantir_gestor_assembleias`.
- `api/assembleias/endpoints.py`:
  - `criar_assembleia` e `excluir_assembleia`;
  - `salvar_configuracoes`.
- `api/assembleias/padroes.py`: `preencher_padroes`, o cálculo das vagas de delegado e a resolução
  dos títulos da pauta.
- `www/administracao/assembleias/index.{py,html,js,css}`: os cards e o diálogo "Nova assembleia".
- `www/administracao/assembleias/configuracoes.{py,html,js,css}`.
- `api/portal_access.py`: sidebar, ícone (`landmark`), `PAGE_ROLES` e `STRICT_PORTAL_PAGES`.
- `www/administracao/index.{py,html}`: o card com `visible`.

### 4.3 Página da assembleia: Visão Geral, Edital, Condução

- `www/administracao/assembleias/assembleia.{py,html,js,css}` com Basecoat `tabs`, uma partial por
  aba.
- Endpoints (todos com `garantir_gestor_assembleias()`):
  - `salvar_visao_geral`;
  - `salvar_edital`, que recebe a pauta inteira;
  - `restaurar_pauta_padrao`;
  - `marcar_edital_publicado`;
  - `salvar_campos` (checklist e condução).
- Controller `assembleia.py`:
  - trava do edital;
  - checklist derivado: `somente_eletiva`, e o "divulgar" acompanha `edital_publicado`;
  - `on_trash` em cascata;
  - `situacao_dos_formularios()`.

### 4.4 Equipes e lista de presença

- `gris/api/associate/importer.py` lê "Equipe:" no layout atual e no antigo, e não apaga uma equipe
  manual quando a linha falta. O campo `equipe` aparece na ficha do associado no portal
  (`www/associados/detalhe`).
- `api/assembleias/votantes.py`:
  - `montar_votantes` (pura);
  - `carregar_associados(data)`: uma consulta;
  - `gerar_lista`, `incluir_votante`, `remover_votante`.
- A aba tem os totais, a maioria absoluta e os avisos.

### 4.5 Ata

- `api/assembleias/ata.py`: `salvar_campos` com a whitelist da ata.
- `api/assembleias/ata_ia.py`:
  - `montar_prompt` (pura);
  - `solicitar_ata_ia`;
  - a task `_gerar_ata`;
  - `status_ata_ia`.
- Front: autosave com debounce, indicador, `beforeunload`, ToastUI em `ata_texto` e o contador de
  marcadores `[A CONFIRMAR`.

### 4.6 Formulários e página pública

- `api/assembleias/formularios.py`:
  - `situacao_do_formulario` e `elegibilidade` (puras);
  - `enviar_candidatura`, `enviar_chapa`, `enviar_assunto_geral`;
  - `listar_inscricoes` e `retirar_inscricao`.

  Os envios inserem com `ignore_permissions`, justificado no código: quem se candidata não tem
  permissão de DocType. Os três endpoints de envio aceitam só POST.
- `www/assembleias/candidatura.{py,html,js}` e `www/assembleias/assunto_geral.{py,html,js}`: login
  obrigatório e redirecionamento de volta.
- `www/assembleias/candidaturas.{py,html,css}`: pública, `portal_clean.html`, campos fixos e `| e`
  em todo texto.

### 4.7 Drive e documentos

- `api/google_workspace/assembleia_drive.py`:
  - `criar_pasta_assembleia_async`;
  - `gerar_documento(assembleia, tipo, final=False)`.
- `gris/utils/docs_conteudo.py`: `markdown_para_requests` (puro).
- `api/assembleias/documentos.py`:
  - `conteudo_do_edital`, `conteudo_da_lista`, `conteudo_da_ata` (markdown, puros);
  - endpoints de download.

### 4.8 Lembretes

- `api/assembleias/lembretes.py`:
  - `marco_do_edital` (pura);
  - `lembrar_publicacao_edital`;
  - o cron em `hooks.py`.
- `utils/whatsapp.py`: o tipo "Grupo da diretoria" no `_registrar_log`.

### 4.9 Testes, lint e evidências

- Os testes da § 6, `pre-commit run --all-files` (depois de `git add -A`) e `semgrep` com as regras
  do Frappe.
- Prints anonimizados em `docs/evidencias/assembleias/`.
- `graphify update .`.

## 5. Implantação

1. Merge e deploy. O patch cria o papel e preenche as configurações.
2. No Desk, em Configurações de Assembleias, escolher o drive, a pasta raiz e ligar as pastas.
   Conferir o link do timbrado em Configurações de Comunicação.
3. Conceder o papel "Gestor de Assembleias" a quem vai cuidar das assembleias.
4. No portal, revisar as configurações gerais: textos, grupo da Diretoria e regra de voto.
5. Criar a próxima assembleia. A pasta é criada e os lembretes passam a contar.
6. Se for usar voto por equipe, conferir as equipes no cadastro: a próxima importação do Paxtu já
   as traz.

## 6. Matriz de validação

Os arquivos ficam em `gris/tests/`. Os testes de banco seguem `test_pessoas_responsavel_associado.py`:
prefixo "ZZ Teste" e `frappe.db.rollback()` no `tearDown`. Código que faz commit (Drive e
lembretes) roda com `patch("frappe.db.commit")`, e o Google e o WhatsApp são simulados.

| CA | Teste |
|---|---|
| 01.1, 04.2–04.5, 04.7 | `test_assembleias_configuracoes.TestConfiguracoes` |
| 01.2–01.4 | `test_assembleias_criacao.TestPermissoes` |
| 02.1–02.4, 04.6 | `test_assembleias_criacao.TestCriacao` |
| 02.5–02.7 | `test_assembleias_criacao.TestExclusao` |
| 03.1–03.2 | `test_assembleias_criacao.TestListaDeAssembleias` |
| 05.1–05.2 | `test_assembleias_pagina.TestVisaoGeral` |
| 05.4, 12.4–12.5 | `test_assembleias_pagina.TestFormularios` |
| 05.6–05.7 | `test_assembleias_pagina.TestChecklist` |
| 06.1–06.8 | `test_assembleias_pagina.TestEdital` |
| 07.1–07.5 | `test_assembleias_votantes.TestRegraDeVoto`, `TestAplicarLista`, `TestEndpointsDaLista` |
| 07.6, 08.8 (conteúdo) | `test_assembleias_documentos.TestConteudoDocumentos` |
| 08.1–08.3 | `test_assembleias_ata.TestAta` |
| 08.4–08.7 | `test_assembleias_ata.TestAtaIA` (LLM simulado) |
| 09.1–09.4, 13.1–13.5 | `test_assembleias_formularios.TestInscricoesEPublica` |
| 10.1–10.3 | `test_assembleias_pagina.TestConducao` |
| 11.1–11.5 | `test_assembleias_documentos.TestAssembleiaDrive`, `TestDocsConteudo` (Drive e Docs simulados) |
| 12.1–12.3, 12.6–12.11 | `test_assembleias_formularios.TestPessoaEElegibilidade`, `TestEnvios`, `TestChapa` |
| 14.1–14.7 | `test_assembleias_lembretes.TestMarcoDoEdital`, `TestRodada` |
| 15.1–15.3 | `test_importacao_associados_extracao`, `test_assembleias_votantes.TestRegraDeVoto.test_equipe_soma_as_linhas_dos_jovens` |
| 03.3, 05.3, 05.8, 08.2 (indicador), 10.4, telas | Validação no dev.gris com Playwright, desktop e 390 px |

**Pendente:** uma rodada real de geração no Google Docs (edital, lista e ata) com um timbrado de
teste, para conferir a tabela e as quebras de linha, e uma geração de ata pelo provedor de IA
configurado.

## 7. Riscos

- **Registro vencido em massa:** em 19/11/2026, 169 dos 276 associados ativos estavam com o
  registro vencido no dev.gris. Com "exigir registro ativo" ligado (padrão do estatuto), a lista
  sai curta até a importação do Paxtu trazer as renovações. O aviso de CA-07.2 mostra o número
  antes da impressão.
- **Docs API:** a inserção de tabela depende de índices. O conversor é puro e testado sobre as
  requests, e cada documento é conferido uma vez no dev.gris com um timbrado de teste.
- **Drive real no dev.gris:** criar uma assembleia cria uma pasta de verdade, como nas festas. Nos
  testes e no E2E, o enqueue é bloqueado ou a pasta raiz aponta para uma pasta de teste.
- **Equipes incompletas:** o voto por equipe vem desligado. Se for ligado antes de a importação
  trazer as equipes, o aviso de jovens sem equipe deixa a lacuna visível.
- **LLM:** a ata gerada é um rascunho. Os marcadores `[A CONFIRMAR` e o aviso antes do PDF evitam
  que um resultado inventado vá para o cartório.
