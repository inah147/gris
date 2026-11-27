# Spec — Assembleias de Grupo

> Status: implementada (etapas 4.1 a 4.8), com testes de unidade e validação no dev.gris; a
> geração no Google Docs e a ata por IA foram testadas com os serviços simulados e ainda precisam
> de uma rodada real · Branch: `feat/assembleias` · Plano técnico: [plano.md](plano.md) · Textos:
> [textos.md](textos.md)

## 1. Problema

A Assembleia de Grupo é o órgão máximo da UEL (estatuto, art. 7º). Ela se reúne ao menos uma vez
por ano em reunião ordinária e, quando preciso, em extraordinária. Hoje o GRIS não participa de
nada disso:

- **Edital.** É reescrito à mão a cada ano, a partir do anterior, e ninguém avisa a Diretoria do
  prazo para publicá-lo (30 dias de antecedência mínima). O edital de 2026 saiu convocando
  "representantes dos ramos", o que o estatuto não prevê.
- **Lista de presença.** É montada a partir de planilhas, sem aplicar a regra de voto do
  estatuto: beneficiário a partir de 16 anos; de 6,5 a 15 anos, representado pelo responsável;
  demais associados com registro ativo.
- **Candidaturas.** Mesa, diretoria, comissão fiscal e delegados, além dos assuntos gerais,
  chegam por formulários soltos e mensagens.
- **Ata.** É redigida depois, preenchendo o modelo à mão a partir das anotações.
- **Depois da eleição.** Os passos que vêm depois de uma assembleia eletiva (cartório, banco,
  Receita) dependem da memória de alguém.

## 2. Objetivo

Gerenciar as assembleias pelo módulo **Administração** do portal:

1. **Cadastro.** Criar e excluir assembleias. As configurações gerais trazem as regras do
   estatuto como padrão.
2. **Preparação.** Edital com pauta e textos padrão, lembretes de prazo à Diretoria e lista de
   presença gerada pela regra de voto.
3. **Participação.** Formulários com login para candidaturas e assuntos gerais, com os prazos
   do estatuto, e uma página pública com os candidatos.
4. **Condução e registro.** Roteiro de cada item da pauta para a mesa, ata com salvamento
   automático e rascunho por IA, e documentos no papel timbrado, numa pasta da assembleia no
   Drive.

## 3. Escopo

### Dentro

| Bloco | Entrega |
|---|---|
| Lista | `/administracao/assembleias`: cards separados em próximas e já realizadas, com os botões "Nova assembleia" e "Configurações" |
| Configurações | `/administracao/assembleias/configuracoes`: prazos, pautas padrão, orientações, materiais, regra de voto e textos. No Desk: o drive e a pasta raiz |
| Assembleia | `/administracao/assembleias/assembleia?name=…` em 4 etapas, na ordem em que a assembleia acontece: Edital, Inscrições, Sessão (preparar e conduzir) e Ata. O cabeçalho mostra o estado de cada etapa e o próximo passo; excluir, pasta no Drive e página pública ficam no menu ⋯ |
| Formulários | Candidatura para mesa, delegado, diretoria (chapa) e comissão fiscal, e envio de assunto geral, só com login |
| Página pública | `/assembleias/candidaturas?assembleia=…`: candidatos por cargo |
| Documentos | Edital, lista de presença e ata gerados no Google Docs a partir do papel timbrado e exportados em PDF, na pasta da assembleia no Drive |
| Lembretes | WhatsApp para o grupo da Diretoria 60, 30, 25 e 7 dias antes do prazo do edital |
| Cadastro | Campo `equipe` no Associado, preenchido pela importação do Paxtu |
| Papel | "Gestor de Assembleias" |

### Fora (desta versão)

- **Vínculo com o calendário.** A assembleia é criada à mão no portal. O switch no calendário fica
  para uma próxima versão.
- **Votação eletrônica e apuração.** A lista de presença é impressa e assinada no papel, e o
  resultado das votações vai para a ata.
- **Envio do edital** por WhatsApp ou e-mail. A divulgação continua manual, e o GRIS só lembra o
  prazo.
- **Ata final em "Documentos da UEL"** (portal de transparência).
- **Assinatura digital** da ata e da lista.
- **Limite de reeleição.** O estatuto veda mais de dois mandatos consecutivos na mesma função,
  mas o GRIS não confere isso. A orientação de condução lembra a regra.
- **Impugnação de candidatura** pelo sistema. Ela é feita por escrito na assembleia, e quem
  gerencia pode marcar a candidatura como retirada.

## 4. Regras do estatuto que a feature aplica

| Regra | Estatuto | Onde entra |
|---|---|---|
| Edital com no mínimo 30 dias de antecedência e com a pauta obrigatória | Art. 1 e 2 (capítulo da assembleia) | `dias_limite_edital` = 30, lembretes e pauta no edital |
| Segunda convocação meia hora depois da primeira, com qualquer número de presentes | Art. 3 | `hora_segunda_convocacao` sugerida como a primeira + 30 min |
| Quórum conta só membros com registro ativo e direito a voto | Art. 3, parágrafo único | A lista de presença tem só votantes e mostra o total (o quórum da primeira convocação é a maioria absoluta) |
| Voto: beneficiário a partir de 16 anos; de 6,5 a 15, representado por um responsável legal; demais associados com registro ativo | Art. 9º | RF-07 e os padrões de "quem vota" |
| Delegação de voto vedada | Art. 4 | Orientações gerais. A lista não tem procurador |
| Assunto fora da pauta por escrito até 2 h antes | Art. 5 | Prazo padrão dos assuntos gerais: 2 horas |
| Eleições sempre secretas; chapa ou candidatura única pode ser por aclamação | Art. 8, §§ 2º e 3º | Orientações de condução |
| Delegado: candidatura individual, até 1 h antes da sessão; 1 vaga por fração de 50 associados | Art. 9, §§ 1º e 4º (e o estatuto da UEB) | Prazo padrão de 1 hora; `associados_por_delegado` = 50 |
| Diretoria por chapa; ninguém em duas chapas | Art. 9, § 2º | Formulário da chapa (CA-12.8) |
| Diretoria e comissão fiscal: inscrição até 8 dias antes | Art. 9, § 3º | Prazo padrão de 8 dias |
| Sem inscritos suficientes, inscrições aceitas até a eleição | Art. 9, § 5º | `manter_aberto_sem_candidatos` (padrão ligado) |
| Candidato associado com registro em dia; responsável sem registro pode ser eleito e se registra até a posse | Art. 9, § 7º, I e II | Elegibilidade nos formulários (CA-12.3) |
| Diretoria eleita: presidente, financeiro e administrativo | Art. 10 | Funções com `diretoria = "Eleita"` |
| Comissão fiscal: 3 titulares e 3 suplentes, voto unitário | Art. 7º, § 2º e art. 14 | `vagas_comissao_fiscal` = 3 e `suplentes_comissao_fiscal` = 3 |
| Mesa: presidente e secretário eleitos a cada reunião, dentre os membros | Art. 7º, § 7º | Formulário da mesa e campos da ata |
| Assembleia pode ser presencial, remota ou híbrida | Art. 6º | `local` é texto livre e aceita um link |

## 5. Definições

- **Gestor de assembleias:** quem tem o papel "Gestor de Assembleias", "Gestor da UEL" ou
  "System Manager".
- **Pessoa:** um `Associado` ou um `Responsavel`, guardado como par tipo + nome (Dynamic Link), na
  mesma convenção de `Unidade Organizacional`. Quem é as duas coisas aparece uma vez só, como
  Associado.
- **Idade:** contada na data da assembleia, pela `data_de_nascimento`. "6,5 anos" significa 6 anos
  e 6 meses.
- **Ativo:** `Associado.status_no_grupo = "Ativo"`.
- **Registro ativo:** `Associado.status = "Válido"`. A validade é conferida na data da assembleia,
  pela `validade_registro`.
- **Primeira convocação:** data da assembleia + `hora_primeira_convocacao`. Os prazos dos
  formulários contam a partir daqui.
- **Prazo do edital:** data da assembleia − `dias_limite_edital`.
- **Finalidade de um item da pauta:** a etiqueta que diz para que o item serve. As opções são
  eleição da mesa, leitura do edital, ata anterior, eleição de delegados, eleição da comissão
  fiscal, eleição da diretoria, assuntos gerais e encerramento. Formulários, checklist e
  orientações olham a finalidade, nunca o título.
- **Assembleia eletiva:** a pauta tem um item com a finalidade "eleição da diretoria".
- **Função eleita:** `Funcao Voluntario` com `diretoria = "Eleita"` e `ativa = 1`. O campo já existe
  e é editado em `/administracao/funcoes`; a observação "switch de função eleita no organograma"
  está atendida por ele. Hoje são Diretor(a) Presidente, Diretor(a) Financeiro e Diretor(a)
  Administrativo.
- **Equipe:** matilha (Lobinho) ou patrulha (Escoteiro e Sênior), lida de `Associado.equipe`.
- **Vagas de delegado:** teto de (associados ativos com registro ativo ÷ `associados_por_delegado`).
  O número é calculado na criação da assembleia e pode ser ajustado nela.

## 6. Requisitos funcionais

Cada critério de aceite (CA) tem um teste correspondente na
[matriz do plano](plano.md#6-matriz-de-validação).

### RF-01 — Papel e acesso

- **CA-01.1** O papel "Gestor de Assembleias" existe depois do `migrate` e pode ser pedido pelo
  portal de Acessos.
- **CA-01.2** As páginas `/administracao/assembleias*` só abrem para gestor de assembleias. Os
  demais recebem 403, e o visitante é mandado para o login.
- **CA-01.3** Todo endpoint de escrita da assembleia e das configurações confere o papel no
  servidor. A chamada direta pela API, sem o papel, é recusada com `PermissionError`.
- **CA-01.4** O card "Assembleias" no índice da Administração e no menu lateral só aparece para
  gestor de assembleias.

### RF-02 — Criar e excluir assembleia

- **CA-02.1** "Nova assembleia" abre um diálogo com data, tipo (Ordinária ou Extraordinária),
  hora da primeira convocação e local. Todos os campos são obrigatórios, e o local já vem com
  `local_padrao`. A data não pode estar no passado.
- **CA-02.2** A hora da segunda convocação é sugerida como a primeira + 30 minutos e pode ser
  alterada depois.
- **CA-02.3** Ao criar, a assembleia recebe:
  - a pauta padrão do tipo, com os títulos já resolvidos (`{gestao}`, `{ano}`,
    `{data_assembleia_anterior}`, ver [textos.md](textos.md#1-variáveis));
  - os textos do edital;
  - as orientações de cada item;
  - o checklist;
  - as vagas de delegado calculadas.

  Em seguida, a criação da pasta no Drive é enfileirada (RF-11), e a página da assembleia abre.
- **CA-02.4** Já existir outra assembleia no mesmo dia é recusado, com mensagem.
- **CA-02.5** "Excluir assembleia" fica no menu ⋯ do cabeçalho e pede confirmação. A confirmação lista o
  que será apagado: as candidaturas, as chapas e os assuntos gerais. A pasta do Drive não é
  apagada.
- **CA-02.6** Com o edital publicado, a exclusão é recusada com "O edital já foi publicado. Para
  excluir, fale com o administrador do sistema". O System Manager ainda consegue excluir pelo
  Desk.
- **CA-02.7** Excluir apaga a assembleia, as candidaturas, as chapas e os assuntos gerais dela, numa
  transação.

### RF-03 — Lista de assembleias

- **CA-03.1** Cada card mostra:
  - data, tipo e local;
  - situação do edital: rascunho, publicado ou "prazo vencido" (vermelho);
  - quantidade de candidaturas e de assuntos gerais.
- **CA-03.2** Os cards ficam em duas seções: "Próximas", com data maior ou igual a hoje e em ordem
  crescente, e "Já realizadas", em ordem decrescente.
- **CA-03.3** Sem assembleia nenhuma, aparece o estado vazio com o mascote e o botão "Nova
  assembleia".

### RF-04 — Configurações gerais

- **CA-04.1** Os grupos de campos editáveis no portal são:

  | Grupo | Campos |
  |---|---|
  | Edital | dias limite (padrão 30); local padrão; cidade; textos antes e depois da pauta |
  | Pautas | as duas pautas padrão, com título, votação, finalidade e orientação; as orientações gerais de condução |
  | Materiais | a lista de materiais |
  | Quem vota | ver CA-04.3 |
  | Prazos | ver CA-04.4 |
  | Vagas | da comissão fiscal (titulares e suplentes); associados por delegado |
  | Outros | modelo de ata; grupo da Diretoria no WhatsApp |

- **CA-04.2** Num site novo, ou logo depois do patch, os padrões de [textos.md](textos.md) estão
  preenchidos:
  - os 9 materiais;
  - a pauta ordinária com 11 itens e a extraordinária com 5;
  - as orientações;
  - o modelo de ata;
  - os textos do edital.

  O patch não sobrescreve o que já foi editado.
- **CA-04.3** "Quem vota" vem com os padrões do art. 9º:

  | Opção | Padrão |
  |---|---|
  | Escotistas | ligado |
  | Dirigentes | ligado |
  | Demais associados (contribuintes, colaboradores e outras categorias adultas) | ligado |
  | Exigir registro ativo | ligado |
  | Jovens a partir de N anos | ligado, N = 16 |
  | Responsáveis representam os jovens a partir de M anos | ligado, M = 6,5 |
  | Voto por matilha, por patrulha no Escoteiro e por patrulha no Sênior | desligados (o estatuto não prevê) |

  M precisa ser menor que N.
- **CA-04.4** Os prazos de mesa, diretoria, comissão fiscal, delegado e assuntos gerais aceitam
  "Sem limite", "N dias" ou "N horas". Os padrões são:

  | Prazo | Padrão |
  |---|---|
  | Mesa | sem limite |
  | Diretoria | 8 dias |
  | Comissão fiscal | 8 dias |
  | Delegado | 1 hora |
  | Assuntos gerais | 2 horas |

  Valor zero ou negativo com "Dias" ou "Horas" é recusado. "Manter aberto sem candidatos
  suficientes" vem ligado.
- **CA-04.5** Um texto ou título com variável desconhecida é recusado ao salvar. A mensagem diz
  qual variável e quais são as permitidas.
- **CA-04.6** Mudar as configurações não altera as assembleias já criadas, porque os padrões são
  copiados na criação. A aba do edital tem "Restaurar pauta padrão" enquanto o edital não for
  publicado.
- **CA-04.7** O drive compartilhado, a pasta raiz e o interruptor das pastas ficam no Desk, em
  "Configurações de Assembleias". Pasta inválida ou fora do drive escolhido é recusada no save.

### RF-05 — Etapas e dados da assembleia

- **CA-05.0** A página tem quatro etapas: **Edital**, **Inscrições**, **Sessão** e **Ata**. Cada
  uma mostra uma linha de estado (ex.: "Prazo venceu em 05/11/2026", "5 abertas · 2 inscrições",
  "Em 8 dias", "1 de 5 tarefas"). A página abre na etapa atual: Edital até a publicação,
  Inscrições até a véspera, Sessão no dia e Ata depois. A etapa vai na URL (`#edital`,
  `#inscricoes`, `#sessao`, `#ata`).
- **CA-05.0a** Acima das etapas, o próximo passo aparece quando há algo a fazer (publicar o edital,
  faltam candidatos, gerar a lista na última semana, a assembleia é hoje, finalizar a ata,
  tarefas de depois), com um botão que leva ao lugar certo. Prazo vencido usa o tom de alerta.
- **CA-05.0b** Tudo na página é salvo sozinho, numa fila só, com um indicador no cabeçalho. Mudar
  data, tipo ou primeira convocação recarrega a página depois de salvar.
- **CA-05.1** Os campos editáveis, cada um na sua etapa, são:
  - data, tipo, local e hora da primeira e da segunda convocação (Edital);
  - vagas de delegado (Inscrições);
  - responsável pelo credenciamento, num combobox de associados ativos com 18 anos ou mais e de
    responsáveis (Sessão, preparar).

  Data, tipo e horários ficam travados depois de o edital ser publicado.
- **CA-05.2** Trocar o tipo, enquanto o edital não for publicado, pergunta se a pauta deve ser
  trocada pela padrão do novo tipo.
- **CA-05.3** O presidente e o secretário da mesa são gravados na Sessão (conduzir).
- **CA-05.4** Na etapa Inscrições, cada formulário aparece com o link copiável, o estado (aberto,
  fechado ou "não previsto na pauta") e o prazo calculado. Cada formulário só existe quando a
  pauta tem a finalidade dele.
- **CA-05.5** O menu ⋯ e a etapa Inscrições abrem a página pública.
- **CA-05.6** O checklist é dividido em três fases, e cada tarefa aparece na etapa em que o
  trabalho acontece: elaborar e divulgar no Edital; imprimir a lista, materiais e credenciamento
  na Sessão (preparar); as de depois na Ata.
  - **Antes:**
    1. Elaborar e aprovar o edital.
    2. Divulgar o edital até o prazo, com a data limite exibida.
    3. Imprimir a lista de presença.
  - **No dia:**
    1. Separar os materiais, com a lista das configurações.
    2. Preparar o credenciamento.
  - **Depois:**
    1. Finalizar a ata.
    2. Assinar a ata.
    3. Só se a assembleia for eletiva: registrar a ata em cartório, alterar os dados bancários e
       alterar os dados na Receita Federal.
- **CA-05.7** "Divulgar o edital" é marcado sozinho quando o edital é publicado e não pode ser
  desmarcado à mão. Os demais itens são marcados à mão e guardam quem marcou e quando.
- **CA-05.8** O menu ⋯ tem o link da pasta no Drive ou, sem ela, "Criar pasta no Drive", com o
  motivo de ela não existir.

### RF-06 — Edital de convocação

- **CA-06.1** A pauta pode ser editada: incluir, excluir e reordenar itens, renomear, marcar se o
  item tem votação e escolher a finalidade. A numeração acompanha a ordem.
- **CA-06.2** Os textos de antes e de depois da pauta são editáveis e aceitam as variáveis de
  [textos.md](textos.md#1-variáveis). Uma pré-visualização mostra o texto resolvido.
- **CA-06.3** Ficam também na etapa a data de publicação e a opção "incluir links dos formulários".
  Com a opção marcada, o documento ganha, entre a pauta e o texto final, uma frase de abertura e
  uma lista com um link clicável para cada formulário previsto (ver
  [textos.md](textos.md#lista-de-formulários-gerada)).
- **CA-06.4** "Gerar PDF" gera o rascunho no timbrado (RF-11), sem publicar.
- **CA-06.5** "Marcar como publicado":
  1. pede confirmação;
  2. grava `edital_publicado_em` e a data de publicação (hoje, se estiver vazia);
  3. gera a versão final;
  4. marca o item do checklist.
- **CA-06.6** Publicar depois do prazo do edital pede uma segunda confirmação: "O estatuto exige
  30 dias de antecedência. Publicar mesmo assim?".
- **CA-06.7** Com o edital publicado, o servidor recusa mudanças:
  - nos textos;
  - na pauta (título, votação, finalidade, ordem, inclusão e exclusão);
  - na data de publicação e na opção dos links;
  - na data, no tipo e no horário da assembleia.

  A tela mostra tudo só para leitura e deixa só baixar o PDF final. A marcação de "concluído" e a
  orientação de condução dos itens continuam livres (RF-10).
- **CA-06.8** Depois de publicado, o PDF baixado é sempre o da versão final. Ele não é gerado de
  novo.

### RF-07 — Lista de presença

- **CA-07.1** "Gerar lista" monta os votantes, na data da assembleia, pelas regras de "quem vota".
  Entram só associados ativos, e só com registro ativo quando a regra exige.

  | Linha | Regra |
  |---|---|
  | Escotista, Dirigente, Demais associados | Pela `categoria`, cada uma com o seu Check |
  | Jovem que vota | Beneficiário com idade ≥ N |
  | Jovem representado | Beneficiário com M ≤ idade < N, nome do jovem + "representado por seu responsável legal". Um por jovem, mesmo com irmãos |
  | Representante de equipe | Uma linha "Representante — <equipe> (<ramo>)" por equipe distinta entre os beneficiários ativos do ramo. Só no ramo com voto por equipe ligado, e **em adição** às linhas dos jovens |

  Beneficiário com menos de M anos (Filhotes) não gera linha.
- **CA-07.2** A lista mostra avisos com links para os associados:
  - "N associados ativos ficaram de fora por registro vencido";
  - "N jovens do ramo X sem equipe cadastrada", quando há voto por equipe;
  - "N beneficiários sem data de nascimento". Eles ficam de fora até a data ser preenchida.
- **CA-07.3** Uma mesma pessoa aparece uma vez só. Quem é escotista e dirigente fica na primeira
  categoria encontrada.
- **CA-07.4** É possível incluir uma pessoa à mão, num combobox de associados e responsáveis ou por
  um nome livre, e remover qualquer linha. Gerar de novo mantém as inclusões manuais e não traz de
  volta as linhas removidas.
- **CA-07.5** A lista mostra o total por tipo de linha e o total de votantes. Com ele, a lista
  mostra o quórum da primeira convocação, que é a maioria absoluta: metade + 1.
- **CA-07.6** "Exportar PDF" gera a lista em retrato no timbrado, com as colunas Nome |
  Representado por | Assinatura, em ordem alfabética.
  - Nas linhas de jovem representado, a coluna "Representado por" tem uma linha em branco para o
    nome do responsável.
  - Nas linhas de equipe, a mesma coluna tem uma linha em branco para o nome do representante.
  - O cabeçalho traz o tipo, a data e o total de votantes.
- **CA-07.7** A lista pode ser editada até o fim do dia da assembleia.

### RF-08 — Ata

- **CA-08.1** Os campos da ata são (horários, presentes, mesa e anotações ficam na Sessão, em conduzir; o texto, na Ata):
  - hora de início e de término;
  - quantidade de presentes, pela lista assinada;
  - presidente e secretário da mesa, num combobox de associados ativos com 16 anos ou mais e de
    responsáveis;
  - anotações do secretário.
- **CA-08.2** Todo campo é salvo sozinho cerca de 1 s depois da última alteração. Um
  indicador mostra "Salvando…", "Salvo às HH:MM" ou "Não foi possível salvar — tentar de novo".
  Sair da página com alteração pendente pede confirmação.
- **CA-08.3** Se outra aba ou outra pessoa salvou a ata depois do carregamento, o salvamento é
  recusado com "A ata foi alterada em outra janela. Recarregue para continuar", e nada é
  sobrescrito sem aviso.
- **CA-08.4** "Gerar ata com IA" preenche o [modelo de ata](textos.md#6-modelo-de-ata) com:
  - as anotações;
  - os dados da assembleia: data, tipo, local, horários, data de publicação do edital e
    quantidade de presentes;
  - a mesa;
  - o diretor presidente e o diretor financeiro em exercício;
  - a pauta, com o que foi concluído;
  - os candidatos de cada eleição;
  - a quantidade de assuntos gerais.

  O texto gerado vai para um campo novo, "Texto da ata", já formatado em títulos e negritos e
  editável. Esse campo também é salvo sozinho.
- **CA-08.5** A IA não inventa resultados. Votos, nomes e decisões que não estão nas anotações nem
  nos dados continuam como `[A CONFIRMAR: …]` no texto, e a tela mostra quantos marcadores
  restaram.
- **CA-08.6** A geração roda em segundo plano. O botão fica em "Gerando…" e a tela acompanha até
  terminar. Uma falha mostra uma mensagem amigável e não apaga o texto que já existia. Gerar de
  novo com o "Texto da ata" já preenchido pede confirmação antes de substituir.
- **CA-08.7** O LLM recebe só nomes, cargos, horários e as anotações. CPF, telefone e e-mail não
  são enviados.
- **CA-08.8** "Gerar PDF da versão final" gera a ata no timbrado a partir do "Texto da ata" (RF-11),
  com as linhas de assinatura do presidente da assembleia, do secretário e do diretor presidente.
  Com o texto vazio, ou com marcador `[A CONFIRMAR` restante, o botão avisa e pede confirmação.

### RF-09 — Candidaturas e assuntos gerais (etapa Inscrições)

- **CA-09.1** A etapa lista as candidaturas ativas de cada cargo (presidente da mesa, secretário da
  mesa, delegado, comissão fiscal), com nome, registro escoteiro, motivação e biografia.
  Candidatos sem registro ativo aparecem com o aviso "registro a regularizar até a posse".
- **CA-09.2** Cada chapa da diretoria aparece com quem a inscreveu e, para cada função eleita, o
  membro, o registro, a motivação e a biografia.
- **CA-09.3** Os assuntos gerais aparecem com quem enviou, o horário e o conteúdo, em ordem de
  chegada.
- **CA-09.4** Quem gerencia pode marcar uma candidatura ou chapa como retirada, informando o motivo
  (impugnação, desistência). Ela some da página pública e continua no histórico.
- **CA-09.5** O botão "Página de candidaturas" abre a página pública.

### RF-10 — Roteiro de condução (etapa Sessão, conduzir)

- **CA-10.1** O topo mostra as orientações gerais (tipos de votação e lembretes do estatuto).
- **CA-10.2** Em seguida vêm os itens da pauta, em ordem, cada um com:
  - a checkbox de concluído, salva sozinha;
  - o selo "Votação" quando o item tem votação;
  - a orientação de condução.
- **CA-10.3** A orientação de cada item vem do item padrão das configurações. Num item criado à
  mão, vem a orientação da finalidade, ou a de "aprovação simples" quando o item não tem
  finalidade. Ela pode ser editada aqui até o dia da assembleia.
- **CA-10.4** Os itens de eleição mostram, junto da orientação, os dados ao vivo:
  - mesa: os candidatos a presidente e a secretário e a quantidade de assuntos gerais;
  - delegados: as vagas e os candidatos;
  - comissão fiscal: titulares, suplentes e candidatos;
  - diretoria: as chapas.

  O item de assuntos gerais mostra a lista dos enviados.

### RF-11 — Drive e documentos no timbrado

- **CA-11.1** Com as pastas habilitadas, cada assembleia ganha uma pasta
  `Assembleia <Ordinária|Extraordinária> - dd-MM-aaaa` dentro da pasta raiz.
- **CA-11.2** Rodar de novo não cria uma segunda pasta: a pasta com o mesmo nome é reaproveitada.
  Mudar a data não renomeia a pasta. Pasta raiz ou drive faltando registram o motivo e não travam
  a assembleia. A pasta pode ser criada depois, pelo botão "Criar pasta no Drive".
- **CA-11.3** O edital, a lista de presença e a ata são gerados assim:
  1. Copia o Google Doc de `Configuracoes de Comunicacao.link_papel_timbrado` para a pasta da
     assembleia.
  2. Insere o conteúdo: títulos, parágrafos, negrito, listas numeradas e tabela.
  3. Exporta o PDF e o guarda na mesma pasta.

  O navegador recebe o PDF para download. O Doc editável fica na pasta, e o link dele aparece na
  aba.
- **CA-11.4** Gerar de novo o mesmo documento (um rascunho) substitui o Doc e o PDF anteriores em
  vez de acumular arquivos. O edital final é um arquivo à parte, "(publicado)", e nunca é
  substituído.
- **CA-11.5** Sem timbrado configurado, sem a pasta da assembleia ou com erro do Google, aparece
  uma mensagem que diz o que falta, sem o modal de erro de servidor.

### RF-12 — Formulários com login

- **CA-12.1** As rotas são:
  - `/assembleias/candidatura?assembleia=…&cargo=mesa|delegado|diretoria|comissao_fiscal`
  - `/assembleias/assunto_geral?assembleia=…`

  O visitante é mandado para o login e volta para o formulário.
- **CA-12.2** O candidato é quem está logado (Associado, ou Responsável sem Associado). Um usuário
  sem nenhum dos dois vê "Seu usuário não está ligado a um cadastro do grupo" e não consegue
  enviar.
- **CA-12.3** Elegibilidade (art. 9, § 7º):

  | Cargo | Associado | Responsável sem cadastro de associado |
  |---|---|---|
  | Mesa | ativo, 16 anos ou mais | aceito |
  | Delegado | ativo, 18 anos ou mais, registro ativo | recusado: "a candidatura a delegado exige registro ativo no grupo" |
  | Comissão fiscal | ativo, 18 anos ou mais | aceito, com o aviso de registrar-se até a posse |
  | Diretoria | ativo, 18 anos ou mais | aceito, com o aviso de registrar-se até a posse |

  Na comissão fiscal e na diretoria, o associado com registro vencido é aceito com o mesmo aviso.
- **CA-12.4** Um formulário está aberto quando:
  1. a data da assembleia não passou;
  2. a pauta tem a finalidade correspondente;
  3. agora é antes de (primeira convocação − prazo do cargo). "Sem limite" fecha no início da
     primeira convocação.
- **CA-12.5** Com `manter_aberto_sem_candidatos` ligado, o formulário fica aberto depois do prazo,
  até a primeira convocação, enquanto faltar candidato:

  | Cargo | Falta candidato quando |
  |---|---|
  | Mesa | nenhum presidente ou nenhum secretário ativo |
  | Comissão fiscal | menos candidatos ativos que titulares + suplentes |
  | Delegado | menos candidatos ativos que as vagas |
  | Diretoria | nenhuma chapa ativa com todas as funções eleitas preenchidas |

  Nesse caso, o formulário mostra "Inscrições reabertas por falta de candidatos".
- **CA-12.6** Mesa: o candidato escolhe presidente ou secretário, confirma a candidatura e
  preenche, se quiser, a biografia e a motivação. A mesma pessoa pode se candidatar aos dois cargos,
  mas a cada um só uma vez.
- **CA-12.7** Delegado e comissão fiscal: confirmação, biografia e motivação opcionais. Uma
  candidatura ativa por pessoa e cargo.
- **CA-12.8** Diretoria:
  - Há um combobox para cada função eleita, com associados ativos com 18 anos ou mais e
    responsáveis.
  - Cada membro tem biografia e motivação opcionais.
  - O envio exige a confirmação e todas as funções preenchidas.
  - Quem envia fica gravado como responsável pela chapa.
  - A mesma pessoa não pode aparecer em duas funções da chapa, nem em outra chapa ativa da mesma
    assembleia (art. 9, § 2º). A recusa diz em qual chapa a pessoa já está.
- **CA-12.9** Assunto geral: o texto é obrigatório (até 2.000 caracteres) e há a confirmação. Quem
  envia e o horário ficam gravados. Uma pessoa pode enviar mais de um assunto.
- **CA-12.10** Fora do prazo, o formulário mostra "Inscrições encerradas em dd/mm às HH:MM". O
  servidor recusa o envio mesmo que a página tenha sido aberta antes do prazo.
- **CA-12.11** Depois de enviar, o usuário vê a confirmação com o resumo do que enviou. O formulário
  da diretoria avisa que os dados aparecem na página pública.

### RF-13 — Página pública de candidaturas

- **CA-13.1** `/assembleias/candidaturas?assembleia=…` abre sem login, com o cabeçalho da UEL, o
  tipo e a data da assembleia.
- **CA-13.2** A página mostra, por cargo, as candidaturas ativas com nome, registro escoteiro,
  motivação e biografia, e as chapas da diretoria com os membros por função.
- **CA-13.3** Nenhum outro dado pessoal aparece: CPF, telefone, e-mail, idade e usuário ficam de
  fora.
- **CA-13.4** Assembleia inexistente mostra "Assembleia não encontrada".
- **CA-13.5** Todo texto vindo de usuário é escapado (biografia, motivação, nome).

### RF-14 — Lembretes do prazo do edital

- **CA-14.1** O job diário das 9h considera as assembleias futuras com o edital não publicado. Para
  cada uma, d = prazo do edital − hoje.
- **CA-14.2** Os marcos são 60, 30, 25 e 7, cada um com uma janela:

  | Marco | Janela de d |
  |---|---|
  | 60 | 31 a 60 |
  | 30 | 26 a 30 |
  | 25 | 8 a 25 |
  | 7 | 0 a 7 |

  Em cada rodada sai no máximo uma mensagem por assembleia: a do marco cuja janela contém d, e só se
  ele vier depois do último já enviado. Um dia perdido é recuperado sem repetir.
- **CA-14.3** A mensagem segue [textos.md](textos.md#7-lembrete-do-prazo-do-edital-whatsapp) e vai
  para `grupo_diretoria_whatsapp`.
- **CA-14.4** O marco é carimbado só depois do envio confirmado. Uma falha não carimba.
- **CA-14.5** O edital publicado para os lembretes. Sem grupo configurado, nada sai e o resumo do
  job explica por quê.
- **CA-14.6** Todo envio gera um `Log de Mensagem` com o tipo "Grupo da diretoria" e o assunto
  "Prazo do edital da assembleia".
- **CA-14.7** Uma assembleia criada já dentro de uma janela recebe só o marco atual, não os que
  ficaram para trás.

### RF-15 — Equipe no cadastro

- **CA-15.1** O `Associado` ganha o campo `equipe` (texto), editável no Desk e na ficha do portal.
- **CA-15.2** A importação do PDF do Paxtu grava a "Equipe: …" de cada associado e não apaga uma
  equipe preenchida à mão quando o PDF não traz a linha.
- **CA-15.3** As equipes são comparadas sem acento e sem diferença de maiúsculas. "Patrulha Lobo"
  e "patrulha lobo" são a mesma equipe.

## 7. Requisitos não funcionais

- **Segurança:**
  - Toda regra fica no servidor.
  - Os endpoints de formulário validam o login, o vínculo, a elegibilidade, o prazo e a
    duplicidade antes de gravar.
  - O `ignore_permissions` só é usado na gravação controlada dos formulários e na exclusão em
    cascata, com a justificativa no código.
  - A página pública tem só leitura, com campos fixos.
- **Performance:** a lista de presença, a lista de assembleias e as candidaturas são montadas com
  consultas agregadas, sem consulta dentro do laço. Não usa `frappe.cache`.
- **Segundo plano:** a pasta do Drive, a ata por IA e os lembretes rodam em fila. A geração de
  documento é síncrona, com indicador, como na declaração de idoneidade.
- **Interface:**
  - O portal usa Basecoat e as macros do design system.
  - O estado vazio usa o mascote.
  - Os textos estão em PT-BR.
  - Desk sem assets do portal.
- **LGPD:** a página pública mostra só nome, registro e os textos que o candidato escreveu para
  publicação. Os formulários avisam isso antes do envio.
