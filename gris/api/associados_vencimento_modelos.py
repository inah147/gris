# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Modelos editáveis das mensagens da régua de vencimento do registro.

Os textos ficam em ``Configuracoes de Associados`` para o administrativo ajustar sem deploy.
Por isso a troca de variáveis é uma substituição simples sobre um dicionário fechado — nada
de ``str.format`` (que avalia ``{x.__class__}``) nem Jinja (que executaria código vindo de
um campo de formulário). A validação no save recusa variável desconhecida, para o erro
aparecer para quem edita e não num job às 9h.

O rodapé ("já renovado" + "mensagem automática") é anexado aqui, fora dos campos editáveis:
nenhum modelo editado consegue tirar o aviso de que a mensagem é automática.

Textos e variáveis estão documentados em ``docs/specs/regua-vencimento-registro/mensagens.md``.
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import cint

SETTINGS_DOCTYPE = "Configuracoes de Associados"

ASSINATURA_AUTOMATICA = "🤖 _Esta é uma mensagem automática do GRIS._"

TEXTO_JA_RENOVADO_PADRAO = (
	"_Se o registro já foi renovado, pode desconsiderar esta mensagem: a renovação aparece "
	"no GRIS na próxima atualização do Paxtu._"
)

# ``{como_renovar}`` muda com a situação do registro: antes de vencer a própria família renova
# pelo Paxtu; depois de vencido o Paxtu não deixa mais, e é preciso falar com a diretoria.
INSTRUCOES_RENOVACAO_PADRAO = (
	"A renovação é feita direto pelo Paxtu, em *Registro individual*, no menu de navegação."
)
INSTRUCOES_RENOVACAO_VENCIDO_PADRAO = (
	"Como o registro já venceu, a renovação não é mais feita direto pelo Paxtu: "
	"entre em contato com a diretoria do grupo."
)

# Modelos para o associado (ou o responsável, quando menor) ───────────────────

MODELO_30 = "modelo_venc_30"
MODELO_7 = "modelo_venc_7"
MODELO_1 = "modelo_venc_1"
MODELO_0 = "modelo_venc_0"
MODELO_RECORRENTE = "modelo_venc_recorrente"
MODELO_GRUPO_MENSAL = "modelo_venc_grupo_mensal"
MODELO_CHEFE_30 = "modelo_venc_chefe_30"
MODELO_CHEFE_7 = "modelo_venc_chefe_7"
MODELO_CHEFE_POS = "modelo_venc_chefe_pos"

VARIAVEIS_DO_ASSOCIADO = frozenset(
	{
		"primeiro_nome_destinatario",
		"nome_associado",
		"primeiro_nome_associado",
		"registro_de",
		"data_vencimento",
		"dias_restantes",
		"dias_vencido",
		"numero_registro",
		"como_renovar",
		"contato_duvidas",
	}
)
VARIAVEIS_DO_GRUPO = frozenset({"mes", "quantidade", "lista_por_secao"})
VARIAVEIS_DO_CHEFE = frozenset({"primeiro_nome_chefe", "secao", "quantidade", "lista_beneficiarios"})

VARIAVEIS_POR_MODELO: dict[str, frozenset[str]] = {
	MODELO_30: VARIAVEIS_DO_ASSOCIADO,
	MODELO_7: VARIAVEIS_DO_ASSOCIADO,
	MODELO_1: VARIAVEIS_DO_ASSOCIADO,
	MODELO_0: VARIAVEIS_DO_ASSOCIADO,
	MODELO_RECORRENTE: VARIAVEIS_DO_ASSOCIADO,
	MODELO_GRUPO_MENSAL: VARIAVEIS_DO_GRUPO,
	MODELO_CHEFE_30: VARIAVEIS_DO_CHEFE,
	MODELO_CHEFE_7: VARIAVEIS_DO_CHEFE,
	MODELO_CHEFE_POS: VARIAVEIS_DO_CHEFE,
}

MODELOS_PADRAO: dict[str, str] = {
	MODELO_30: (
		"Olá, {primeiro_nome_destinatario}!\n\n"
		"Passando para lembrar que {registro_de} vence em *{data_vencimento}*, "
		"daqui a {dias_restantes} dias.\n\n"
		"Com o registro em dia, a participação nas atividades e o seguro escoteiro continuam "
		"garantidos. {como_renovar}\n\n"
		"{contato_duvidas}"
	),
	MODELO_7: (
		"Olá, {primeiro_nome_destinatario}!\n\n"
		"Falta uma semana: {registro_de} vence em *{data_vencimento}*.\n\n"
		"Para não ficar de fora das atividades, faça a renovação nos próximos dias. {como_renovar}\n\n"
		"{contato_duvidas}"
	),
	MODELO_1: (
		"Olá, {primeiro_nome_destinatario}!\n\n"
		"Amanhã, *{data_vencimento}*, vence {registro_de}. Ainda dá tempo de renovar hoje. "
		"{como_renovar}\n\n"
		"{contato_duvidas}"
	),
	MODELO_0: (
		"Olá, {primeiro_nome_destinatario}!\n\n"
		"Hoje, *{data_vencimento}*, vence {registro_de}. Sem a renovação, a participação nas "
		"atividades fica suspensa. {como_renovar}\n\n"
		"{contato_duvidas}"
	),
	MODELO_RECORRENTE: (
		"Olá, {primeiro_nome_destinatario}!\n\n"
		"Lembrete: {registro_de} está vencido desde *{data_vencimento}* (há {dias_vencido} dias). "
		"Enquanto não for renovado, a participação nas atividades fica suspensa. {como_renovar}\n\n"
		"{contato_duvidas}"
	),
	MODELO_GRUPO_MENSAL: (
		"📋 *Registros de beneficiários que vencem em {mes}*\n\n"
		"{lista_por_secao}\n\n"
		"Total: {quantidade}. As famílias recebem os lembretes automáticos; vale reforçar nas "
		"atividades."
	),
	MODELO_CHEFE_30: (
		"📅 *{secao}: registros que vencem em cerca de 30 dias*\n"
		"{lista_beneficiarios}\n"
		"Vale lembrar as famílias nas próximas atividades."
	),
	MODELO_CHEFE_7: ("⏳ *{secao}: registros que vencem na próxima semana*\n{lista_beneficiarios}"),
	MODELO_CHEFE_POS: (
		"⚠️ *{secao}: registros vencidos*\n"
		"{lista_beneficiarios}\n"
		"Enquanto não regularizarem o registro, esses jovens não podem participar das atividades."
	),
}

# Dados fictícios da pré-visualização: nenhum nome real sai da tela de configuração.
EXEMPLO_POR_GRUPO_DE_VARIAVEIS: dict[frozenset[str], dict[str, str]] = {
	VARIAVEIS_DO_ASSOCIADO: {
		"primeiro_nome_destinatario": "Mariana",
		"nome_associado": "Ana Exemplo",
		"primeiro_nome_associado": "Ana",
		"registro_de": "o registro escoteiro de Ana",
		"data_vencimento": "09/11/2027",
		"dias_restantes": "7",
		"dias_vencido": "3",
		"numero_registro": "1234567-8",
		"contato_duvidas": (
			"Dúvidas sobre a renovação? Fale com a Joana, do administrativo, pelo telefone +55 11 91234-5678."
		),
	},
	VARIAVEIS_DO_GRUPO: {
		"mes": "dezembro de 2026",
		"quantidade": "3",
		"lista_por_secao": (
			"*Alcateia Exemplo* @5511900000001\n• 05/12 — Ana Exemplo\n• 18/12 — Bruno Exemplo\n\n"
			"*Tropa Exemplo* @5511900000002\n• 30/12 — Carla Exemplo"
		),
	},
	VARIAVEIS_DO_CHEFE: {
		"primeiro_nome_chefe": "Rafael",
		"secao": "Alcateia Exemplo",
		"quantidade": "2",
		"lista_beneficiarios": (
			"• Ana Exemplo (Lobinho) — vence em 19/12/2026\n• Bruno Exemplo (Lobinho) — vence em 20/12/2026"
		),
	},
}

# Prazo coerente com cada mensagem na pré-visualização ("30 dias antes" diz "daqui a 30 dias").
_EXEMPLO_DE_PRAZO: dict[str, dict[str, str]] = {
	MODELO_30: {"data_vencimento": "20/12/2026", "dias_restantes": "30", "dias_vencido": "0"},
	MODELO_7: {"data_vencimento": "27/11/2026", "dias_restantes": "7", "dias_vencido": "0"},
	MODELO_1: {"data_vencimento": "21/11/2026", "dias_restantes": "1", "dias_vencido": "0"},
	MODELO_0: {"data_vencimento": "20/11/2026", "dias_restantes": "0", "dias_vencido": "0"},
	MODELO_RECORRENTE: {"data_vencimento": "14/11/2026", "dias_restantes": "0", "dias_vencido": "6"},
}

_VARIAVEL = re.compile(r"\{(\w+)\}")
_CODIGO_DE_TEMPLATE = re.compile(r"\{\{|\}\}|\{%|%\}")
_LINHAS_EM_BRANCO_SOBRANDO = re.compile(r"\n{3,}")

MESES = (
	"janeiro",
	"fevereiro",
	"março",
	"abril",
	"maio",
	"junho",
	"julho",
	"agosto",
	"setembro",
	"outubro",
	"novembro",
	"dezembro",
)


# ─── Substituição ─────────────────────────────────────────────────────────────


def substituir(texto: str, valores: dict[str, object]) -> str:
	"""Troca ``{variavel}`` pelo valor; o que não estiver em ``valores`` fica como está.

	Variável vazia some, e as linhas em branco que ela deixa são compactadas — é o caso do
	``{contato_duvidas}`` sem administrativo configurado.
	"""

	def _trocar(match: re.Match) -> str:
		nome = match.group(1)
		if nome not in valores:
			return match.group(0)
		valor = valores[nome]
		return "" if valor is None else str(valor)

	resultado = _VARIAVEL.sub(_trocar, texto or "")
	resultado = "\n".join(linha.rstrip() for linha in resultado.split("\n"))
	return _LINHAS_EM_BRANCO_SOBRANDO.sub("\n\n", resultado).strip()


def com_rodape(corpo: str, texto_ja_renovado: str | None = None) -> str:
	"""Corpo + aviso de "já renovado" + assinatura fixa de mensagem automática."""
	aviso = (texto_ja_renovado if texto_ja_renovado is not None else _texto_ja_renovado()).strip()
	partes = [corpo.strip()]
	if aviso:
		partes.append(aviso)
	partes.append(ASSINATURA_AUTOMATICA)
	return "\n\n".join(parte for parte in partes if parte)


# ─── Leitura da configuração ──────────────────────────────────────────────────

# Interruptores individuais; a lista existe para o patch que os liga em sites já criados.
CAMPOS_DE_INTERRUPTOR = (
	"msg_venc_30",
	"msg_venc_7",
	"msg_venc_1",
	"msg_venc_0",
	"msg_venc_recorrente",
	"msg_venc_grupo_mensal",
	"msg_venc_chefe_30",
	"msg_venc_chefe_7",
	"msg_venc_chefe_pos",
)


def valor_bruto(fieldname: str):
	"""Valor cru em ``tabSingles`` — ``None`` quando a linha ainda não existe.

	Mesmo motivo de ``recepcao_mensagens._valor_bruto_do_single``: pela via convertida um
	Check ausente vira ``0``, indistinguível de desmarcado.
	"""
	# ``order_by=None``: ``tabSingles`` não tem a coluna ``modified`` da ordenação padrão.
	return frappe.db.get_value(
		"Singles",
		{"doctype": SETTINGS_DOCTYPE, "field": fieldname},
		"value",
		order_by=None,
	)


def interruptor_ligado(fieldname: str) -> bool:
	"""Interruptor individual da régua; ausente conta como ligado."""
	valor = valor_bruto(fieldname)
	return True if valor is None else bool(cint(valor))


def regua_ativa() -> bool:
	"""O geral é a exceção: ausente conta como **desligado** — a régua só liga de propósito."""
	return bool(cint(valor_bruto("regua_vencimento_ativa")))


def _valor_do_single(fieldname: str) -> str:
	return (frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname) or "").strip()


def _texto_ja_renovado() -> str:
	return _valor_do_single("texto_ja_renovado") or TEXTO_JA_RENOVADO_PADRAO


def instrucoes_renovacao(vencido: bool = False) -> str:
	"""Texto de ``{como_renovar}``: Paxtu antes de vencer, diretoria depois."""
	if vencido:
		return _valor_do_single("instrucoes_renovacao_vencido") or INSTRUCOES_RENOVACAO_VENCIDO_PADRAO
	return _valor_do_single("instrucoes_renovacao") or INSTRUCOES_RENOVACAO_PADRAO


def modelo_configurado(campo: str) -> str:
	"""Texto do modelo nas configurações, ou o padrão quando o campo está vazio."""
	if campo not in MODELOS_PADRAO:
		raise KeyError(campo)
	return _valor_do_single(campo) or MODELOS_PADRAO[campo]


def renderizar(campo: str, valores: dict[str, object]) -> str:
	"""Modelo configurado com as variáveis trocadas, ainda sem o rodapé."""
	return substituir(modelo_configurado(campo), valores)


def mes_por_extenso(data) -> str:
	"""``date(2026, 12, 1)`` → "dezembro de 2026"."""
	return f"{MESES[data.month - 1]} de {data.year}"


# ─── Validação (Configuracoes de Associados.validate) ─────────────────────────


def variaveis_desconhecidas(campo: str, texto: str | None) -> list[str]:
	"""Variáveis usadas no texto que o modelo não conhece, na ordem em que aparecem."""
	permitidas = VARIAVEIS_POR_MODELO[campo]
	usadas = _VARIAVEL.findall(texto or "")
	return list(dict.fromkeys(nome for nome in usadas if nome not in permitidas))


def _lista_de_variaveis(campo: str) -> str:
	return ", ".join(f"{{{nome}}}" for nome in sorted(VARIAVEIS_POR_MODELO[campo]))


def validar_configuracoes(doc) -> None:
	"""Recusa no save o que faria a régua falhar ou sair errada às 9h."""
	for campo in MODELOS_PADRAO:
		texto = doc.get(campo) or ""
		rotulo = _(doc.meta.get_label(campo)) if getattr(doc, "meta", None) else campo
		if _CODIGO_DE_TEMPLATE.search(texto):
			frappe.throw(
				_(
					"O modelo “{0}” só aceita variáveis no formato {{variavel}}. "
					"Remova os trechos com {{{{ }}}} ou {{% %}}."
				).format(rotulo),
				title=_("Modelo inválido"),
			)
		desconhecidas = variaveis_desconhecidas(campo, texto)
		if desconhecidas:
			frappe.throw(
				_("O modelo “{0}” usa variável que não existe: {1}. Variáveis aceitas: {2}.").format(
					rotulo,
					", ".join(f"{{{nome}}}" for nome in desconhecidas),
					_lista_de_variaveis(campo),
				),
				title=_("Modelo inválido"),
			)

	if doc.get("regua_vencimento_ativa") and not doc.get("cobrar_vencidos_desde"):
		frappe.throw(
			_(
				"Informe a data em “Cobrar vencidos a partir de” antes de ligar a régua: sem ela, "
				"todo associado ativo já vencido passaria a receber a cobrança recorrente."
			),
			title=_("Data de corte obrigatória"),
		)

	intervalo = doc.get("intervalo_recorrente_dias")
	if intervalo is not None and int(intervalo or 0) < 1:
		frappe.throw(_("O intervalo da cobrança recorrente precisa ser de pelo menos 1 dia."))


# ─── Endpoints da tela de configuração ────────────────────────────────────────


def _assert_campo_de_modelo(campo: str) -> None:
	if campo not in MODELOS_PADRAO:
		frappe.throw(_("Modelo desconhecido: {0}.").format(campo or "vazio"))


@frappe.whitelist()
def pre_visualizar_modelo(campo: str, texto: str | None = None) -> str:
	"""Mensagem como ela sai, com dados fictícios e o rodapé, para quem está editando."""
	frappe.only_for("System Manager")
	_assert_campo_de_modelo(campo)

	texto = texto if (texto or "").strip() else MODELOS_PADRAO[campo]
	desconhecidas = variaveis_desconhecidas(campo, texto)
	if desconhecidas:
		frappe.throw(
			_("Variável que não existe: {0}. Variáveis aceitas: {1}.").format(
				", ".join(f"{{{nome}}}" for nome in desconhecidas), _lista_de_variaveis(campo)
			)
		)

	valores = dict(EXEMPLO_POR_GRUPO_DE_VARIAVEIS[VARIAVEIS_POR_MODELO[campo]])
	valores.update(_EXEMPLO_DE_PRAZO.get(campo, {}))
	if campo == MODELO_CHEFE_POS:
		valores["lista_beneficiarios"] = (
			valores["lista_beneficiarios"]
			.replace("vence em 19/12/2026", "venceu em 19/11/2026")
			.replace("vence em 20/12/2026", "venceu em 18/11/2026")
		)
	valores.setdefault("como_renovar", instrucoes_renovacao(vencido=campo in (MODELO_0, MODELO_RECORRENTE)))
	corpo = substituir(texto, valores)
	if VARIAVEIS_POR_MODELO[campo] is VARIAVEIS_DO_CHEFE:
		corpo = f"Olá, {valores['primeiro_nome_chefe']}!\n\n{corpo}"
	return com_rodape(corpo)


@frappe.whitelist()
def modelo_padrao(campo: str) -> str:
	"""Texto padrão do modelo, para o botão "Restaurar padrão"."""
	frappe.only_for("System Manager")
	_assert_campo_de_modelo(campo)
	return MODELOS_PADRAO[campo]


@frappe.whitelist()
def grupos_para_select() -> dict:
	"""Grupos do WhatsApp para o Select de ``grupo_chefes_whatsapp``, sem modal de erro.

	Com a integração desligada ou a instância fora do ar, a listagem levanta exceção e o Desk
	abre um "Erro de Servidor" toda vez que alguém entra na tela. Aqui o problema volta como
	dado e a tela avisa na descrição do campo. A permissão continua sendo checada em
	``listar_grupos_whatsapp_para_select``.
	"""
	from gris.utils.whatsapp import listar_grupos_whatsapp_para_select
	from gris.utils.whatsapp_errors import WhatsAppConfigurationError, WhatsAppRequestError

	try:
		return {"grupos": listar_grupos_whatsapp_para_select(doctype=SETTINGS_DOCTYPE), "erro": None}
	except (WhatsAppConfigurationError, WhatsAppRequestError) as erro:
		return {"grupos": None, "erro": str(erro)}
