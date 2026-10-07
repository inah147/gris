"""Nomes compartilhados pelo portal de acessos."""

ROLE_GESTOR = "Gestor de Acessos"
ROLE_SYSTEM_MANAGER = "System Manager"

ACESSO_DOCTYPE = "Acesso"
SOLICITACAO_DOCTYPE = "Solicitacao de Acesso"
LICENCA_DOCTYPE = "Licenca de Ferramenta"
SETTINGS_DOCTYPE = "Configuracoes de Acessos"
SECAO_DOCTYPE = "Acesso por Secao"

TIPO_PAPEL = "Papel do Gris"
TIPO_DRIVE = "Drive compartilhado"
TIPO_FERRAMENTA = "Ferramenta externa"

# As duas abas do portal. O papel vai para "Gris"; drive e ferramenta, para "Ferramentas".
ABA_GRIS = "gris"
ABA_FERRAMENTAS = "ferramentas"
ABA_POR_TIPO = {
	TIPO_PAPEL: ABA_GRIS,
	TIPO_DRIVE: ABA_FERRAMENTAS,
	TIPO_FERRAMENTA: ABA_FERRAMENTAS,
}

STATUS_EM_APROVACAO = "Em aprovação"
STATUS_AGUARDANDO_CONCESSAO = "Aguardando concessão"
STATUS_CONCEDIDA = "Concedida"
STATUS_RECUSADA = "Recusada"
STATUS_CANCELADA = "Cancelada"

# Solicitação "aberta" = ainda pode virar acesso. É a que bloqueia um segundo pedido.
STATUS_ABERTOS = (STATUS_EM_APROVACAO, STATUS_AGUARDANDO_CONCESSAO)

DECISAO_PENDENTE = "Pendente"
DECISAO_APROVADA = "Aprovada"
DECISAO_RECUSADA = "Recusada"

LICENCA_ATIVA = "Ativa"
LICENCA_REVOGACAO_PENDENTE = "Revogação pendente"
LICENCA_REVOGADA = "Revogada"

# Uma licença ocupa a vaga até a revogação ser confirmada: enquanto a conta existe na
# ferramenta, ela conta no limite contratado.
LICENCAS_QUE_OCUPAM_VAGA = (LICENCA_ATIVA, LICENCA_REVOGACAO_PENDENTE)

MOTIVO_INATIVACAO = "Inativação"
MOTIVO_GESTOR = "Gestor"
MOTIVO_OUTRO = "Outro"

# Papéis que nunca passam pelo portal: são do Frappe ou dariam a chave do próprio portal
# a quem aprova a si mesmo. "Gestor de Acessos" fica de fora da ação em massa e só é
# concedido com a decisão de um System Manager (ver `solicitacao_de_acesso.py`).
PAPEIS_PROTEGIDOS = frozenset({"Administrator", "System Manager", "Guest", "All", "Desk User"})

# Ação em massa com mais usuários do que isto vai para a fila longa.
LIMITE_MASSA_SINCRONA = 50
