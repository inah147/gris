# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Nomes, opções e textos padrão das assembleias.

Os textos espelham `docs/specs/assembleias/textos.md`: são o que o patch grava em
Configurações de Assembleias e o que cada assembleia copia ao ser criada. Depois disso
passam a ser da gestão — mudar este arquivo não altera o que já foi gravado.
"""

from __future__ import annotations

DOCTYPE_ASSEMBLEIA = "Assembleia"
DOCTYPE_CONFIGURACOES = "Configuracoes de Assembleias"
DOCTYPE_CANDIDATURA = "Candidatura de Assembleia"
DOCTYPE_CHAPA = "Chapa de Assembleia"
DOCTYPE_ASSUNTO = "Assunto Geral de Assembleia"

ROLE_GESTOR_ASSEMBLEIAS = "Gestor de Assembleias"

TIPO_ORDINARIA = "Ordinária"
TIPO_EXTRAORDINARIA = "Extraordinária"

# --------------------------------------------------------------------------------------
# Finalidades: ligam o item da pauta aos formulários, ao checklist e às orientações.
# --------------------------------------------------------------------------------------

FINALIDADE_MESA = "Eleição da mesa"
FINALIDADE_LEITURA = "Leitura do edital"
FINALIDADE_ATA_ANTERIOR = "Ata anterior"
FINALIDADE_DELEGADOS = "Eleição de delegados"
FINALIDADE_COMISSAO_FISCAL = "Eleição da comissão fiscal"
FINALIDADE_DIRETORIA = "Eleição da diretoria"
FINALIDADE_ASSUNTOS_GERAIS = "Assuntos gerais"
FINALIDADE_ENCERRAMENTO = "Encerramento"

FINALIDADES = (
	FINALIDADE_MESA,
	FINALIDADE_LEITURA,
	FINALIDADE_ATA_ANTERIOR,
	FINALIDADE_DELEGADOS,
	FINALIDADE_COMISSAO_FISCAL,
	FINALIDADE_DIRETORIA,
	FINALIDADE_ASSUNTOS_GERAIS,
	FINALIDADE_ENCERRAMENTO,
)

# O que cada finalidade aciona, para quem escolhe o tipo do item na pauta.
DESCRICAO_DA_FINALIDADE = {
	"": "Aprovação simples, como balanço e relatórios. Não abre formulário.",
	FINALIDADE_MESA: "Abre a candidatura à mesa (presidente e secretário) e mostra os candidatos na sessão.",
	FINALIDADE_LEITURA: "Leitura do edital no início da sessão.",
	FINALIDADE_ATA_ANTERIOR: "Apreciação da ata da assembleia anterior.",
	FINALIDADE_DELEGADOS: "Abre a candidatura a delegado e mostra as vagas e os candidatos na sessão.",
	FINALIDADE_COMISSAO_FISCAL: "Abre a candidatura à comissão fiscal e mostra titulares, suplentes e candidatos na sessão.",
	FINALIDADE_DIRETORIA: "Abre a inscrição de chapas e torna a assembleia eletiva: cartório, banco e Receita entram no checklist.",
	FINALIDADE_ASSUNTOS_GERAIS: "Abre o envio de assuntos gerais e lista os enviados na sessão.",
	FINALIDADE_ENCERRAMENTO: "Encerramento, com o horário que vai para a ata.",
}

# --------------------------------------------------------------------------------------
# Formulários. A chave é a da URL (`?cargo=`) e do prefixo dos prazos nas configurações.
# --------------------------------------------------------------------------------------

FORMULARIO_MESA = "mesa"
FORMULARIO_DELEGADO = "delegado"
FORMULARIO_DIRETORIA = "diretoria"
FORMULARIO_COMISSAO_FISCAL = "comissao_fiscal"
FORMULARIO_ASSUNTOS_GERAIS = "assuntos_gerais"

FINALIDADE_DO_FORMULARIO = {
	FORMULARIO_MESA: FINALIDADE_MESA,
	FORMULARIO_DELEGADO: FINALIDADE_DELEGADOS,
	FORMULARIO_DIRETORIA: FINALIDADE_DIRETORIA,
	FORMULARIO_COMISSAO_FISCAL: FINALIDADE_COMISSAO_FISCAL,
	FORMULARIO_ASSUNTOS_GERAIS: FINALIDADE_ASSUNTOS_GERAIS,
}

CARGO_PRESIDENTE_MESA = "Presidente da mesa"
CARGO_SECRETARIO_MESA = "Secretário da mesa"
CARGO_DELEGADO = "Delegado"
CARGO_COMISSAO_FISCAL = "Comissão Fiscal"

CARGOS_DO_FORMULARIO = {
	FORMULARIO_MESA: (CARGO_PRESIDENTE_MESA, CARGO_SECRETARIO_MESA),
	FORMULARIO_DELEGADO: (CARGO_DELEGADO,),
	FORMULARIO_COMISSAO_FISCAL: (CARGO_COMISSAO_FISCAL,),
}

# Idade mínima de candidatura (anos). A mesa é eleita "dentre seus membros" (art. 7º, § 7º),
# e o pedido original fixou 16 anos; os demais cargos são de adulto.
IDADE_MINIMA_CANDIDATURA = {
	FORMULARIO_MESA: 16,
	FORMULARIO_DELEGADO: 18,
	FORMULARIO_COMISSAO_FISCAL: 18,
	FORMULARIO_DIRETORIA: 18,
}

PRAZO_SEM_LIMITE = "Sem limite"
PRAZO_DIAS = "Dias"
PRAZO_HORAS = "Horas"

# --------------------------------------------------------------------------------------
# Lista de presença
# --------------------------------------------------------------------------------------

LINHA_ESCOTISTA = "Escotista"
LINHA_DIRIGENTE = "Dirigente"
LINHA_ASSOCIADO = "Associado"
LINHA_JOVEM = "Jovem"
LINHA_JOVEM_REPRESENTADO = "Jovem representado"
LINHA_EQUIPE = "Representante de equipe"
LINHA_MANUAL = "Incluído manualmente"

# --------------------------------------------------------------------------------------
# Checklist
# --------------------------------------------------------------------------------------

CHECKLIST_DIVULGAR_EDITAL = "divulgar_edital"

# (chave, fase, título, só em assembleia eletiva)
CHECKLIST_PADRAO = (
	("elaborar_edital", "Antes", "Elaborar e aprovar o edital de convocação", 0),
	(CHECKLIST_DIVULGAR_EDITAL, "Antes", "Divulgar o edital de convocação até o prazo", 0),
	("imprimir_lista", "Antes", "Imprimir a lista de presença", 0),
	("separar_materiais", "No dia", "Separar os materiais", 0),
	("preparar_credenciamento", "No dia", "Preparar o credenciamento", 0),
	("finalizar_ata", "Depois", "Finalizar a ata", 0),
	("assinar_ata", "Depois", "Assinar a ata", 0),
	("registrar_cartorio", "Depois", "Registrar a ata em cartório", 1),
	("alterar_banco", "Depois", "Alterar os dados bancários com os novos responsáveis", 1),
	("alterar_receita", "Depois", "Alterar os dados na Receita Federal com os novos responsáveis", 1),
)

MATERIAIS_PADRAO = (
	"Projetor",
	"Telão",
	"Extensão",
	"Cartões de votação",
	"Três mesas",
	"Cadeiras",
	"Bandeira",
	"Microfone",
	"Caixas de som",
)

# --------------------------------------------------------------------------------------
# Edital
# --------------------------------------------------------------------------------------

TEXTO_TOPO_EDITAL = (
	"De acordo com o que estabelece o Estatuto da União dos Escoteiros do Brasil, o Regulamento "
	"Regional e o Estatuto do {nome_uel}, ficam CONVOCADOS todos os associados com registro ativo e os "
	"responsáveis legais dos beneficiários com idade entre 6,5 e 15 anos para a REUNIÃO {tipo} DA "
	"ASSEMBLEIA DE GRUPO, que se dará em {local} no próximo dia {data}, às {hora_primeira} em "
	"primeira convocação, e às {hora_segunda}, em segunda convocação, com qualquer número de "
	"presentes.\n\n"
	"Assuntos a serem deliberados na ordem do dia:"
)

TEXTO_RODAPE_EDITAL = (
	"A ASSEMBLEIA é o órgão máximo do Grupo, sendo de suma importância a participação de todos. "
	"Lembramos que, para ter direito a voz e voto, é necessário que o associado cumpra as exigências "
	"estabelecidas no Estatuto do Grupo e esteja regularizado conforme o estatuto da UEB.\n\n"
	"{cidade}, {data_publicacao}.\n\n"
	"____________________________________\n"
	"{diretor_presidente}\n"
	"Diretor Presidente"
)

# Versão anterior do texto padrão, para o patch trocar só onde ninguém editou.
TEXTO_RODAPE_EDITAL_ANTIGO = (
	"A ASSEMBLEIA é o órgão máximo do Grupo, sendo de suma importância a participação de todos. "
	"Lembramos que, para ter direito a voz e voto, é necessário que o associado cumpra as exigências "
	"estabelecidas no Estatuto do Grupo e esteja regularizado conforme o estatuto da UEB.\n\n"
	"{cidade}, {data_publicacao}.\n\n"
	"{diretor_presidente}\n"
	"Diretor Presidente"
)

# Bloco dos formulários no edital: uma frase de abertura e um item por formulário
# previsto na pauta, com o texto do link clicável e o prazo por extenso.
INTRO_LINKS_EDITAL = (
	"As candidaturas e submissões para assuntos gerais devem ser realizadas de maneira digital, "
	"através dos links abaixo:"
)
LINHA_LINK_EDITAL = "- {rotulo}: [{texto}]({link}) (até {prazo})"

# --------------------------------------------------------------------------------------
# Orientações de condução
# --------------------------------------------------------------------------------------

ORIENTACOES_GERAIS = """**Votação por aclamação.** Manifestação verbal, sem contagem individual. Pode ser usada nas eleições com chapa ou candidatura única e em aprovações sem oposição.

**Votação simbólica.** Por senha visual: levantar o cartão para aprovar, depois para reprovar. Vence quem tiver mais votos.

**Votação nominal.** O voto de cada um é identificado e registrado. Qualquer membro da assembleia pode pedi-la ao presidente.

**Votação secreta.** Por cédula, sem identificar o eleitor. É obrigatória em eleições e cassações de mandato.

**Unitária ou de aprovação.** Na unitária, cada pessoa vota em uma só opção entre várias; na de aprovação, vota se aprova ou não o assunto.

**Lembretes do estatuto**

- É vedada a delegação de voto, sob qualquer forma.
- Matéria fora da ordem do dia só entra se apresentada por escrito até 2 horas antes do início, a critério da comissão de assuntos gerais ou, na falta dela, do presidente da assembleia.
- O presidente pode suspender a reunião a bem dos trabalhos.
- Se o balanço ou o orçamento for rejeitado, a diretoria tem 30 dias para reapresentá-lo, e a reunião fica em sessão permanente."""

ORIENTACAO_APROVACAO_SIMPLES = """- Pedir a apresentação do assunto. No balanço, a diretoria financeira apresenta o relatório e a comissão fiscal apresenta o parecer anual.
- Perguntar se alguém se opõe à aprovação.
    - Sem oposição: aprovado por aclamação.
    - Com oposição: votação simbólica — cartões para aprovar, depois para reprovar. Vence o que tiver mais votos."""

ORIENTACAO_POR_FINALIDADE = {
	FINALIDADE_MESA: """- O diretor presidente da UEL abre a reunião e informa se houve candidaturas prévias para presidente da assembleia (elas aparecem abaixo). Sem candidatos, pede voluntários.
    - Um só candidato: votação por aclamação.
    - Mais de um: votação unitária e secreta, por cédula.
- Empossado, o presidente conduz a eleição do secretário pela mesma regra.
- O presidente pode pedir 3 candidatos para a comissão de escrutínio (quem conta os votos).
    - Exatamente 3: perguntar se alguém se opõe; sem oposição, eleita por aclamação.
    - Mais de 3: votação unitária e secreta.
- Se houve assunto geral enviado pelo formulário (a quantidade aparece abaixo), formar também a comissão de assuntos gerais, com 3 membros e a mesma regra.""",
	FINALIDADE_LEITURA: "- O presidente abre o edital e faz a leitura, que indica a ordem dos assuntos do dia.",
	FINALIDADE_ATA_ANTERIOR: """- Informar que a ata foi enviada antes para apreciação.
- Perguntar se alguém tem objeção à aprovação. Sem objeção, aprovada por aclamação.""",
	FINALIDADE_DELEGADOS: """- Informar o número de vagas: 1 delegado para cada fração de 50 associados (o número calculado aparece abaixo). Devem ser eleitos ao menos tantos suplentes quanto vagas.
- Informar onde será a próxima Assembleia Regional.
- Conferir as candidaturas prévias (abaixo). Se forem menos que as vagas, abrir inscrições na hora — o estatuto permite até o momento da eleição.
- Mais candidatos que vagas: votação unitária e secreta, por cédula. Os mais votados são titulares; os demais, suplentes.
- Candidatos em número igual ou menor que as vagas: perguntar se alguém se opõe; sem oposição, todos eleitos por aclamação.
- Sugerir a ordem de suplência por idade, do mais novo para o mais velho. Sem oposição, aprovada por aclamação.""",
	FINALIDADE_COMISSAO_FISCAL: """- São 3 titulares e 3 suplentes, com mandato de 2 anos. O voto é unitário e secreto: cada eleitor vota em um só candidato.
- Os 3 mais votados são titulares; os 3 seguintes, suplentes, na ordem de votação. Depois, os titulares elegem entre si o presidente da comissão.
- Com candidatura única por vaga, pode ser por aclamação.
- Impugnações por escrito são aceitas até o início da votação. Se faltarem candidatos, aceitar inscrições na hora.""",
	FINALIDADE_DIRETORIA: """- A eleição é por chapa (diretor presidente, diretor financeiro e diretor administrativo), com mandato de 2 anos. As chapas inscritas aparecem abaixo.
- Um mesmo candidato não pode estar em duas chapas.
- Chapa única: pode ser por aclamação. Mais de uma: votação secreta.
- Impugnações por escrito são aceitas até o início da votação; impugnado um membro, a chapa pode indicar substituto.
- Responsável sem registro que for eleito deve se registrar até a posse (ou em 30 dias, se a posse for no mesmo dia).
- Não há reeleição por mais de dois mandatos consecutivos na mesma função.""",
	FINALIDADE_ASSUNTOS_GERAIS: """- Os assuntos enviados aparecem abaixo.
- Se não houve nenhum, informar que nenhum assunto foi submetido.
- Se houve, a comissão de assuntos gerais apresenta os assuntos submetidos.""",
	FINALIDADE_ENCERRAMENTO: "- Declarar encerrada a reunião da Assembleia de Grupo, com o dia e o horário exato — eles entram na ata.",
}


def orientacao_da_finalidade(finalidade: str | None) -> str:
	return ORIENTACAO_POR_FINALIDADE.get(finalidade or "", ORIENTACAO_APROVACAO_SIMPLES)


# --------------------------------------------------------------------------------------
# Pautas padrão: (título, tem votação, finalidade)
# --------------------------------------------------------------------------------------

_ITEM_MESA = ("Eleição da mesa diretora: Presidente e Secretário(a)", 1, FINALIDADE_MESA)
_ITEM_LEITURA = ("Leitura do Edital de Convocação", 0, FINALIDADE_LEITURA)
_ITEM_ATA = (
	"Apreciação e deliberação da ata da Assembleia anterior (realizada em {data_assembleia_anterior})",
	1,
	FINALIDADE_ATA_ANTERIOR,
)
_ITEM_ASSUNTOS = ("Assuntos Gerais", 0, FINALIDADE_ASSUNTOS_GERAIS)
_ITEM_ENCERRAMENTO = ("Encerramento", 0, FINALIDADE_ENCERRAMENTO)

PAUTA_ORDINARIA = (
	_ITEM_MESA,
	_ITEM_LEITURA,
	_ITEM_ATA,
	(
		"Apreciação e deliberação do balanço financeiro do exercício de {exercicio} juntamente com parecer da Comissão Fiscal",
		1,
		"",
	),
	("Apreciação e deliberação do relatório da Diretoria da UEL", 1, ""),
	("Apreciação e deliberação do relatório das Seções", 1, ""),
	("Eleição de Delegados para a Assembleia Regional", 1, FINALIDADE_DELEGADOS),
	(
		"Apresentação e eleição dos candidatos à Comissão Fiscal Local - Gestão {gestao}",
		1,
		FINALIDADE_COMISSAO_FISCAL,
	),
	(
		"Apresentação e eleição das chapas para Direção Local - Gestão {gestao}",
		1,
		FINALIDADE_DIRETORIA,
	),
	_ITEM_ASSUNTOS,
	_ITEM_ENCERRAMENTO,
)

PAUTA_EXTRAORDINARIA = (_ITEM_MESA, _ITEM_LEITURA, _ITEM_ATA, _ITEM_ASSUNTOS, _ITEM_ENCERRAMENTO)

# --------------------------------------------------------------------------------------
# Ata
# --------------------------------------------------------------------------------------

MODELO_ATA = """No dia [DIA] de [MÊS] de [ANO], às [HORA INÍCIO], reuniram-se os membros devidamente registrados do {nome_uel} - {numeral}, CNPJ {cnpj}, na sede do Grupo Escoteiro, sito a {endereco_sede} - {cidade}, para deliberar sobre os assuntos apontados na ordem do dia do edital de convocação da reunião [ORDINÁRIA / EXTRAORDINÁRIA] da Assembleia de Grupo, publicado no dia [DATA DO EDITAL]. O quórum presente na reunião é de [QUANTIDADE DE PRESENTES PELA LISTA DE PRESENÇA]. O diretor presidente do Grupo Escoteiro, [NOME DO DIRETOR PRESIDENTE], informou [SE HOUVE OU NÃO CANDIDATURAS PRÉVIAS PARA A MESA] **em atendimento ao item 1 do edital de convocação (Eleição da mesa diretora: Presidente e Secretário(a))**.

[DESCRIÇÃO DE COMO SE DEU A ELEIÇÃO DA MESA]

[PARA CADA ITEM SEGUINTE DA PAUTA, UM PARÁGRAFO QUE COMEÇA COM "**Em atendimento ao item N do edital de convocação (TÍTULO DO ITEM)**", com quem apresentou, os questionamentos relevantes e o resultado da votação — por aclamação, ou com votos a favor, abstenções e votos contrários. Nas eleições: candidatos, forma de votação, eleitos e suplentes, com a ordem de suplência.]

Por fim, o(a) presidente eleito(a) da mesa, [NOME DO PRESIDENTE DA MESA], encerrou a reunião [ordinária / extraordinária] da Assembleia de Grupo às [HORÁRIO DE TÉRMINO POR EXTENSO] e eu, [NOME DO SECRETÁRIO], redigi e assino a presente ata.

_____________________________________
[NOME PRESIDENTE ASSEMBLEIA]

_____________________________________
[NOME SECRETÁRIO ASSEMBLEIA]

_____________________________________
[NOME DIRETOR PRESIDENTE]"""

# --------------------------------------------------------------------------------------
# Lembrete do edital (WhatsApp)
# --------------------------------------------------------------------------------------

ASSINATURA_AUTOMATICA = "🤖 _Esta é uma mensagem automática do GRIS._"

MENSAGEM_LEMBRETE_EDITAL = """📣 *Edital da Assembleia de Grupo*

A reunião {tipo_minusculo} da Assembleia de Grupo está marcada para *{data}*. Pelo estatuto, o edital de convocação precisa ser publicado até *{prazo_edital}*: {faltam}.

Prepare e publique o edital no GRIS: {link}"""
