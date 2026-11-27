# Plano técnico — Assembleias de Grupo

> Spec: [spec.md](spec.md)

## 1. Ponto de partida

| Peça | Hoje | Depois |
|---|---|---|
| `Calendario` / `Calendario Simulado` | Sem nenhuma marcação de assembleia. A simulação cria um evento por seção, e a conciliação copia campo a campo (`www/calendario/simulacao_calendario.py::reconcile_calendar`) | Os dois ganham `assembleia_de_grupo`. A conciliação e o diff passam a considerá-lo. O controller do `Calendario` sincroniza a `Assembleia` |
| `Funcao Voluntario.diretoria` | Select `Eleita`/`Nomeada`, editado em `/administracao/funcoes` | Sem mudança. É a fonte das funções da chapa |
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
| Uma assembleia por dia | `Assembleia.data` é única. `sincronizar_do_calendario(cal)` procura pela data do `inicio`. O campo `calendario` guarda o primeiro evento, e os demais eventos marcados no dia só garantem o vínculo. Fica "Desvinculada" quando não sobra nenhum evento marcado no dia (consulta por data, sem guardar a lista) |
| Switch e `permlevel` | O campo tem `permlevel 1` no `Calendario`. Na conciliação, o `doc.save()` de quem não tem nível 1 descartaria o valor, então `reconcile_calendar` grava `assembleia_de_grupo` com `db.set_value` depois do insert ou save e chama a sincronização. O valor veio do `Calendario Simulado`, onde só o gestor consegue gravá-lo, porque `create`/`update_simulation_event` ignoram o parâmetro sem o papel e preservam o valor atual |
| Criação pela sincronização | `insert(ignore_permissions=True)`, justificado: é sincronização de sistema disparada por quem edita o calendário, que não precisa do papel de assembleias. O controller do `Calendario` captura a falha e grava no `Error Log`, como as notificações já fazem, para não travar o calendário |
| Pessoa | Pares `*_tipo` (Select Associado/Responsavel) + Dynamic Link, como em `Unidade Organizacional`. As opções de combobox generalizam `api/administracao/consultas.py::opcoes_de_responsavel` com `idade_minima` e `data_referencia`, numa consulta por DocType |
| Usuário → pessoa | Helper novo `pessoa_do_usuario(user)` em `api/assembleias/pessoas.py`: primeiro `acessos/permissoes.associado_do_usuario`, depois `responsavel_acesso.get_responsavel_do_usuario(incluir_vinculo_do_beneficiario=False)`. Associado tem precedência, porque o login é o `id_escoteiros` |
| Votantes | Função pura `montar_votantes(config, associados, vinculos, data)` sobre dados lidos de uma vez: os associados ativos com categoria, ramo, equipe e nascimento. `aplicar_lista(existentes, gerados)` preserva as linhas manuais e as removidas, com a chave `tipo_voto` + pessoa, ou `equipe` + ramo |
| Prazos | Função pura `situacao_do_formulario(cargo, assembleia, config, agora, contagens)` → `{aberto, motivo, fecha_em}`. As contagens vêm de uma consulta agregada por cargo |
| Edital publicado | O `validate` da `Assembleia` compara com `get_doc_before_save()` e recusa a mudança nos campos travados e na pauta (menos `concluido` e `orientacao_conducao`) quando `edital_publicado` já era 1 |
| Autosave da ata | `salvar_campos_ata(assembleia, campos, modified)`. Aceita só a whitelist de campos e recusa com `"conflito"`, como dado, quando o `modified` mudou: a tela recarrega em vez de sobrescrever. No front, debounce de 800 ms, indicador e `beforeunload` |
| IA | `solicitar_ata_ia(assembleia)` grava `ata_status_geracao = "Gerando"` e enfileira na fila `long` com `enqueue_after_commit`. A task chama `gris.api.llm.gerar_resposta_modelo` e grava `ata_texto` ou o erro amigável. A tela consulta `status_ata_ia`. O prompt é montado em `api/assembleias/ata_ia.py`, sem CPF, telefone ou e-mail |
| Editor | `window.gris.editor` (ToastUI) para `ata_texto` e para os textos do edital, como em `www/projetos/projeto.js`. Na leitura, `frappe.utils.markdown` |
| Documentos | Módulo novo, `api/google_workspace/assembleia_drive.py`. A pasta segue `festa_drive.create_festa_folder_async`, e o validador da pasta raiz é extraído para uma função comum em vez de copiado. O documento segue `recepcao_drive.gerar_declaracao_idoneidade`: copiar o timbrado, `batchUpdate`, `export` PDF e upload. O conteúdo é um markdown restrito, convertido por `gris/utils/docs_conteudo.py::markdown_para_requests(md, indice_inicial)` em `insertText`, `updateParagraphStyle` (títulos), `updateTextStyle` (negrito e itálico), `createParagraphBullets` e `insertTable`. As tabelas são preenchidas de trás para frente para os índices não andarem |
| Rascunho e final | Os links ficam na assembleia. Gerar de novo apaga os arquivos anteriores do mesmo tipo (`files().delete`), menos o edital "(publicado)". O download devolve os bytes do export (`response.type = "pdf"`) |
| Lembretes | Cron `0 9 * * *` → enfileira `lembrar_publicacao_edital` na fila `long`. `marco_do_edital(d, ultimo)` é uma função pura, com as janelas da spec. O envio é síncrono (`enviar_para_grupo(..., enqueue=False)`) e o carimbo `lembretes_edital_enviados`, com o último marco e a data, só é gravado depois. Métricas no `job_logger` |
| Situação "Realizada" | O mesmo job diário passa a "Realizada" as assembleias "Agendadas" com data menor que hoje |

## 3. Modelo de dados

### 3.1 `Configuracoes de Assembleias` (Single, módulo Gris)

| Seção | Campos |
|---|---|
| Drive (só no Desk) | `habilitar_pastas_drive` (Check); `drive_compartilhado_assembleias` (Select, carregado como em Configurações de Festas); `pasta_assembleias_id` (Data, aceita ID ou link) |
| Edital | `dias_limite_edital` (Int, 30); `texto_topo_edital`, `texto_rodape_edital` (Long Text, markdown); `grupo_diretoria_whatsapp` (Select de grupos, entra em `DOCTYPES_COM_SELECT_DE_GRUPO`) |
| Pautas | `pauta_ordinaria`, `pauta_extraordinaria` (Table "Item Padrao de Pauta": `titulo`, `tem_votacao`, `finalidade`, `orientacao_conducao`) |
| Materiais | `materiais` (Table "Material de Assembleia": `item`) |
| Voto | `voto_escotistas`, `voto_dirigentes`, `voto_jovens`, `idade_minima_voto_jovem`, `voto_por_matilha`, `voto_por_patrulha_escoteiro`, `voto_por_patrulha_senior`, `voto_responsaveis` |
| Prazos | `prazo_{mesa,diretoria,comissao_fiscal,delegado,assuntos_gerais}_unidade` (Select Sem limite/Dias/Horas) + `_valor` (Int); `manter_aberto_sem_candidatos` (Check); `vagas_comissao_fiscal` (Int) |
| Ata | `modelo_ata` (Long Text) |

### 3.2 `Assembleia`

Naming `ASM-.YYYY.-.##`. Lida e escrita por Gestor de Assembleias, Gestor da UEL e System Manager.

| Grupo | Campos |
|---|---|
| Vínculo | `calendario` (Link), `data` (Date, única), `local`, `situacao` (Agendada/Realizada/Desvinculada), `pasta_drive_link` |
| Visão geral | `tipo` (Ordinária/Extraordinária), `credenciamento_tipo` + `credenciamento`, `hora_primeira_convocacao`, `hora_segunda_convocacao`, `checklist` (Table "Etapa do Checklist da Assembleia": `chave`, `fase`, `titulo`, `concluido`, `concluido_em`, `concluido_por`, `somente_eletiva`) |
| Edital | `edital_texto_topo`, `edital_texto_rodape`, `edital_incluir_links`, `data_publicacao_edital`, `edital_publicado`, `edital_publicado_em`, `edital_doc_link`, `edital_pdf_link`, `pauta` (Table "Item da Pauta da Assembleia": `titulo`, `tem_votacao`, `finalidade`, `orientacao_conducao`, `concluido`) |
| Presença | `votantes` (Table "Votante da Assembleia": `nome`, `tipo_voto`, `pessoa_tipo`, `pessoa`, `ramo`, `equipe`, `origem`, `removido`), `lista_presenca_doc_link`, `lista_presenca_pdf_link` |
| Ata | `ata_hora_inicio`, `ata_hora_termino`, `presidente_tipo` + `presidente`, `secretario_tipo` + `secretario`, `anotacoes_secretario`, `ata_texto`, `ata_status_geracao`, `ata_erro_geracao`, `ata_doc_link`, `ata_pdf_link` |
| Controle | `lembretes_edital_enviados` (Data: último marco e data, read-only) |

### 3.3 Inscrições

| DocType | Campos | Restrições |
|---|---|---|
| `Candidatura de Assembleia` | `assembleia`, `cargo` (Presidente da mesa / Secretário da mesa / Delegado / Comissão Fiscal), `candidato_tipo` + `candidato`, `nome`, `registro`, `biografia`, `motivacao`, `usuario`, `status` (Ativa/Retirada) | Única por (assembleia, cargo, candidato) entre as ativas |
| `Chapa de Assembleia` | `assembleia`, `responsavel_usuario`, `responsavel_tipo` + `responsavel_pessoa`, `status`, `membros` (Table "Membro da Chapa": `funcao` Link Funcao Voluntario, `pessoa_tipo` + `pessoa`, `nome`, `registro`, `biografia`, `motivacao`) | Uma função por linha, sem pessoa repetida |
| `Assunto Geral de Assembleia` | `assembleia`, `conteudo`, `usuario`, `pessoa_tipo` + `pessoa`, `nome` | Até 2.000 caracteres |

### 3.4 DocTypes existentes

| DocType | Mudança |
|---|---|
| `Calendario` | `assembleia_de_grupo` (Check, `permlevel 1`; o nível 1 é de leitura para os papéis do calendário e de escrita para Gestor de Assembleias e System Manager) |
| `Calendario Simulado` | `assembleia_de_grupo` (Check) |
| `Associado` | `equipe` (Data), perto de `secao` |
| `Log de Mensagem` | Opção "Grupo da diretoria" em `destinatario_tipo` |

## 4. Etapas

Cada etapa é um commit na branch `feat/assembleias`.

### 4.0 Spec

Este diretório. Revisão do usuário com o estatuto e o último edital, e resolução das
[pendências](spec.md#7-pendências-que-dependem-do-estatuto-e-do-último-edital).

### 4.1 Papel, schema e padrões

- O papel e os DocTypes de § 3.
- Patch `gris.patches.preparar_assembleias`:
  - cria o papel;
  - preenche as configurações vazias: materiais, as duas pautas com orientações, prazos, vagas,
    `dias_limite_edital`, as regras de voto e os textos.
- `gris/api/assembleias/constantes.py`: finalidades, cargos, chaves do checklist e os textos
  padrão.

### 4.2 Calendário → Assembleia

- `gris/api/assembleias/sincronizacao.py::sincronizar_do_calendario(cal, evento)`, chamada no
  `after_insert`, `on_update` e `on_trash` do `Calendario`.
- `api/calendario/simulation.py`:
  - `create_simulation_event` e `update_simulation_event` ganham `assembleia_de_grupo`, que só é
    aplicado com `pode_gerenciar_assembleias()`;
  - a resposta inclui o campo.
- `www/calendario/simulacao_calendario.{py,html,js}`:
  - `context.pode_gerenciar_assembleias`;
  - switch nos dois diálogos;
  - selo "Assembleia" no evento;
  - o campo entra no diff e na conciliação.

### 4.3 Equipes

- `gris/api/associate/importer.py` lê "Equipe:" no layout atual e no antigo, e não apaga uma equipe
  manual quando a linha falta.
- `gris/api/assembleias/votantes.py::equipes_por_ramo(associados)` normaliza com
  `utils/chefes.normalizar_texto`.
- O campo `equipe` aparece na ficha do associado no portal (`www/associados/detalhe`).

### 4.4 Lista e configurações (portal)

- `www/administracao/assembleias/index.{py,html,js,css}`: os cards.
- `www/administracao/assembleias/configuracoes.{py,html,js,css}`:
  - a tela;
  - `api/assembleias/configuracoes.py::salvar_configuracoes(payload)`, com o
    `validate` do Single conferindo prazos e idade.
- `api/assembleias/permissoes.py`: `pode_gerenciar_assembleias`, `garantir_gestor_assembleias`.
- `api/portal_access.py`: sidebar, ícone (`landmark`), `PAGE_ROLES` e `STRICT_PORTAL_PAGES`.
- `www/administracao/index.{py,html}`: o card com `visible`.

### 4.5 Página da assembleia: Visão Geral, Edital, Condução

- `www/administracao/assembleias/assembleia.{py,html,js,css}` com Basecoat `tabs`, uma partial por
  aba.
- `api/assembleias/endpoints.py` (tudo com `garantir_gestor_assembleias()`):
  - `salvar_visao_geral`;
  - `salvar_edital`, que recebe a pauta inteira;
  - `restaurar_pauta_padrao`;
  - `marcar_edital_publicado`;
  - `marcar_item_checklist`;
  - `marcar_item_pauta`.
- Controller `assembleia.py`:
  - trava do edital;
  - `checklist` derivado: `somente_eletiva`, e o "divulgar" acompanha `edital_publicado`;
  - `situacao_dos_formularios()`.

### 4.6 Lista de presença

- `api/assembleias/votantes.py`:
  - `montar_votantes` (pura);
  - `carregar_dados_de_voto(data)`: três consultas (associados ativos, vínculos e responsáveis);
  - `gerar_lista`, `incluir_votante`, `remover_votante`.
- A aba tem os totais por tipo e o aviso de jovens sem equipe.

### 4.7 Ata

- `api/assembleias/ata.py`: `salvar_campos_ata` (whitelist de campos + `modified`).
- `api/assembleias/ata_ia.py`:
  - `montar_prompt` (pura);
  - `solicitar_ata_ia`;
  - a task `_gerar_ata`;
  - `status_ata_ia`.
- Front: autosave com debounce, indicador, `beforeunload`, ToastUI em `ata_texto`.

### 4.8 Formulários e página pública

- `api/assembleias/formularios.py`:
  - `situacao_do_formulario` (pura);
  - `enviar_candidatura`;
  - `enviar_chapa`;
  - `enviar_assunto_geral`.

  Cada envio valida login, vínculo, prazo, duplicidade e as funções eleitas em vigor, e insere com
  `ignore_permissions` justificado: quem se candidata não tem permissão de DocType. Os três endpoints
  aceitam só POST.
- `www/assembleias/candidatura.{py,html,js}` e `www/assembleias/assunto_geral.{py,html,js}`: login
  obrigatório e redirecionamento de volta.
- `www/assembleias/candidaturas.{py,html,css}`: pública, `portal_clean.html`, campos fixos e `| e`
  em todo texto.
- A aba "Candidaturas e assuntos gerais" usa `listar_inscricoes(assembleia)` (consultas
  agregadas) e `retirar_inscricao`.

### 4.9 Drive e documentos

- `api/google_workspace/assembleia_drive.py`:
  - `criar_pasta_assembleia_async`;
  - `gerar_documento(assembleia, tipo, final=False)`.
- `gris/utils/docs_conteudo.py`: `markdown_para_requests` (puro).
- `api/assembleias/documentos.py`:
  - `conteudo_do_edital`, `conteudo_da_lista`, `conteudo_da_ata` (markdown, puros);
  - endpoints de download.
- O `validate` de `Configuracoes de Assembleias` confere a pasta raiz no drive escolhido, como o de
  Festas.

### 4.10 Lembretes e situação

- `api/assembleias/lembretes.py`:
  - `marco_do_edital` (pura);
  - `executar_rotina_diaria`: lembretes + "Realizada";
  - o cron em `hooks.py`.
- `utils/whatsapp.py`: o tipo "Grupo da diretoria" no `_registrar_log`.

### 4.11 Testes, lint e evidências

- Os testes da § 6, `pre-commit run --all-files` (depois de `git add -A`) e `semgrep` com as regras
  do Frappe.
- Prints anonimizados em `docs/evidencias/assembleias/`.
- `graphify update .`.

## 5. Implantação

1. Merge e deploy. O patch cria o papel e preenche as configurações, e nenhuma assembleia existe
   ainda.
2. No Desk, em Configurações de Assembleias, escolher o drive, a pasta raiz e ligar as pastas.
   Conferir o link do timbrado em Configurações de Comunicação.
3. Conceder o papel "Gestor de Assembleias" a quem vai cuidar das assembleias.
4. No portal, revisar as configurações gerais: textos, regras de voto e grupo da Diretoria.
5. Marcar a próxima assembleia no calendário e conciliar. A assembleia aparece, a pasta é criada e
   os lembretes passam a contar.
6. Antes da assembleia, conferir as equipes dos ramos no cadastro: a próxima importação do Paxtu já
   as traz.

## 6. Matriz de validação

| CA | Teste |
|---|---|
| 01.1 | `TestPapel.test_patch_cria_papel` |
| 01.2–01.4 | `TestPermissoes` (páginas, endpoints sem o papel, card) |
| 02.1–02.2 | `TestSimulacao.test_switch_ignorado_sem_papel`, `test_switch_gravado_com_papel` |
| 02.3 | `TestConciliacao.test_switch_chega_ao_calendario_mesmo_sem_nivel_1`, `test_switch_e_diferenca` |
| 02.4 | `TestCalendario.test_permlevel_do_switch` |
| 03.1–03.6 | `TestSincronizacao` (cria, um por dia, data, desvincula, revincula, data ocupada, pasta enfileirada, realizada) |
| 04.1–04.3 | `TestListaDeAssembleias` |
| 05.2–05.4 | `TestConfiguracoes.test_validacoes` |
| 05.3 | `TestConfiguracoes.test_patch_preenche_padroes_sem_sobrescrever` |
| 05.5 | `TestSincronizacao.test_copia_padroes_na_criacao`, `TestEdital.test_restaurar_pauta` |
| 05.6 | `TestConfiguracoes.test_pasta_raiz_invalida` (Drive simulado) |
| 06.4 | `TestFormularios` (estado na Visão Geral) |
| 06.6–06.7 | `TestChecklist` |
| 07.1–07.7 | `TestEdital` (trava, `concluido` livre, publicação idempotente) |
| 08.1–08.5 | `TestVotantes` (cada regra, equipe, sem equipe, deduplicação, manuais e removidos) |
| 08.6 | `TestConteudoDocumentos.test_lista_de_presenca` |
| 09.2–09.3 | `TestAta.test_autosave_whitelist`, `test_conflito_de_modified` |
| 09.4–09.7 | `TestAtaIA` (prompt sem dados sensíveis, status, falha preserva texto; LLM simulado) |
| 10.1–10.4 | `TestInscricoes.test_listagem`, `test_retirar` |
| 12.1–12.5 | `TestAssembleiaDrive` (Drive e Docs simulados), `TestDocsConteudo` (requests geradas) |
| 13.1–13.10 | `TestFormularios` (sem login, sem vínculo, prazos em dias e horas, sem limite, manter aberto, duplicidade, chapa incompleta, pessoa repetida, envio fora do prazo) |
| 14.1–14.5 | `TestPaginaPublica` (sem login, campos fixos, desvinculada, escape) |
| 15.1–15.6 | `TestLembretes` (janelas, dia perdido, carimbo depois do envio, falha, publicado, sem grupo, log) |
| 16.1–16.3 | `TestImportacaoEquipe`, `TestVotantes.test_equipe_normalizada` |
| 06.1–06.3, 09.1, 09.8, 11.x | Validação manual e Playwright no dev.gris (`docs/evidencias/assembleias/`) |

Arquivos: `gris/tests/test_assembleias_*.py`. Os testes de banco seguem
`test_pessoas_responsavel_associado.py`: prefixo "ZZ Teste" e `frappe.db.rollback()` no `tearDown`.
O `enqueue` do Drive e do WhatsApp é bloqueado em todos eles.

## 7. Riscos

- **Docs API:** a inserção de tabela depende de índices. O conversor é puro e testado sobre as
  requests, e cada documento é conferido uma vez no dev.gris com um timbrado de teste.
- **Drive real no dev.gris:** criar uma assembleia cria uma pasta de verdade, como nas festas. Nos
  testes e no E2E, o enqueue é bloqueado ou a pasta raiz aponta para uma pasta de teste.
- **Evento por seção:** uma assembleia marcada em várias seções gera vários `Calendario` no
  mesmo dia. A chave por data evita assembleias duplicadas.
- **Equipes incompletas:** enquanto a importação não trouxer as equipes, o voto por equipe sai
  incompleto. O aviso de jovens sem equipe deixa isso visível antes da impressão.
- **LLM:** a ata gerada é um rascunho e precisa de revisão humana. O texto deixa isso claro, e o
  PDF só sai do "Texto da ata" editado.
