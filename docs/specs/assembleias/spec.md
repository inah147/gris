# Spec — Assembleias de Grupo

> Status: em revisão; aguarda o estatuto e o último edital · Branch: `feat/assembleias` ·
> Plano técnico: [plano.md](plano.md)

## 1. Problema

A Assembleia de Grupo é obrigatória pelo estatuto e acontece pelo menos uma vez por ano, a
ordinária. Pode haver também extraordinárias. Hoje o GRIS não participa de nada disso:

- O edital de convocação é escrito à mão a cada ano, a partir do anterior, e ninguém avisa a
  Diretoria do prazo para publicá-lo.
- A lista de presença é montada a partir de planilhas, sem uma regra única de quem vota. Por
  exemplo, se o jovem vota ou é representado pelo responsável, ou quantas matilhas e patrulhas
  votam.
- As candidaturas (mesa, diretoria, comissão fiscal e delegados) e os assuntos gerais chegam por
  mensagem e se perdem.
- A ata é redigida depois, a partir das anotações do secretário, e os passos que vêm depois de uma
  assembleia eletiva (cartório, banco, Receita) dependem da memória de alguém.

## 2. Objetivo

Gerenciar as assembleias do grupo pelo módulo **Administração** do portal, a partir do calendário:

1. **Descoberta.** Um switch no calendário marca a atividade como assembleia de grupo, e a
   assembleia aparece sozinha na lista.
2. **Preparação.** Configurações gerais, edital com pauta e textos padrão, lembretes de prazo à
   Diretoria e lista de presença gerada pelas regras de voto.
3. **Participação.** Formulários com login para candidaturas e assuntos gerais, com prazos, e uma
   página pública com os candidatos.
4. **Condução e registro.** Roteiro da pauta para a mesa, ata com salvamento automático e
   rascunho por IA, e PDFs no papel timbrado guardados numa pasta da assembleia no Drive.

## 3. Escopo

### Dentro

| Bloco | Entrega |
|---|---|
| Calendário | Switch "Assembleia de grupo" na simulação do calendário e no `Calendario`, visível e gravável só por quem gerencia assembleias |
| Lista | `/administracao/assembleias`: cards separados em próximas e passadas, com o botão de configurações |
| Configurações | `/administracao/assembleias/configuracoes`: prazos, pautas padrão, materiais, regras de voto e textos. No Desk: o drive e a pasta raiz |
| Assembleia | `/administracao/assembleias/assembleia?name=…` com 6 abas: Visão Geral, Edital de convocação, Lista de presença, Ata, Candidaturas e assuntos gerais, Auxílio para condução |
| Formulários | Candidatura para mesa, delegado, diretoria e comissão fiscal, e submissão de assunto geral, só com login |
| Página pública | `/assembleias/candidaturas?assembleia=…`: candidatos por cargo |
| Documentos | Edital, lista de presença e ata gerados no Google Docs a partir do papel timbrado e exportados em PDF, na pasta da assembleia no Drive |
| Lembretes | WhatsApp para o grupo da Diretoria 60, 30, 25 e 7 dias antes do prazo do edital |
| Cadastro | Campo `equipe` no Associado, preenchido pela importação do Paxtu |
| Papel | "Gestor de Assembleias" |

### Fora (desta versão)

- **Votação eletrônica e quórum ao vivo.** A lista de presença é impressa e assinada no papel.
- **Envio do edital** por WhatsApp ou e-mail. A divulgação continua manual, e o GRIS só lembra o
  prazo.
- **Ata final em "Documentos da UEL".** Publicar a ata de eleição no portal de transparência fica
  para uma próxima versão.
- **Assinatura digital** da ata e da lista.
- **Retirada de candidatura pelo próprio candidato.** Quem gerencia pode marcar como retirada.

## 4. Definições

- **Gestor de assembleias:** quem tem o papel "Gestor de Assembleias", "Gestor da UEL" ou
  "System Manager".
- **Pessoa:** um `Associado` ou um `Responsavel`, guardado como par tipo + nome (Dynamic Link). É a
  mesma convenção de `Unidade Organizacional`. Quem é as duas coisas aparece uma vez só, como
  Associado.
- **Idade:** contada na data da assembleia, pela `data_de_nascimento`.
- **Ativo:** `Associado.status_no_grupo = "Ativo"`.
- **Primeira convocação:** data da assembleia + `hora_primeira_convocacao`. Sem a hora, vale o
  `inicio` do evento do calendário. Os prazos dos formulários contam a partir daqui.
- **Finalidade de um item da pauta:** a etiqueta que diz para que o item serve. As opções são
  eleição da mesa, leitura do edital, ata anterior, eleição de delegados, eleição da comissão
  fiscal, eleição da diretoria, assuntos gerais e encerramento. Formulários e checklist olham a
  finalidade, nunca o título, que pode ser reescrito.
- **Assembleia eletiva:** a pauta tem um item com finalidade "eleição da diretoria".
- **Prazo do edital:** data da assembleia − `dias_limite_edital`. É a data até a qual o edital
  precisa ser publicado.
- **Função eleita:** `Funcao Voluntario` com `diretoria = "Eleita"` e `ativa = 1`. O campo já existe e
  é editado em `/administracao/funcoes`; a observação "switch de função eleita no organograma" está
  atendida por ele.
- **Equipe:** matilha (Lobinho) ou patrulha (Escoteiro e Sênior), lida de `Associado.equipe`.

## 5. Requisitos funcionais

Cada critério de aceite (CA) tem um teste correspondente na
[matriz do plano](plano.md#6-matriz-de-validação).

### RF-01 — Papel e acesso

- **CA-01.1** O papel "Gestor de Assembleias" existe depois do `migrate` e pode ser pedido pelo
  portal de Acessos.
- **CA-01.2** As páginas `/administracao/assembleias*` só abrem para gestor de assembleias. Os
  demais recebem 403, e o visitante é mandado para o login.
- **CA-01.3** Todo endpoint de escrita da assembleia, das configurações e do switch confere o
  papel no servidor. A chamada direta pela API, sem o papel, é recusada com `PermissionError`.
- **CA-01.4** O card "Assembleias" no índice da Administração e no menu lateral só aparece para
  gestor de assembleias.

### RF-02 — Switch no calendário

- **CA-02.1** Os diálogos de criar e de editar atividade em `/calendario/simulacao_calendario`
  mostram o switch "Assembleia de grupo" só para gestor de assembleias.
- **CA-02.2** Quando um usuário sem o papel edita uma atividade, o valor do switch não se altera,
  mesmo que o parâmetro seja enviado à API.
- **CA-02.3** Ao conciliar, o valor do switch vai para o `Calendario`, inclusive quando quem
  concilia é "Gestor Calendario" sem o papel de assembleias. Uma mudança só no switch também conta
  como diferença na conciliação.
- **CA-02.4** No Desk, o campo `assembleia_de_grupo` do `Calendario` só é editável por gestor de
  assembleias.

### RF-03 — Assembleia nasce do calendário

- **CA-03.1** Um `Calendario` marcado como assembleia cria uma `Assembleia` com:
  - situação "Agendada";
  - tipo "Ordinária";
  - pauta, textos do edital e checklist copiados das configurações.
- **CA-03.2** Existe uma assembleia por dia. Vários eventos marcados no mesmo dia, como as linhas
  de cada seção que a simulação cria, apontam para a mesma assembleia.
- **CA-03.3** Mudar a data, o horário ou o local do evento atualiza a assembleia. Mudar a data para
  um dia que já tem assembleia é recusado, com mensagem.
- **CA-03.4** Desmarcar o switch ou apagar o evento deixa a assembleia como "Desvinculada", sem
  apagar o que já foi feito. Ela sai da lista principal e fica visível no filtro "Desvinculadas".
  Remarcar no mesmo dia a vincula de novo.
- **CA-03.5** A criação enfileira a criação da pasta da assembleia no Drive (RF-12).
- **CA-03.6** Depois do dia da assembleia, a situação passa a "Realizada". O job diário cuida
  disso.

### RF-04 — Lista de assembleias

- **CA-04.1** A página mostra um card por assembleia com:
  - data;
  - tipo;
  - local;
  - situação do edital (rascunho, publicado ou prazo vencido);
  - quantidade de candidaturas e de assuntos gerais.
- **CA-04.2** Os cards ficam em duas seções: "Próximas", com data maior ou igual a hoje e em ordem
  crescente, e "Já realizadas", em ordem decrescente.
- **CA-04.3** Sem assembleia nenhuma, aparece o estado vazio com o mascote e a instrução de marcar
  a atividade no calendário.
- **CA-04.4** O botão "Configurações" leva às configurações gerais.

### RF-05 — Configurações gerais

- **CA-05.1** Os campos editáveis no portal são:
  - dias limite do edital (padrão 30);
  - grupo da Diretoria no WhatsApp;
  - materiais;
  - as duas pautas padrão, com título, votação, finalidade e orientação de condução;
  - quem vota;
  - os prazos;
  - manter o formulário aberto sem candidatos;
  - vagas da comissão fiscal;
  - os textos do topo e do rodapé do edital;
  - o modelo de ata.
- **CA-05.2** Os prazos de mesa, diretoria, comissão fiscal, delegado e assuntos gerais aceitam
  "Sem limite", "N dias" ou "N horas". Os padrões são:

  | Prazo | Padrão |
  |---|---|
  | Mesa | sem limite |
  | Diretoria | 8 dias |
  | Comissão fiscal | 8 dias |
  | Delegado | 1 hora |
  | Assuntos gerais | 2 horas |

  Valor zero ou negativo com "Dias" ou "Horas" é recusado.
- **CA-05.3** Num site novo, ou logo depois do patch, os padrões estão preenchidos:
  - os 9 materiais;
  - a pauta ordinária com 11 itens e a extraordinária com 5, na ordem do pedido;
  - os textos de orientação de condução.

  O patch não sobrescreve o que já foi editado.
- **CA-05.4** Quem vota:
  - escotistas;
  - dirigentes;
  - jovens a partir de N anos;
  - voto por matilha;
  - voto por patrulha no Escoteiro e no Sênior;
  - responsáveis.

  A idade é obrigatória quando "jovens" está ligado.
- **CA-05.5** Mudar as configurações não altera as assembleias já criadas. Os padrões são copiados
  na criação. A aba do edital tem "Restaurar pauta padrão", enquanto o edital não for publicado.
- **CA-05.6** O drive compartilhado, a pasta raiz e o interruptor das pastas são editados no
  Desk, em "Configurações de Assembleias". Pasta inválida ou fora do drive escolhido é recusada no
  save.

### RF-06 — Visão Geral

- **CA-06.1** Os campos editáveis são:
  - tipo (Ordinária ou Extraordinária);
  - responsável pelo credenciamento, num combobox de associados ativos com 18 anos ou mais e de
    responsáveis;
  - hora da primeira e da segunda convocação.

  A data e o local vêm do calendário e são só leitura, com o link para o evento.
- **CA-06.2** Trocar o tipo, enquanto o edital não for publicado, pergunta se a pauta deve ser
  trocada pela padrão do novo tipo.
- **CA-06.3** O presidente e o secretário da mesa aparecem só para leitura. Eles são gravados na
  aba Ata.
- **CA-06.4** Cada formulário aparece com o link copiável, o estado (aberto, fechado ou "não
  previsto na pauta") e o prazo calculado. O link da diretoria só existe quando a assembleia é
  eletiva.
- **CA-06.5** O botão "Página de candidaturas" abre a página pública.
- **CA-06.6** O checklist é dividido em três fases:
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
- **CA-06.7** "Divulgar o edital" é marcado sozinho quando o edital é publicado e não pode ser
  desmarcado à mão. Os demais itens são marcados à mão e guardam quem marcou e quando.

### RF-07 — Edital de convocação

- **CA-07.1** A pauta pode ser editada: incluir, excluir e reordenar itens, renomear, marcar se o
  item tem votação e escolher a finalidade.
- **CA-07.2** Os textos de antes e de depois da pauta são editáveis. O texto de depois traz as
  orientações.
- **CA-07.3** Ficam também na aba a data de publicação e a opção "incluir links de candidatura e
  de assuntos gerais". Com a opção marcada, o documento lista um link para cada formulário previsto
  na pauta.
- **CA-07.4** "Gerar PDF" gera o rascunho no timbrado (RF-12), sem publicar.
- **CA-07.5** "Marcar como publicado" pede confirmação, grava `edital_publicado_em` e a data de
  publicação (hoje, se estiver vazia), gera a versão final e marca o checklist.
- **CA-07.6** Com o edital publicado, o servidor recusa mudanças:
  - nos textos;
  - na pauta (título, votação, finalidade, ordem, inclusão e exclusão);
  - na data de publicação;
  - na opção dos links;
  - no tipo da assembleia.

  A tela mostra tudo só para leitura e deixa só baixar o PDF final. A marcação de "concluído" do
  item continua livre (RF-11).
- **CA-07.7** Depois de publicado, o PDF baixado é sempre o da versão final. Ele não é gerado de
  novo.

### RF-08 — Lista de presença

- **CA-08.1** "Gerar lista" monta os votantes pelas regras de quem vota, na data da assembleia:
  - **Escotistas e Dirigentes:** os associados ativos com essa `categoria` entram quando o
    Check correspondente está ligado.
  - **Jovem com a idade mínima ou mais:** o beneficiário ativo vota por si, quando "jovens" está
    ligado.
  - **Jovem abaixo da idade, ou com "jovens" desligado:** com "responsáveis" ligado, entra uma
    linha com o nome do jovem e "representado por seu responsável legal".
  - **Ramo com voto por equipe:** os jovens do ramo não entram um a um, nem representados. Entra
    uma linha "Representante — <equipe>" para cada equipe distinta entre os beneficiários ativos
    do ramo. Os ramos possíveis são Lobinho (matilha), Escoteiro e Sênior (patrulha).
- **CA-08.2** O beneficiário de um ramo com voto por equipe que não tem equipe aparece num aviso,
  "N jovens do ramo X sem equipe cadastrada", com o link para os associados. Ele não gera linha.
- **CA-08.3** Uma mesma pessoa aparece uma vez só. Quem é escotista e dirigente fica na primeira
  categoria.
- **CA-08.4** É possível incluir uma pessoa à mão, num combobox de associados e responsáveis ou
  por um nome livre, e remover qualquer linha. Gerar de novo mantém as inclusões manuais e não
  traz de volta as linhas removidas.
- **CA-08.5** A lista mostra o total por tipo de voto.
- **CA-08.6** "Exportar PDF" gera a lista em retrato no timbrado, com as colunas Nome |
  Representado por | Assinatura, em ordem alfabética:
  - A coluna "Representado por" tem uma linha em branco para o nome do responsável nas linhas
    "representado por seu responsável legal".
  - Nas linhas de equipe, a mesma coluna tem uma linha em branco para o nome do representante.
- **CA-08.7** A lista pode ser editada até o fim do dia da assembleia.

### RF-09 — Ata

- **CA-09.1** Os campos da aba são:
  - hora de início e de término;
  - presidente e secretário da mesa, num combobox de associados ativos com 16 anos ou mais e de
    responsáveis;
  - anotações do secretário.
- **CA-09.2** Todo campo da aba é salvo sozinho cerca de 1 s depois da última alteração. Um
  indicador mostra "Salvando…", "Salvo às HH:MM" ou "Não foi possível salvar — tentar de novo".
  Sair da página com alteração pendente pede confirmação.
- **CA-09.3** Se outra aba ou outra pessoa salvou a ata depois do carregamento, o salvamento é
  recusado com "A ata foi alterada em outra janela", e nada é sobrescrito sem aviso.
- **CA-09.4** "Gerar ata com IA" junta o modelo de ata das configurações, as anotações e os dados
  da assembleia:
  - data, local e convocações;
  - mesa;
  - pauta, com o que foi concluído;
  - total de votantes na lista;
  - candidatos.

  O texto gerado vai para um campo novo, "Texto da ata", já formatado e editável. Esse campo também
  é salvo sozinho.
- **CA-09.5** A geração roda em segundo plano. O botão fica em "Gerando…" e a tela acompanha até
  terminar. Uma falha mostra uma mensagem amigável e não apaga o texto que já existia.
- **CA-09.6** Gerar de novo com o "Texto da ata" já preenchido pede confirmação antes de
  substituir.
- **CA-09.7** O LLM recebe só nomes, cargos e o conteúdo das anotações. CPF, telefone e e-mail
  não são enviados.
- **CA-09.8** "Gerar PDF da versão final" gera a ata no timbrado a partir do "Texto da ata" (RF-12).
  Sem texto, o botão fica desabilitado.

### RF-10 — Candidaturas e assuntos gerais (aba)

- **CA-10.1** A aba lista as candidaturas ativas de cada cargo (presidente da mesa, secretário da
  mesa, delegado, comissão fiscal), com nome, registro escoteiro, motivação e biografia.
- **CA-10.2** Cada chapa da diretoria aparece com quem a inscreveu e, para cada função eleita,
  o membro, o registro, a motivação e a biografia.
- **CA-10.3** Os assuntos gerais aparecem com quem submeteu, o horário e o conteúdo, em ordem de
  chegada.
- **CA-10.4** Quem gerencia pode marcar uma candidatura ou chapa como retirada. Ela some da página
  pública e continua no histórico.
- **CA-10.5** O botão "Página de candidaturas" abre a página pública.

### RF-11 — Auxílio para condução

- **CA-11.1** A aba lista os itens da pauta em ordem, cada um com uma checkbox de concluído (salvo
  sozinho) e a orientação de como conduzir.
- **CA-11.2** A orientação de cada item vem do item padrão das configurações, ou fica em branco
  num item criado à mão, e pode ser editada aqui enquanto a assembleia não for "Realizada". Itens
  com votação mostram o selo "Votação".
- **CA-11.3** No item de eleição, a orientação é acompanhada da lista de candidatos ao cargo.

### RF-12 — Drive e documentos no timbrado

- **CA-12.1** Com as pastas habilitadas, cada assembleia ganha uma pasta
  `Assembleia <Ordinária|Extraordinária> - dd-MM-aaaa` dentro da pasta raiz. O link fica na
  Visão Geral.
- **CA-12.2** Rodar de novo não cria uma segunda pasta: a pasta com o mesmo nome é reaproveitada.
  Pasta raiz ou drive faltando registram o motivo e não travam a assembleia.
- **CA-12.3** O edital, a lista de presença e a ata são gerados assim:
  1. Copia o Google Doc de `Configuracoes de Comunicacao.link_papel_timbrado` para a pasta da
     assembleia.
  2. Insere o conteúdo: títulos, parágrafos, negrito, listas e tabela.
  3. Exporta o PDF e o guarda na mesma pasta.

  O navegador recebe o PDF para download. O Doc editável fica na pasta, e o link dele aparece na
  aba.
- **CA-12.4** Gerar de novo o mesmo documento (um rascunho) substitui o Doc e o PDF anteriores em
  vez de acumular arquivos. O edital final é um arquivo à parte, "(publicado)", e nunca é
  substituído.
- **CA-12.5** Sem timbrado configurado, sem a pasta da assembleia ou com erro do Google, aparece
  uma mensagem que diz o que falta, sem o modal de erro de servidor.

### RF-13 — Formulários com login

- **CA-13.1** As rotas são:
  - `/assembleias/candidatura?assembleia=…&cargo=mesa|delegado|diretoria|comissao_fiscal`
  - `/assembleias/assunto_geral?assembleia=…`

  O visitante é mandado para o login e volta para o formulário.
- **CA-13.2** O candidato é quem está logado. Um usuário sem Associado ou Responsável vinculado vê
  "Seu usuário não está ligado a um cadastro do grupo" e não consegue enviar.
- **CA-13.3** Um formulário está aberto quando:
  1. a assembleia está "Agendada";
  2. a pauta tem a finalidade correspondente;
  3. agora é antes de (primeira convocação − prazo do cargo). "Sem limite" fecha no início da
     primeira convocação.
- **CA-13.4** Com `manter_aberto_sem_candidatos` ligado, o formulário fica aberto depois do prazo,
  até a primeira convocação, enquanto faltar candidato:

  | Cargo | Falta candidato quando |
  |---|---|
  | Mesa | nenhum presidente ou nenhum secretário ativo |
  | Comissão fiscal | menos candidatos ativos que `vagas_comissao_fiscal` |
  | Diretoria | nenhuma chapa com todas as funções eleitas preenchidas |
  | Delegado | nenhum candidato ativo |

- **CA-13.5** Mesa: o candidato escolhe presidente ou secretário, confirma a candidatura e
  preenche, se quiser, a biografia e a motivação. A mesma pessoa pode se candidatar aos dois cargos,
  mas a cada um só uma vez.
- **CA-13.6** Delegado e comissão fiscal: confirmação, biografia e motivação opcionais. Uma
  candidatura por pessoa e cargo.
- **CA-13.7** Diretoria:
  - Há um combobox para cada função eleita, com associados ativos com 18 anos ou mais e
    responsáveis.
  - Cada membro tem biografia e motivação opcionais.
  - O envio exige a confirmação e todas as funções preenchidas.
  - Quem envia fica gravado como responsável pela chapa.
  - A mesma pessoa não pode aparecer em duas funções da mesma chapa.
- **CA-13.8** Assunto geral: o texto é obrigatório (até 2.000 caracteres) e há a confirmação. Quem
  envia e o horário ficam gravados.
- **CA-13.9** Fora do prazo, o formulário mostra "Inscrições encerradas em dd/mm às HH:MM". O
  servidor recusa o envio mesmo que a página tenha sido aberta antes do prazo.
- **CA-13.10** Depois de enviar, o usuário vê a confirmação com o resumo do que enviou.

### RF-14 — Página pública de candidaturas

- **CA-14.1** `/assembleias/candidaturas?assembleia=…` abre sem login, com o cabeçalho da UEL.
- **CA-14.2** A página mostra, por cargo, as candidaturas ativas com nome, registro escoteiro,
  motivação e biografia, e as chapas da diretoria com os membros por função.
- **CA-14.3** Nenhum outro dado pessoal aparece: CPF, telefone, e-mail, idade e usuário ficam de
  fora.
- **CA-14.4** Assembleia inexistente ou "Desvinculada" mostra "Assembleia não encontrada".
- **CA-14.5** Todo texto vindo de usuário é escapado (biografia, motivação, nome).

### RF-15 — Lembretes do prazo do edital

- **CA-15.1** O job diário das 9h considera as assembleias "Agendadas" com o edital não
  publicado. Para cada uma, d = prazo do edital − hoje.
- **CA-15.2** Os marcos são 60, 30, 25 e 7, cada um com uma janela:

  | Marco | Janela de d |
  |---|---|
  | 60 | 31 a 60 |
  | 30 | 26 a 30 |
  | 25 | 8 a 25 |
  | 7 | 0 a 7 |

  Em cada rodada sai no máximo uma mensagem por assembleia: a do marco cuja janela contém d, e só se
  ele vier depois do último já enviado. Um dia perdido é recuperado sem repetir.
- **CA-15.3** A mensagem vai para `grupo_diretoria_whatsapp` e diz o tipo e a data da assembleia, a
  data limite para publicar o edital, quantos dias faltam e o link da assembleia no portal.
- **CA-15.4** O marco é carimbado só depois do envio confirmado. Uma falha não carimba.
- **CA-15.5** O edital publicado para os lembretes. Sem grupo configurado, nada sai e o resumo do
  job explica por quê.
- **CA-15.6** Todo envio gera um `Log de Mensagem` com o tipo "Grupo da diretoria" e o assunto
  "Prazo do edital da assembleia".

### RF-16 — Equipe no cadastro

- **CA-16.1** O `Associado` ganha o campo `equipe` (texto), editável no Desk e na ficha do portal.
- **CA-16.2** A importação do PDF do Paxtu grava a "Equipe: …" de cada associado, sem o prefixo
  vazio, e não apaga uma equipe preenchida à mão quando o PDF não traz a linha.
- **CA-16.3** As equipes são comparadas sem acento e sem diferença de maiúsculas. "Patrulha Lobo"
  e "patrulha lobo" são a mesma equipe.

## 6. Requisitos não funcionais

- **Segurança:**
  - Toda regra fica no servidor.
  - Os endpoints de formulário validam o login, o vínculo, o prazo e a duplicidade antes de
    gravar.
  - O `ignore_permissions` só é usado na sincronização com o calendário e na gravação controlada
    dos formulários, com a justificativa no código.
  - A página pública tem um `allow_guest` só de leitura, com campos fixos.
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
  publicação. O formulário avisa que esses dados serão públicos.

## 7. Pendências que dependem do estatuto e do último edital

1. Regras de voto: a idade mínima do jovem e se o jovem abaixo da idade é representado; se vota um
   responsável por jovem ou um por família; o voto por equipe.
2. Quem pode se candidatar a cada cargo: idade, categoria, tempo de grupo e registro em dia.
3. Quórum da primeira e da segunda convocação, para o texto do edital e para a orientação de
   condução.
4. Textos padrão do topo e do rodapé do edital, e o modelo de ata.
5. Vagas da comissão fiscal e número de delegados.
6. Orientação de condução de cada item da pauta padrão.
