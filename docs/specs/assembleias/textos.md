# Textos padrão — Assembleias de Grupo

> Spec: [spec.md](spec.md) · Plano: [plano.md](plano.md)

Os textos abaixo são os padrões que o patch grava em **Configurações de Assembleias** e que
cada assembleia copia ao ser criada. Eles vêm de três fontes:

- **Edital:** o edital de convocação de 2026, com o público convocado corrigido para o
  estatuto (art. 9º). O edital de 2026 convocava "representantes dos ramos", e essa redação estava
  errada.
- **Ata:** o modelo de ata usado pelo grupo.
- **Orientações:** o documento de orientações para conduzir a reunião ordinária, completado
  com os itens de eleição da comissão fiscal e da diretoria, que faltavam nele.

Tudo é editável. As variáveis são trocadas por substituição simples (`{nome}`), como na régua de
vencimento. Uma variável desconhecida é recusada ao salvar.

## 1. Variáveis

| Variável | Valor | Exemplo |
|---|---|---|
| `{tipo}` | Tipo em maiúsculas | ORDINÁRIA |
| `{tipo_minusculo}` | Tipo em minúsculas | ordinária |
| `{data}` | Data da assembleia por extenso | 05 de dezembro de 2026 |
| `{data_curta}` | Data da assembleia | 05/12/2026 |
| `{hora_primeira}` / `{hora_segunda}` | Horários das convocações | 14:30 / 15:00 |
| `{local}` | Local da assembleia | nossa sede |
| `{nome_uel}` | `Definicao da UEL.nome_da_uel` | Grupo Escoteiro Professora Inah de Mello |
| `{numeral}` | Numeral e UF da UEL | 147/SP |
| `{cnpj}` | `Definicao da UEL.cnpj` | |
| `{endereco_sede}` | Rua, número e bairro da `Definicao da UEL` | |
| `{cidade}` | `Configuracoes de Assembleias.cidade` | Santo André |
| `{data_publicacao}` | Data de publicação do edital por extenso | 05 de novembro de 2026 |
| `{diretor_presidente}` | Quem ocupa hoje a função de presidente (`utils/diretoria.py`) | |
| `{ano}` / `{ano_anterior}` | Ano da assembleia e o anterior | 2026 / 2025 |
| `{gestao}` | Biênio da diretoria eleita: o seguinte ao ano da assembleia no segundo semestre, o próprio ano no primeiro | 2027-2028 |
| `{exercicio}` | Ano do balanço apreciado: o próprio ano no segundo semestre, o anterior no primeiro (art. 40) | 2026 |
| `{data_assembleia_anterior}` | Data da última assembleia cadastrada antes desta, ou "[data]" | 06/12/2025 |

Os títulos da pauta são resolvidos quando a assembleia é criada, porque viram texto da própria
assembleia. Os textos do edital são resolvidos ao gerar o documento, e a aba mostra uma
pré-visualização.

## 2. Edital

### Texto antes da pauta

> De acordo com o que estabelece o Estatuto da União dos Escoteiros do Brasil, o Regulamento
> Regional e o Estatuto do {nome_uel}, ficam CONVOCADOS todos os associados com registro ativo e os
> responsáveis legais dos beneficiários com idade entre 6,5 e 15 anos para a REUNIÃO {tipo} DA
> ASSEMBLEIA DE GRUPO, que se dará em {local} no próximo dia {data}, às {hora_primeira} em
> primeira convocação, e às {hora_segunda}, em segunda convocação, com qualquer número de
> presentes.
>
> Assuntos a serem deliberados na ordem do dia:

### Texto depois da pauta

O bloco com os links dos formulários é montado pelo código, entre a pauta e este texto, quando a
opção está marcada (ver RF-06 da spec).

> A ASSEMBLEIA é o órgão máximo do Grupo, sendo de suma importância a participação de todos.
> Lembramos que, para ter direito a voz e voto, é necessário que o associado cumpra as exigências
> estabelecidas no Estatuto do Grupo e esteja regularizado conforme o estatuto da UEB.
>
> {cidade}, {data_publicacao}.
>
> \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_
> {diretor_presidente}
> Diretor Presidente

A linha de sublinhados abre a assinatura: no documento, ela ganha espaço acima para assinar, e o
nome e o cargo ficam logo abaixo. `{diretor_presidente}` é uma pessoa só: a lotação em vigor mais
recente da função de presidente.

### Lista de formulários (gerada)

Um item com marcador para cada formulário previsto na pauta; "formulário eletrônico" é o link,
sublinhado e clicável.

> - Candidaturas para {cargo} devem ser encaminhadas pelo [formulário eletrônico]({link}) até {prazo}.
> - Propostas de assuntos gerais devem ser encaminhadas pelo [formulário eletrônico]({link}) até {prazo}.

`{prazo}` é por extenso: "27 de novembro de 2026" para prazo em dias; "uma hora antes da
primeira convocação" ou "duas horas antes da primeira convocação" para prazo em horas.

### Formatação no papel timbrado

Calibri 11 no corpo, justificado e sem recuo; títulos centralizados em negrito (14 e 12). Na lista
de presença, a tabela ocupa a largura útil da página (Nome 42%, Representado por 30%, Assinatura
28%), só com linhas horizontais, cabeçalho sombreado e repetido a cada página, linhas pares
sombreadas e nenhuma linha partida entre páginas.

## 3. Pautas padrão

Coluna "Vot." = `tem_votacao`.

### Ordinária

| # | Título | Vot. | Finalidade |
|---|---|---|---|
| 1 | Eleição da mesa diretora: Presidente e Secretário(a) | sim | Eleição da mesa |
| 2 | Leitura do Edital de Convocação | não | Leitura do edital |
| 3 | Apreciação e deliberação da ata da Assembleia anterior (realizada em {data_assembleia_anterior}) | sim | Ata anterior |
| 4 | Apreciação e deliberação do balanço financeiro do exercício de {exercicio} juntamente com parecer da Comissão Fiscal | sim | — |
| 5 | Apreciação e deliberação do relatório da Diretoria da UEL | sim | — |
| 6 | Apreciação e deliberação do relatório das Seções | sim | — |
| 7 | Eleição de Delegados para a Assembleia Regional | sim | Eleição de delegados |
| 8 | Apresentação e eleição dos candidatos à Comissão Fiscal Local - Gestão {gestao} | sim | Eleição da comissão fiscal |
| 9 | Apresentação e eleição das chapas para Direção Local - Gestão {gestao} | sim | Eleição da diretoria |
| 10 | Assuntos Gerais | não | Assuntos gerais |
| 11 | Encerramento | não | Encerramento |

Os itens 8 e 9 são bienais (art. 7º, § 2º). Numa ordinária sem eleição de diretoria, basta
excluí-los da pauta da assembleia: os formulários e os passos pós-eleição do checklist somem
junto.

### Extraordinária

| # | Título | Vot. | Finalidade |
|---|---|---|---|
| 1 | Eleição da mesa diretora: Presidente e Secretário(a) | sim | Eleição da mesa |
| 2 | Leitura do Edital de Convocação | não | Leitura do edital |
| 3 | Apreciação e deliberação da ata da Assembleia anterior (realizada em {data_assembleia_anterior}) | sim | Ata anterior |
| 4 | Assuntos Gerais | não | Assuntos gerais |
| 5 | Encerramento | não | Encerramento |

## 4. Orientações gerais de condução

Aparecem no topo da aba "Auxílio para condução". O padrão é o resumo de tipos de votação das
orientações do grupo:

> **Votação por aclamação.** Manifestação verbal, sem contagem individual. Pode ser usada nas
> eleições com chapa ou candidatura única e em aprovações sem oposição.
>
> **Votação simbólica.** Por senha visual: levantar o cartão para aprovar e depois para reprovar,
> e quem tiver mais votos vence.
>
> **Votação nominal.** O voto de cada um é identificado e registrado. Qualquer membro da
> assembleia pode pedi-la ao presidente.
>
> **Votação secreta.** Por cédula, sem identificar o eleitor. É obrigatória em eleições e
> cassações de mandato.
>
> **Unitária ou de aprovação.** Na unitária, cada pessoa vota em uma só opção entre várias. Na de
> aprovação, vota se aprova ou não o assunto.
>
> **Lembretes do estatuto.**
> - É vedada a delegação de voto, sob qualquer forma.
> - Matéria fora da ordem do dia só entra se apresentada por escrito até 2 horas antes do início,
>   a critério da comissão de assuntos gerais ou, na falta dela, do presidente da assembleia.
> - O presidente pode suspender a reunião a bem dos trabalhos.
> - Se o balanço ou o orçamento for rejeitado, a diretoria tem 30 dias para reapresentá-lo, e a
>   reunião fica em sessão permanente.

## 5. Orientação por item

A orientação é ligada pela finalidade. Um item sem finalidade usa a orientação de "aprovação
simples", que é a mesma dos itens 4 a 6.

**Eleição da mesa.**
- O diretor presidente da UEL abre a reunião e informa se houve candidaturas prévias para
  presidente da assembleia: elas aparecem logo abaixo. Sem candidatos, pede voluntários.
- Com um só candidato, a votação é por aclamação. Com mais de um, é unitária e secreta, por
  cédula.
- Empossado, o presidente conduz a eleição do secretário pela mesma regra.
- O presidente pode pedir 3 candidatos para a comissão de escrutínio, que conta os votos. Com
  exatamente 3, pergunta se alguém se opõe e, sem oposição, a comissão é eleita por aclamação. Com
  mais de 3, a votação é unitária e secreta.
- Se houve assunto geral enviado pelo formulário (a quantidade aparece abaixo), forma-se também a
  comissão de assuntos gerais, com 3 membros e a mesma regra.

**Leitura do edital.** O presidente abre o edital e faz a leitura, que indica a ordem dos assuntos
do dia.

**Ata anterior.**
- Informar que a ata foi enviada antes para apreciação.
- Perguntar se alguém tem objeção à aprovação. Sem objeção, ela é aprovada por aclamação.

**Aprovação simples** (balanço, relatório da diretoria, relatório das seções e itens sem
finalidade):
- Pedir a apresentação. No balanço, a diretoria financeira apresenta o relatório e a comissão
  fiscal apresenta o parecer anual.
- Perguntar se alguém se opõe. Sem oposição, o item é aprovado por aclamação.
- Com oposição, fazer uma votação simbólica: cartões para aprovar, depois para reprovar, e vence
  o que tiver mais votos.

**Eleição de delegados.**
- Informar o número de vagas: 1 delegado para cada fração de 50 associados, com o número
  calculado abaixo. Devem ser eleitos ao menos tantos suplentes quanto vagas.
- Informar onde será a próxima Assembleia Regional.
- Conferir as candidaturas prévias, que aparecem abaixo. Se forem menos que as vagas, abrir
  inscrições na hora (o estatuto permite até o momento da eleição).
- Com mais candidatos que vagas, a votação é unitária e secreta, por cédula. Os mais votados são
  os titulares, e os demais ficam como suplentes.
- Com candidatos em número igual ou menor que as vagas, perguntar se alguém se opõe. Sem oposição,
  todos são eleitos por aclamação.
- Sugerir a ordem de suplência por idade, do mais novo para o mais velho. Sem oposição, ela é
  aprovada por aclamação.

**Eleição da comissão fiscal.**
- São 3 titulares e 3 suplentes, com mandato de 2 anos. O voto é unitário e secreto, e cada
  eleitor vota em um só candidato.
- Os 3 mais votados são titulares, e os 3 seguintes são suplentes, na ordem de votação. Depois,
  os titulares elegem entre si o presidente da comissão.
- Com candidatura única por vaga, pode ser por aclamação.
- Impugnações por escrito são aceitas até o início da votação. Se faltarem candidatos, aceitar
  inscrições na hora.

**Eleição da diretoria.**
- A eleição é por chapa, com diretor presidente, diretor financeiro e diretor administrativo, e o
  mandato é de 2 anos. As chapas inscritas aparecem abaixo.
- Um mesmo candidato não pode estar em duas chapas.
- Com chapa única, a votação pode ser por aclamação. Com mais de uma, é secreta.
- Impugnações por escrito são aceitas até o início da votação. Impugnado um membro, a chapa pode
  indicar um substituto.
- Responsável sem registro que for eleito deve se registrar até a posse, ou em 30 dias se a posse
  for no mesmo dia.
- Não há reeleição por mais de dois mandatos consecutivos na mesma função.

**Assuntos gerais.** Os assuntos enviados aparecem abaixo. Se não houve nenhum, informar isso. Se
houve, a comissão de assuntos gerais os apresenta.

**Encerramento.** Declarar encerrada a reunião da Assembleia de Grupo, com o dia e o horário
exato, que entram na ata.

## 6. Modelo de ata

É a base da geração por IA (RF-08). Os marcadores `[ENTRE COLCHETES]` são preenchidos com os dados
da assembleia e as anotações do secretário. O que não puder ser preenchido continua como
`[A CONFIRMAR: …]`.

> No dia [DIA] de [MÊS] de [ANO], às [HORA INÍCIO], reuniram-se os membros devidamente registrados
> do {nome_uel} - {numeral}, CNPJ {cnpj}, na sede do Grupo Escoteiro, sito a {endereco_sede} -
> {cidade}, para deliberar sobre os assuntos apontados na ordem do dia do edital de convocação da
> reunião [ORDINÁRIA / EXTRAORDINÁRIA] da Assembleia de Grupo, publicado no dia [DATA DO EDITAL].
> O quórum presente na reunião é de [QUANTIDADE DE PRESENTES PELA LISTA DE PRESENÇA]. O diretor
> presidente do Grupo Escoteiro, [NOME DO DIRETOR PRESIDENTE], informou [SE HOUVE OU NÃO
> CANDIDATURAS PRÉVIAS PARA A MESA] em atendimento ao **item 1 do edital de convocação (Eleição
> da mesa diretora: Presidente e Secretário(a))**.
>
> [DESCRIÇÃO DE COMO SE DEU A ELEIÇÃO DA MESA]
>
> [PARA CADA ITEM SEGUINTE DA PAUTA, UM PARÁGRAFO QUE COMEÇA COM "**Em atendimento ao item N do
> edital de convocação (TÍTULO DO ITEM)**", com quem apresentou, os questionamentos relevantes e
> o resultado da votação: por aclamação, ou com votos a favor, abstenções e votos contrários.
> Nas eleições: candidatos, forma de votação, eleitos e suplentes, com a ordem de suplência.]
>
> Por fim, o(a) presidente eleito(a) da mesa, [NOME DO PRESIDENTE DA MESA], encerrou a reunião
> [ordinária / extraordinária] da Assembleia de Grupo às [HORÁRIO DE TÉRMINO POR EXTENSO] e eu,
> [NOME DO SECRETÁRIO], redigi e assino a presente ata.
>
> \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_ [NOME PRESIDENTE ASSEMBLEIA]
> \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_ [NOME SECRETÁRIO ASSEMBLEIA]
> \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_ [NOME DIRETOR PRESIDENTE]

## 7. Lembrete do prazo do edital (WhatsApp)

> 📣 *Edital da Assembleia de Grupo*
>
> A reunião {tipo_minusculo} da Assembleia de Grupo está marcada para *{data}*. Pelo estatuto, o
> edital de convocação precisa ser publicado até *{prazo_edital}*: {faltam}.
>
> Prepare e publique o edital no GRIS: {link}
>
> 🤖 _Esta é uma mensagem automática do GRIS._

`{faltam}` é "faltam *N* dias" (ou "falta *1* dia") e, no dia do prazo, "o prazo termina *hoje*".
