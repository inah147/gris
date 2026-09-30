"""Documentos do grupo que os editais pedem: cartão CNPJ, estatuto, ata, certidões…

A base é o DocType `Transparencia`, e não um cadastro à parte: vários desses documentos
já eram publicados no portal de transparência, e o grupo pediu para editar em um lugar e
ver nos dois. Quem envia e corrige é o Gestor da UEL, na página Documentos da
Administração (`gris.api.administracao.transparencia`); aqui fica só a leitura que a
Captação consulta em /captacao/documentos. O registro mais recente de cada tipo é o
"atual", e os anteriores ficam como histórico.

`Transparencia` tem `make_attachments_public`: todo anexo dela é arquivo público. Por
isso o que se controla aqui é **quem vê o link** de um documento não publicado no
portal de transparência — gestão, Diretoria e Relações Institucionais —, não o acesso
ao arquivo em si.
"""

from __future__ import annotations

from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, getdate

from gris.utils import diretoria

DOCTYPE = "Transparencia"

ROLES_GESTAO_DE_DOCUMENTOS = ("Gestor da UEL", "Editor de Parecer", "System Manager")

RELATORIO_DE_ATIVIDADES = "Relatório de atividades"

#: Tipo → como o documento se comporta. `validade`: vence e precisa de nova emissão;
#: `cartorio`: faz sentido marcar o registro em cartório.
CATALOGO: dict[str, dict] = {
	"Cartão CNPJ": {
		"descricao": "Comprovante de inscrição e de situação cadastral, emitido no site da Receita.",
		"validade": False,
		"cartorio": False,
	},
	"Estatuto": {
		"descricao": "Versão mais recente, registrada em cartório.",
		"validade": False,
		"cartorio": True,
	},
	"Ata de eleição e posse da diretoria": {
		"descricao": "Ata da assembleia que elegeu e deu posse à diretoria atual, registrada em cartório.",
		"validade": False,
		"cartorio": True,
	},
	"Certificado de funcionamento": {
		"descricao": "Emitido pela Região Escoteira.",
		"validade": True,
		"cartorio": False,
	},
	"Certificado de grupo padrão": {
		"descricao": "Reconhecimento de grupo padrão.",
		"validade": True,
		"cartorio": False,
	},
	RELATORIO_DE_ATIVIDADES: {
		"descricao": "Relatório das atividades do ano anterior.",
		"validade": False,
		"cartorio": False,
	},
	"História do grupo": {
		"descricao": "Documento com a história do grupo, sempre atualizado.",
		"validade": False,
		"cartorio": False,
	},
	"Certidão negativa de tributos federais": {
		"descricao": "Certidão conjunta RFB/PGFN. Vale 180 dias.",
		"validade": True,
		"cartorio": False,
	},
	"Certidão negativa de tributos estaduais": {
		"descricao": "Emitida pela Secretaria da Fazenda do estado.",
		"validade": True,
		"cartorio": False,
	},
	"Consulta à regularidade do empregador": {
		"descricao": "Certificado de Regularidade do FGTS (CRF), emitido pela Caixa. Vale 30 dias.",
		"validade": True,
		"cartorio": False,
	},
}

#: Os que o grupo precisa ter sempre prontos para um edital.
DOCUMENTOS_PARA_CAPTACAO = (
	"Ata de eleição e posse da diretoria",
	"Estatuto",
	"Certificado de funcionamento",
	"Cartão CNPJ",
	"Consulta à regularidade do empregador",
	"Certidão negativa de tributos federais",
	"Certidão negativa de tributos estaduais",
	RELATORIO_DE_ATIVIDADES,
	"História do grupo",
)

SITUACAO_AUSENTE = "ausente"
SITUACAO_VENCIDO = "vencido"
SITUACAO_DESATUALIZADO = "desatualizado"
SITUACAO_EM_DIA = "em_dia"


# ---------------------------------------------------------------------------
# Permissões
# ---------------------------------------------------------------------------


def pode_gerenciar_documentos(user: str | None = None) -> bool:
	return bool(set(ROLES_GESTAO_DE_DOCUMENTOS) & set(frappe.get_roles(user or frappe.session.user)))


def pode_ver_nao_publicados(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if pode_gerenciar_documentos(user):
		return True
	papeis = diretoria.papeis_na_diretoria(user)
	return papeis["membro"] or papeis["relacoes_institucionais"]


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def listar_documentos(tipos: tuple[str, ...] | list[str] | None = None) -> list[dict]:
	"""Um item por tipo, na ordem pedida: a versão atual, as anteriores e a situação."""
	tipos = list(tipos or CATALOGO.keys())
	ver_restritos = pode_ver_nao_publicados()

	por_tipo: dict[str, list[dict]] = {tipo: [] for tipo in tipos}
	# `get_all`, não `get_list`: a página é aberta a quem está logado e a regra de
	# quem vê o link fica em `_serializar_versao`.
	for linha in frappe.get_all(
		DOCTYPE,
		filters={"tipo_arquivo": ["in", tipos]},
		fields=[
			"name",
			"tipo_arquivo",
			"arquivo",
			"ano_referencia",
			"data_emissao",
			"data_validade",
			"registrado_em_cartorio",
			"publicado",
			"modified",
		],
		# Mais recente primeiro: o ano do documento e, no mesmo ano, o último enviado.
		# (O `data_de_atualização` do DocType tem acento no nome e o Frappe recusa
		# ordenar por ele.)
		order_by="ano_referencia desc, creation desc",
	):
		por_tipo[linha.tipo_arquivo].append(_serializar_versao(linha, ver_restritos))

	hoje = getdate()
	documentos = []
	for tipo in tipos:
		versoes = por_tipo.get(tipo) or []
		atual = versoes[0] if versoes else None
		situacao, rotulo = situacao_do_documento(tipo, atual, hoje)
		documentos.append(
			{
				"tipo": tipo,
				"descricao": CATALOGO.get(tipo, {}).get("descricao", ""),
				"pede_validade": CATALOGO.get(tipo, {}).get("validade", False),
				"pede_cartorio": CATALOGO.get(tipo, {}).get("cartorio", False),
				"atual": atual,
				"anteriores": versoes[1:],
				"situacao": situacao,
				"situacao_rotulo": rotulo,
			}
		)
	return documentos


def situacao_do_documento(tipo: str, atual: dict | None, hoje: date | None = None) -> tuple[str, str]:
	hoje = hoje or getdate()
	if not atual:
		return SITUACAO_AUSENTE, _("Não enviado")

	validade = atual.get("data_validade")
	if validade and getdate(validade) < hoje:
		return SITUACAO_VENCIDO, _("Vencido")

	# O edital pede o relatório do ano anterior: um de dois anos atrás já não serve.
	if tipo == RELATORIO_DE_ATIVIDADES and cint(atual.get("ano_referencia")) < hoje.year - 1:
		return SITUACAO_DESATUALIZADO, _("Desatualizado")

	if validade:
		dias = (getdate(validade) - hoje).days
		if dias <= 30:
			return SITUACAO_EM_DIA, _("Vence em {0} dia(s)").format(dias)
	return SITUACAO_EM_DIA, _("Em dia")


def _serializar_versao(linha, ver_restritos: bool) -> dict:
	publicado = bool(linha.publicado)
	return {
		"name": linha.name,
		"ano_referencia": linha.ano_referencia,
		"data_emissao": str(linha.data_emissao) if linha.data_emissao else None,
		"data_validade": str(linha.data_validade) if linha.data_validade else None,
		"registrado_em_cartorio": bool(linha.registrado_em_cartorio),
		"publicado": publicado,
		"atualizado_em": str(linha.modified) if linha.modified else None,
		"arquivo": linha.arquivo if (publicado or ver_restritos) else None,
	}
