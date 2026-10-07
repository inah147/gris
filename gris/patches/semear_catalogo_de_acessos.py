"""Semeia o catálogo do portal de acessos.

Só insere: cada item é procurado pelo papel, pelo drive ou pelo título, e um item que já
existe nunca é sobrescrito — descrições, limites e etapas passam a ser da gestão de
acessos. Só as contribuições trazem etapas próprias (diretoria financeira); os demais
ficam com a etapa padrão que o controller grava, aprovada pelo Gestor de Acessos, que a
gestão pode trocar depois.

Ficam de fora o papel "Responsavel" (é do portal das famílias, não de associados) e os
papéis citados no código que nunca foram criados.
"""

import frappe

from gris.api.acessos.constantes import ACESSO_DOCTYPE, TIPO_DRIVE, TIPO_FERRAMENTA, TIPO_PAPEL
from gris.install import garantir_role_gestor_de_acessos

# Contribuições são aprovadas pela diretoria financeira. A marcação "por seção" e "só para
# associados" vem em `ajustar_acessos_de_contribuicoes`, que roda logo depois.
ETAPAS_CONTRIBUICAO = [("Gestor Contribuição Mensal", "Diretoria financeira")]

PAPEIS = [
	# (papel, título no portal, ícone, ordem, solicitável, descrição, o que muda, etapas)
	(
		"Visualizador Associados",
		"Consulta de associados",
		"users",
		10,
		1,
		"Consulta ao cadastro de associados do grupo.",
		"Libera /associados: painel, lista e a ficha de cada associado e responsável, só para leitura.",
		None,
	),
	(
		"Gestor de Associados",
		"Gestão de associados",
		"user-check",
		11,
		1,
		"Gestão do cadastro de associados.",
		"Libera /associados por completo, inclusive a importação do Paxtu. Cria e edita associados, responsáveis e vínculos, e recebe por WhatsApp o aviso de registros vencidos.",
		None,
	),
	(
		"Visualizador Financeiro",
		"Consulta financeira",
		"wallet",
		20,
		1,
		"Consulta às finanças do grupo.",
		"Libera /financeiro: painel, contas, extrato, despesas, previsão orçamentária, relatórios e pareceres, só para leitura.",
		None,
	),
	(
		"Gestor Financeiro",
		"Gestão financeira",
		"landmark",
		21,
		1,
		"Gestão das finanças do grupo.",
		"Libera todo /financeiro, exceto as contribuições: conciliação de extratos, contas fixas, orçamento e o extrato com a descrição completa. Cadastra carteiras, categorias e centros de custo.",
		None,
	),
	(
		"Editor de Parecer",
		"Pareceres da Comissão Fiscal",
		"scale",
		22,
		1,
		"Pareceres da Comissão Fiscal sobre as contas do grupo.",
		"Libera /financeiro/pareceres para registrar pareceres e mostra os documentos da transparência que ainda não foram publicados.",
		None,
	),
	(
		"Visualizador Contribuição Mensal",
		"Consulta de contribuições",
		"coins",
		30,
		1,
		"Consulta às contribuições mensais de todas as seções do grupo.",
		"Libera /financeiro/contribuicoes com todas as seções, para ver quem está em dia, em aberto ou em atraso, sem cobrar.",
		ETAPAS_CONTRIBUICAO,
	),
	(
		"Visualizador Contribuição Mensal da Seção",
		"Contribuições da seção",
		"coins",
		31,
		1,
		"Consulta às contribuições mensais dos beneficiários de uma seção.",
		"Você escolhe a seção ao pedir e passa a ver em /financeiro/contribuicoes só os beneficiários dela, sem cobrar. Para ver outra seção, faça outro pedido. Quem é chefe de seção já vê a própria seção pelo perfil.",
		ETAPAS_CONTRIBUICAO,
	),
	(
		"Gestor Contribuição Mensal",
		"Gestão de contribuições",
		"hand-coins",
		32,
		1,
		"Gestão das contribuições mensais.",
		"Libera /financeiro/contribuicoes por completo: gera as mensalidades, envia cobranças e links de pagamento e registra os pagamentos.",
		ETAPAS_CONTRIBUICAO,
	),
	(
		"Visualizador Calendario",
		"Consulta do calendário",
		"calendar",
		40,
		1,
		"Consulta ao calendário do grupo.",
		"Libera /calendario para ver os eventos do grupo.",
		None,
	),
	(
		"Gestor Calendario",
		"Gestão do calendário",
		"calendar-days",
		41,
		1,
		"Gestão do calendário do grupo pelo portal.",
		"Libera /calendario por completo: cria, edita e exclui eventos, importa o calendário e usa a simulação.",
		None,
	),
	(
		"Editor Calendario",
		"Edição do calendário (Desk)",
		"calendar-days",
		42,
		1,
		"Edição do calendário pela área administrativa.",
		"Cria, edita e exclui eventos do calendário e do calendário simulado no Desk. Precisa também de Acesso ao Desk.",
		None,
	),
	(
		"Visualizador de projetos",
		"Consulta de projetos",
		"folder-kanban",
		50,
		1,
		"Consulta aos projetos do grupo.",
		"Libera /projetos: visão geral, meus projetos, a página de cada projeto e a aprovação, só para leitura.",
		None,
	),
	(
		"Editor de projetos",
		"Edição de projetos",
		"folder-kanban",
		51,
		1,
		"Cadastro e edição de projetos.",
		"Libera todo /projetos, inclusive cadastrar projeto novo. Edita projetos, avaliações e as tarefas dos quadros de que você participa.",
		None,
	),
	(
		"Visualizador de festas",
		"Consulta de festas",
		"party-popper",
		60,
		1,
		"Consulta às festas do grupo.",
		"Libera /festas, a lista de festas, a página de cada festa e o relatório, só para leitura.",
		None,
	),
	(
		"Gestor de festas",
		"Gestão de festas",
		"party-popper",
		61,
		1,
		"Organização das festas do grupo.",
		"Libera todo /festas: cria festas e cuida de áreas, barracas, compras, contratações, convites, portaria e avaliação.",
		None,
	),
	(
		"Portaria",
		"Portaria das festas",
		"ticket",
		62,
		1,
		"Operação da portaria nas festas.",
		"Libera /festas/portaria para conferir convites e a lista de entrada de todas as festas.",
		None,
	),
	(
		"Gestor de Metodos",
		"Gestão de Métodos Educativos",
		"lightbulb",
		70,
		1,
		"Diretoria de Métodos Educativos.",
		"Edita o calendário e gerencia as compras do Programa Educativo em /compras/fila. Recebe por WhatsApp o aviso de mudanças no calendário.",
		None,
	),
	(
		"Equipe de Metodos",
		"Equipe de Métodos Educativos",
		"lightbulb",
		71,
		1,
		"Equipe de Métodos Educativos.",
		"Edita o calendário e abre solicitações de compra. Recebe por WhatsApp o aviso de mudanças no calendário.",
		None,
	),
	(
		"Gestor de Manutencao",
		"Compras da Manutenção",
		"wrench",
		72,
		1,
		"Compras da área de Manutenção.",
		"Gerencia a fila de compras da Manutenção em /compras/fila e o catálogo de itens.",
		None,
	),
	(
		"Gestor Administrativo",
		"Compras do Administrativo",
		"shopping-cart",
		73,
		1,
		"Compras da área Administrativa.",
		"Gerencia a fila de compras do Administrativo em /compras/fila e o catálogo de itens.",
		None,
	),
	(
		"Recepcao",
		"Recepção de novos associados",
		"user-plus",
		80,
		1,
		"Recepção de novos associados.",
		"Libera /recepcao: funil de novos associados, visitas, fila de espera, ficha de registro e mensagens. Permite preencher o registro no lugar da família.",
		None,
	),
	(
		"Gestor de Adultos",
		"Gestão de adultos",
		"briefcase",
		90,
		1,
		"Gestão de adultos voluntários.",
		"Libera /gestao_adultos: acordos de trabalho voluntário, entrevistas por competências e as respostas. Edita as funções internas dos associados.",
		None,
	),
	(
		"Gestor da UEL",
		"Gestão da UEL",
		"building-2",
		91,
		1,
		"Gestão da estrutura da UEL.",
		"Edita unidades organizacionais e funções em /administracao, cuida da transparência e das configurações de captação.",
		None,
	),
	(
		"Acompanhamento de Sugestoes",
		"Acompanhamento de sugestões",
		"message-square",
		100,
		0,
		"Acompanhamento do quadro de sugestões e problemas do Gris.",
		"Libera /sugestoes para ver e comentar os cards. Todo associado já recebe junto com o usuário.",
		None,
	),
	(
		"Desenvolvedor",
		"Desenvolvimento do Gris",
		"code",
		101,
		1,
		"Equipe que desenvolve o Gris.",
		"Permite triar e mover os cards de /sugestoes/acompanhamento, ser responsável por uma sugestão e participar do quadro de tarefas Desenvolvimento do GRIS.",
		None,
	),
	(
		"Acesso ao Desk",
		"Acesso ao Desk",
		"monitor",
		110,
		1,
		"Entrada na área administrativa nativa do Frappe (/app).",
		"Libera abrir /app, onde ficam cadastros e configurações sem tela no portal, e criar usuários de associados. O que se vê lá dentro continua dependendo dos outros papéis.",
		None,
	),
	(
		"Gestor de Acessos",
		"Gestão de acessos",
		"shield-check",
		120,
		1,
		"Administração deste portal de acessos.",
		"Libera /acessos/gestao: aprova qualquer solicitação, confirma a criação de contas nas ferramentas, controla as licenças e concede ou revoga papéis em massa.",
		None,
	),
]

FERRAMENTAS = [
	{
		"titulo": "Canva",
		"icone": "palette",
		"ordem": 10,
		"limite_licencas": 50,
		"link_externo": "https://www.canva.com",
		"descricao": "Canva Pro no time do GEPIM: modelos, kit da marca do grupo e pastas compartilhadas.",
		"o_que_muda": "Você é convidado para o time do GEPIM no Canva com o seu id@escoteiros. O grupo tem 50 licenças, e a sua fica reservada enquanto você estiver ativo.",
		"instrucoes_concessao": "No Canva, abra Pessoas > Convidar pessoas e convide o id@escoteiros da solicitação. Depois confirme a concessão aqui.",
	},
	{
		"titulo": "Microsoft 365",
		"icone": "app-window",
		"ordem": 20,
		"limite_licencas": 300,
		"link_externo": "https://www.office.com",
		"descricao": "Word, Excel, PowerPoint, OneDrive e Teams na web, pelo programa da Microsoft para organizações sem fins lucrativos.",
		"o_que_muda": "A equipe cria a sua conta Microsoft com o seu id@escoteiros. O grupo tem 300 licenças, e a sua fica reservada enquanto você estiver ativo.",
		"instrucoes_concessao": "No centro de administração do Microsoft 365, crie o usuário com o id@escoteiros da solicitação e atribua a licença. Depois confirme a concessão aqui.",
	},
]

# Drives conhecidos pela especificação; casados pelo nome configurado no Workspace.
DRIVES = [
	(
		"restrito",
		{
			"icone": "folder-lock",
			"ordem": 31,
			"solicitavel": 1,
			"permissao_drive": "writer",
			"descricao": "Documentos de acesso restrito da diretoria.",
			"o_que_muda": "Para a diretoria eleita e pessoas selecionadas. A concessão expira depois do prazo configurado e pode ser pedida de novo.",
		},
	),
	(
		"site",
		{
			"icone": "globe",
			"ordem": 32,
			"solicitavel": 1,
			"permissao_drive": "writer",
			"descricao": "Arquivos da administração do site do grupo, feito no Google Sites.",
			"o_que_muda": "Para quem vai editar o site do grupo.",
		},
	),
	(
		"backup",
		{
			"icone": "archive",
			"ordem": 33,
			"solicitavel": 0,
			"permissao_drive": "reader",
			"descricao": "Uso do sistema: guarda os backups automáticos do Gris.",
			"o_que_muda": "Somente administradores do sistema têm acesso.",
		},
	),
	(
		"datalake",
		{
			"icone": "database",
			"ordem": 34,
			"solicitavel": 0,
			"permissao_drive": "reader",
			"descricao": "Legado: dados do sistema usado antes do Gris.",
			"o_que_muda": "Somente administradores do sistema têm acesso.",
		},
	),
]

DRIVE_GLOBAL = {
	"icone": "hard-drive",
	"ordem": 30,
	"solicitavel": 0,
	"permissao_drive": "reader",
	"descricao": "Drive geral do GEPIM, com os documentos de uso comum do grupo.",
	"o_que_muda": "Concedido automaticamente a todo associado ativo com id@escoteiros: jovens como leitores e voluntários como administradores de conteúdo.",
}


def _inserir(dados: dict, etapas=None) -> None:
	doc = frappe.get_doc({"doctype": ACESSO_DOCTYPE, "ativo": 1, **dados})
	for papel, descricao in etapas or []:
		doc.append("etapas_aprovacao", {"papel_aprovador": papel, "descricao": descricao})
	doc.insert(ignore_permissions=True)


def _semear_papeis() -> None:
	existentes = set(frappe.get_all(ACESSO_DOCTYPE, filters={"tipo": TIPO_PAPEL}, pluck="papel"))
	titulos = set(frappe.get_all(ACESSO_DOCTYPE, pluck="name"))
	for papel, titulo, icone, ordem, solicitavel, descricao, o_que_muda, etapas in PAPEIS:
		if papel in existentes or titulo in titulos or not frappe.db.exists("Role", papel):
			continue
		_inserir(
			{
				"titulo": titulo,
				"tipo": TIPO_PAPEL,
				"papel": papel,
				"icone": icone,
				"ordem": ordem,
				"solicitavel": solicitavel,
				"descricao": descricao,
				"o_que_muda": o_que_muda,
			},
			etapas,
		)


def _semear_ferramentas() -> None:
	for ferramenta in FERRAMENTAS:
		if frappe.db.exists(ACESSO_DOCTYPE, ferramenta["titulo"]):
			continue
		_inserir({"tipo": TIPO_FERRAMENTA, "solicitavel": 1, **ferramenta})


def _semear_drives() -> None:
	from gris.api.acessos.drives import drives_configurados

	existentes = set(frappe.get_all(ACESSO_DOCTYPE, filters={"tipo": TIPO_DRIVE}, pluck="drive_id"))
	titulos = set(frappe.get_all(ACESSO_DOCTYPE, pluck="name"))
	for drive in drives_configurados():
		if drive.drive_id in existentes or drive.nome_drive in titulos:
			continue
		if drive.conceder_a_todos:
			dados = dict(DRIVE_GLOBAL)
		else:
			nome = (drive.nome_drive or "").casefold()
			dados = next((dict(d) for chave, d in DRIVES if chave in nome), None) or {
				"icone": "hard-drive",
				"ordem": 39,
				"solicitavel": 0,
				"permissao_drive": "reader",
				"descricao": f"Drive compartilhado {drive.nome_drive}.",
				"o_que_muda": "A gestão de acessos decide quem recebe este drive.",
			}
		_inserir({"titulo": drive.nome_drive, "tipo": TIPO_DRIVE, "drive_id": drive.drive_id, **dados})


def execute():
	garantir_role_gestor_de_acessos()
	_semear_papeis()
	_semear_ferramentas()
	_semear_drives()
