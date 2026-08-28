"""Apuração da contribuição mensal a partir das transações do extrato geral.

A fonte de verdade desta apuração é o DocType `Transacao Extrato Geral`: toda
transação de crédito com `categoria = "Contribuição Mensal"` e `beneficiario`
preenchido conta como contribuição recebida do associado no mês de competência.

O DocType `Pagamento Contribuicao Mensal` continua existindo para o fluxo de
cobrança (schedulers e gráficos do dashboard), mas **não** participa do cálculo
feito aqui — o dinheiro que entrou é o que manda.
"""

from __future__ import annotations

import datetime

import frappe
from frappe import _
from frappe.utils import add_months, getdate

from gris.api.portal_access import user_has_access

# Categoria da transação que representa a contribuição mensal.
CATEGORIA_CONTRIBUICAO = "Contribuição Mensal"

# Categorias de associado que contribuem. Dirigente não paga contribuição e,
# por não estar nesta tupla, jamais entra na apuração nem nos totais.
CATEGORIAS_CONTRIBUINTES = ("Beneficiário", "Escotista")

# Data de competência da contribuição: a data da transação é a informação mais
# confiável do extrato; depósito e timestamp entram só como fallback.
SQL_DATA_COMPETENCIA = "COALESCE(data_transacao, DATE(data_deposito), DATE(timestamp_transacao))"

# Janela padrão de apuração, em meses (inclui o mês corrente).
MESES_PADRAO = 12
MESES_MAXIMO = 36

STATUS_PAGO = "Pago"
STATUS_PARCIAL = "Parcial"
STATUS_EM_ABERTO = "Em Aberto"
STATUS_ATRASADO = "Atrasado"
STATUS_AGUARDANDO = "Aguardando"
STATUS_NAO_APLICAVEL = "Não aplicável"

# Sufixo de classe CSS por situação, usado pelo template e pelo JS da página.
SLUG_SITUACAO = {
	STATUS_PAGO: "pago",
	STATUS_PARCIAL: "parcial",
	STATUS_EM_ABERTO: "aberto",
	STATUS_ATRASADO: "atrasado",
	STATUS_AGUARDANDO: "aguardando",
	STATUS_NAO_APLICAVEL: "na",
}

# Ordem de severidade usada para resumir a situação do associado no período.
ORDEM_SITUACAO = [
	STATUS_ATRASADO,
	STATUS_PARCIAL,
	STATUS_EM_ABERTO,
	STATUS_PAGO,
	STATUS_AGUARDANDO,
	STATUS_NAO_APLICAVEL,
]

FERIADOS_FIXOS = {
	"01-01",  # Confraternização Universal
	"21-04",  # Tiradentes
	"01-05",  # Dia do Trabalho
	"07-09",  # Independência
	"12-10",  # Nossa Senhora Aparecida
	"02-11",  # Finados
	"15-11",  # Proclamação da República
	"25-12",  # Natal
}


def _e_feriado(data: datetime.date) -> bool:
	return data.strftime("%d-%m") in FERIADOS_FIXOS


def normalizar_meses(meses) -> int:
	"""Valida a janela de apuração pedida pelo usuário."""
	try:
		valor = int(meses)
	except (TypeError, ValueError):
		return MESES_PADRAO
	return max(1, min(valor, MESES_MAXIMO))


def construir_meses(meses: int = MESES_PADRAO, hoje: datetime.date | None = None) -> list[datetime.date]:
	"""Lista de primeiros dias de mês, do mais antigo ao mês corrente."""
	hoje = hoje or getdate()
	primeiro_do_mes_atual = getdate(f"{hoje.year}-{hoje.month:02d}-01")
	inicio = add_months(primeiro_do_mes_atual, -(meses - 1))
	sequencia = []
	cursor = getdate(inicio)
	for _mes in range(meses):
		sequencia.append(cursor)
		cursor = getdate(add_months(cursor, 1))
	return sequencia


def chave_mes(data: datetime.date) -> str:
	return data.strftime("%Y-%m")


def rotulo_mes(data: datetime.date) -> str:
	return data.strftime("%m/%Y")


def get_dia_vencimento() -> int:
	"""Dia de vencimento configurado, limitado à janela segura do mês."""
	try:
		config = frappe.get_single("Configuracoes Contribuicao Mensal")
		dia = int(getattr(config, "dia_vencimento", 10) or 10)
	except Exception:
		dia = 10
	if dia < 1 or dia > 28:
		dia = 10
	return dia


def get_valor_base() -> float:
	"""Valor base da contribuição, usado quando o associado não tem valor próprio."""
	try:
		config = frappe.get_single("Configuracoes Contribuicao Mensal")
		return float(getattr(config, "valor_base", 0) or 0)
	except Exception:
		return 0.0


def calcular_vencimento(mes: datetime.date, dia_vencimento: int) -> datetime.date:
	"""Vencimento do mês, adiado para o próximo dia útil quando cai em fim de semana/feriado."""
	vencimento = datetime.date(mes.year, mes.month, dia_vencimento)
	while vencimento.weekday() >= 5 or _e_feriado(vencimento):
		vencimento += datetime.timedelta(days=1)
	return vencimento


def get_contribuintes() -> list[dict]:
	"""Associados que devem contribuir.

	Inclui os ativos das categorias contribuintes e também os inativos que ainda
	estão com cobrança ativa — são justamente os que precisam ser cancelados e
	sumiriam da tela se filtrássemos só por ativos.
	"""
	campos = [
		"name",
		"nome_completo",
		"categoria",
		"secao",
		"inicio_do_pagamento",
		"valor_contribuicao",
		"status_no_grupo",
		"status_cobranca",
		"email_cobranca",
		"telefone_cobranca",
	]
	ativos = frappe.get_all(
		"Associado",
		filters={
			"status_no_grupo": "Ativo",
			"categoria": ["in", list(CATEGORIAS_CONTRIBUINTES)],
		},
		fields=campos,
		order_by="nome_completo asc",
		limit_page_length=0,
	)
	inativos_em_cobranca = frappe.get_all(
		"Associado",
		filters={
			"status_no_grupo": "Inativo",
			"status_cobranca": "Ativo",
			"categoria": ["in", list(CATEGORIAS_CONTRIBUINTES)],
		},
		fields=campos,
		order_by="nome_completo asc",
		limit_page_length=0,
	)

	vistos = set()
	contribuintes = []
	for associado in ativos + inativos_em_cobranca:
		if associado["name"] in vistos:
			continue
		vistos.add(associado["name"])
		contribuintes.append(dict(associado))
	return contribuintes


def get_recebimentos_por_associado(
	primeiro_dia: datetime.date, proximo_mes: datetime.date
) -> dict[str, dict[str, dict]]:
	"""Soma as contribuições recebidas por associado e mês de competência.

	Retorna `{associado: {"YYYY-MM": {"valor": float, "qtd": int}}}`.
	"""
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	linhas = frappe.db.sql(
		f"""
		SELECT beneficiario,
		       DATE_FORMAT({SQL_DATA_COMPETENCIA}, '%%Y-%%m') AS ym,
		       SUM(ABS(valor)) AS valor,
		       COUNT(name) AS qtd
		FROM `tabTransacao Extrato Geral`
		WHERE categoria = %(categoria)s
		  AND debito_credito = 'Crédito'
		  AND COALESCE(excluir_do_total, 0) = 0
		  AND COALESCE(beneficiario, '') != ''
		  AND {SQL_DATA_COMPETENCIA} >= %(primeiro_dia)s
		  AND {SQL_DATA_COMPETENCIA} < %(proximo_mes)s
		GROUP BY beneficiario, ym
		""",
		{
			"categoria": CATEGORIA_CONTRIBUICAO,
			"primeiro_dia": primeiro_dia,
			"proximo_mes": proximo_mes,
		},
		as_dict=True,
	)

	recebimentos: dict[str, dict[str, dict]] = {}
	for linha in linhas:
		por_mes = recebimentos.setdefault(linha.beneficiario, {})
		por_mes[linha.ym] = {
			"valor": float(linha.valor or 0),
			"qtd": int(linha.qtd or 0),
		}
	return recebimentos


def get_transacoes_do_associado(
	associado: str, primeiro_dia: datetime.date, proximo_mes: datetime.date
) -> list[dict]:
	"""Transações de contribuição de um associado no período, da mais recente para a mais antiga."""
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	linhas = frappe.db.sql(
		f"""
		SELECT name,
		       {SQL_DATA_COMPETENCIA} AS data_competencia,
		       DATE_FORMAT({SQL_DATA_COMPETENCIA}, '%%Y-%%m') AS ym,
		       ABS(valor) AS valor,
		       descricao,
		       metodo,
		       carteira
		FROM `tabTransacao Extrato Geral`
		WHERE categoria = %(categoria)s
		  AND debito_credito = 'Crédito'
		  AND COALESCE(excluir_do_total, 0) = 0
		  AND beneficiario = %(associado)s
		  AND {SQL_DATA_COMPETENCIA} >= %(primeiro_dia)s
		  AND {SQL_DATA_COMPETENCIA} < %(proximo_mes)s
		ORDER BY data_competencia DESC
		""",
		{
			"categoria": CATEGORIA_CONTRIBUICAO,
			"associado": associado,
			"primeiro_dia": primeiro_dia,
			"proximo_mes": proximo_mes,
		},
		as_dict=True,
	)
	return [
		{
			"name": linha.name,
			"data": linha.data_competencia.isoformat() if linha.data_competencia else None,
			"ym": linha.ym,
			"valor": float(linha.valor or 0),
			"descricao": linha.descricao or "",
			"metodo": linha.metodo or "",
			"carteira": linha.carteira or "",
		}
		for linha in linhas
	]


def get_transacoes_nao_vinculadas(primeiro_dia: datetime.date, proximo_mes: datetime.date) -> list[dict]:
	"""Contribuições recebidas que ainda não foram atribuídas a um associado.

	Elas entram no total geral recebido (o dinheiro caiu na conta), mas não podem
	ser apuradas por associado enquanto alguém não preencher o beneficiário no
	detalhe do extrato.
	"""
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	linhas = frappe.db.sql(
		f"""
		SELECT name,
		       {SQL_DATA_COMPETENCIA} AS data_competencia,
		       ABS(valor) AS valor,
		       descricao,
		       metodo,
		       carteira
		FROM `tabTransacao Extrato Geral`
		WHERE categoria = %(categoria)s
		  AND debito_credito = 'Crédito'
		  AND COALESCE(excluir_do_total, 0) = 0
		  AND COALESCE(beneficiario, '') = ''
		  AND {SQL_DATA_COMPETENCIA} >= %(primeiro_dia)s
		  AND {SQL_DATA_COMPETENCIA} < %(proximo_mes)s
		ORDER BY data_competencia DESC
		""",
		{
			"categoria": CATEGORIA_CONTRIBUICAO,
			"primeiro_dia": primeiro_dia,
			"proximo_mes": proximo_mes,
		},
		as_dict=True,
	)
	return [
		{
			"name": linha.name,
			"data": linha.data_competencia.isoformat() if linha.data_competencia else None,
			"valor": float(linha.valor or 0),
			"descricao": linha.descricao or "",
			"metodo": linha.metodo or "",
			"carteira": linha.carteira or "",
		}
		for linha in linhas
	]


def _acao_de_cadastro(contribuinte: dict, hoje: datetime.date) -> str | None:
	"""Pendência de cadastro da cobrança, independente do que as transações mostram.

	- "Cancelar": saiu do grupo mas a cobrança continua ativa.
	- "Cadastrar": está ativo, começa a pagar em até 30 dias e a cobrança ainda não foi criada.
	"""
	status_grupo = contribuinte.get("status_no_grupo")
	status_cobranca = contribuinte.get("status_cobranca")

	if status_grupo == "Inativo" and status_cobranca == "Ativo":
		return "Cancelar"

	if status_grupo == "Ativo" and status_cobranca != "Ativo":
		inicio = contribuinte.get("inicio_do_pagamento")
		if not inicio:
			return "Cadastrar"
		inicio = getdate(inicio)
		if hoje >= inicio - datetime.timedelta(days=30):
			return "Cadastrar"

	return None


def montar_grade(
	contribuinte: dict,
	meses: list[datetime.date],
	recebido_por_mes: dict[str, dict],
	hoje: datetime.date,
	vencimentos: dict[str, datetime.date],
	valor_base: float = 0.0,
) -> dict:
	"""Apura mês a mês a situação de um associado a partir do que ele pagou.

	Um mês é considerado quitado quando o recebido (somado ao crédito que sobrou
	dos meses anteriores) alcança o valor esperado. Quem paga a mais acumula
	crédito, que abate os meses seguintes.
	"""
	esperado_mensal = float(contribuinte.get("valor_contribuicao") or 0) or float(valor_base or 0)
	inicio_raw = contribuinte.get("inicio_do_pagamento")
	inicio = getdate(inicio_raw) if inicio_raw else None
	inicio_mes = datetime.date(inicio.year, inicio.month, 1) if inicio else None
	mes_atual = datetime.date(hoje.year, hoje.month, 1)

	linhas = []
	credito = 0.0
	total_recebido = 0.0
	total_esperado = 0.0
	meses_devidos = 0
	meses_quitados = 0

	for mes in meses:
		ym = chave_mes(mes)
		dados = recebido_por_mes.get(ym) or {}
		recebido = float(dados.get("valor") or 0)
		qtd = int(dados.get("qtd") or 0)
		total_recebido += recebido

		antes_do_inicio = inicio_mes is not None and mes < inicio_mes
		comeca_no_futuro = inicio is not None and mes == inicio_mes and inicio > hoje

		if antes_do_inicio or comeca_no_futuro:
			# Fora da vigência da cobrança: o que porventura entrou vira crédito.
			credito += recebido
			linhas.append(
				{
					"ym": ym,
					"rotulo": rotulo_mes(mes),
					"esperado": 0.0,
					"recebido": recebido,
					"qtd_transacoes": qtd,
					"status": STATUS_AGUARDANDO if comeca_no_futuro else STATUS_NAO_APLICAVEL,
					"status_slug": SLUG_SITUACAO[
						STATUS_AGUARDANDO if comeca_no_futuro else STATUS_NAO_APLICAVEL
					],
					"usou_credito": False,
				}
			)
			continue

		esperado = esperado_mensal
		total_esperado += esperado
		disponivel = recebido + credito
		usou_credito = False

		if esperado <= 0:
			status = STATUS_PAGO if recebido > 0 else STATUS_NAO_APLICAVEL
			credito = disponivel
		elif disponivel >= esperado:
			status = STATUS_PAGO
			usou_credito = recebido < esperado
			credito = disponivel - esperado
		elif disponivel > 0:
			status = STATUS_PARCIAL
			usou_credito = credito > 0
			credito = 0.0
		else:
			vencido = mes < mes_atual or hoje > vencimentos[ym]
			status = STATUS_ATRASADO if vencido else STATUS_EM_ABERTO
			credito = 0.0

		if esperado > 0:
			meses_devidos += 1
			if status == STATUS_PAGO:
				meses_quitados += 1

		linhas.append(
			{
				"ym": ym,
				"rotulo": rotulo_mes(mes),
				"esperado": esperado,
				"recebido": recebido,
				"qtd_transacoes": qtd,
				"status": status,
				"status_slug": SLUG_SITUACAO[status],
				"usou_credito": usou_credito,
			}
		)

	situacao = STATUS_NAO_APLICAVEL
	status_presentes = {linha["status"] for linha in linhas}
	for candidato in ORDEM_SITUACAO:
		if candidato in status_presentes:
			situacao = candidato
			break

	return {
		"linhas": linhas,
		"situacao": situacao,
		"situacao_slug": SLUG_SITUACAO[situacao],
		"total_recebido": total_recebido,
		"total_esperado": total_esperado,
		"saldo": total_recebido - total_esperado,
		"credito": credito,
		"meses_devidos": meses_devidos,
		"meses_quitados": meses_quitados,
		"esperado_mensal": esperado_mensal,
	}


def apurar(
	meses=MESES_PADRAO,
	hoje: datetime.date | None = None,
	incluir_dados_cobranca: bool = False,
) -> dict:
	"""Apuração completa do período: por associado, totais e transações a identificar.

	`incluir_dados_cobranca` acrescenta e-mail e telefone de cobrança ao resultado —
	dados de contato que só gestores da contribuição mensal podem ver.
	"""
	quantidade_meses = normalizar_meses(meses)
	hoje = hoje or getdate()
	sequencia = construir_meses(quantidade_meses, hoje)
	primeiro_dia = sequencia[0]
	proximo_mes = getdate(add_months(sequencia[-1], 1))

	dia_vencimento = get_dia_vencimento()
	vencimentos = {chave_mes(mes): calcular_vencimento(mes, dia_vencimento) for mes in sequencia}
	valor_base = get_valor_base()

	contribuintes = get_contribuintes()
	recebimentos = get_recebimentos_por_associado(primeiro_dia, proximo_mes)
	nao_vinculadas = get_transacoes_nao_vinculadas(primeiro_dia, proximo_mes)

	chaves = [chave_mes(mes) for mes in sequencia]
	recebido_mes = dict.fromkeys(chaves, 0.0)
	esperado_mes = dict.fromkeys(chaves, 0.0)
	devidos_mes = dict.fromkeys(chaves, 0)
	quitados_mes = dict.fromkeys(chaves, 0)

	associados = []
	for contribuinte in contribuintes:
		grade = montar_grade(
			contribuinte,
			sequencia,
			recebimentos.get(contribuinte["name"], {}),
			hoje,
			vencimentos,
			valor_base,
		)
		for linha in grade["linhas"]:
			ym = linha["ym"]
			recebido_mes[ym] += linha["recebido"]
			esperado_mes[ym] += linha["esperado"]
			if linha["esperado"] > 0:
				devidos_mes[ym] += 1
				if linha["status"] == STATUS_PAGO:
					quitados_mes[ym] += 1

		inicio = contribuinte.get("inicio_do_pagamento")
		dados_cobranca = (
			{
				"email_cobranca": contribuinte.get("email_cobranca"),
				"telefone_cobranca": contribuinte.get("telefone_cobranca"),
			}
			if incluir_dados_cobranca
			else {}
		)
		associados.append(
			{
				"id": contribuinte["name"],
				"nome": contribuinte.get("nome_completo") or contribuinte["name"],
				"categoria": contribuinte.get("categoria"),
				"secao": contribuinte.get("secao"),
				"status_no_grupo": contribuinte.get("status_no_grupo"),
				"status_cobranca": contribuinte.get("status_cobranca"),
				"inicio_do_pagamento": getdate(inicio).isoformat() if inicio else None,
				"acao_cadastro": _acao_de_cadastro(contribuinte, hoje),
				**dados_cobranca,
				**grade,
			}
		)

	nao_vinculado_mes = dict.fromkeys(chaves, 0.0)
	for transacao in nao_vinculadas:
		ym = (transacao.get("data") or "")[:7]
		if ym in nao_vinculado_mes:
			nao_vinculado_mes[ym] += transacao["valor"]

	total_vinculado = sum(recebido_mes.values())
	total_nao_vinculado = sum(nao_vinculado_mes.values())
	total_esperado = sum(esperado_mes.values())
	total_devidos = sum(devidos_mes.values())
	total_quitados = sum(quitados_mes.values())

	com_pendencia = [a for a in associados if a["situacao"] in (STATUS_ATRASADO, STATUS_PARCIAL)]

	return {
		"meses": [{"ym": chave_mes(mes), "rotulo": rotulo_mes(mes)} for mes in sequencia],
		"quantidade_meses": quantidade_meses,
		"periodo": {"inicio": primeiro_dia.isoformat(), "fim": sequencia[-1].isoformat()},
		"dia_vencimento": dia_vencimento,
		"associados": associados,
		"nao_vinculadas": nao_vinculadas,
		"series": {
			"labels": [rotulo_mes(mes) for mes in sequencia],
			"recebido": [round(recebido_mes[ym], 2) for ym in chaves],
			"nao_vinculado": [round(nao_vinculado_mes[ym], 2) for ym in chaves],
			"esperado": [round(esperado_mes[ym], 2) for ym in chaves],
			"adimplencia": [
				round((quitados_mes[ym] / devidos_mes[ym]) * 100, 2) if devidos_mes[ym] else 0.0
				for ym in chaves
			],
		},
		"totais": {
			"contribuintes": len(associados),
			"recebido_vinculado": round(total_vinculado, 2),
			"recebido_nao_vinculado": round(total_nao_vinculado, 2),
			"recebido_total": round(total_vinculado + total_nao_vinculado, 2),
			"esperado": round(total_esperado, 2),
			"saldo": round(total_vinculado - total_esperado, 2),
			"meses_devidos": total_devidos,
			"meses_quitados": total_quitados,
			"adimplencia": round((total_quitados / total_devidos) * 100, 2) if total_devidos else 0.0,
			"com_pendencia": len(com_pendencia),
			"a_cadastrar": len([a for a in associados if a["acao_cadastro"] == "Cadastrar"]),
			"a_cancelar": len([a for a in associados if a["acao_cadastro"] == "Cancelar"]),
			"transacoes_nao_vinculadas": len(nao_vinculadas),
		},
	}


# Role que pode ver e editar dados de cobrança na página de contribuições.
ROLE_GESTOR = "Gestor Contribuição Mensal"

# Rota do portal cujas roles governam esta apuração.
ROTA_CONTRIBUICOES = "/financeiro/contribuicoes"


def _assert_acesso_leitura() -> None:
	"""Vale o mesmo controle da página do portal.

	Checar permissão nos DocTypes não serviria aqui: `Transacao Extrato Geral` só
	concede leitura a System Manager, e a página é estrita — nem System Manager
	entra sem uma das roles de contribuição.
	"""
	if frappe.session.user == "Guest" or not user_has_access(ROTA_CONTRIBUICOES):
		frappe.throw(
			_("Sem permissão para consultar a apuração de contribuições mensais."),
			frappe.PermissionError,
		)


@frappe.whitelist()
def get_apuracao(meses: str | int = MESES_PADRAO):
	"""Apuração completa do período, para consumo do portal."""
	_assert_acesso_leitura()
	pode_ver_cobranca = ROLE_GESTOR in frappe.get_roles()
	return {"success": True, "dados": apurar(meses, incluir_dados_cobranca=pode_ver_cobranca)}


@frappe.whitelist()
def get_extrato_do_associado(associado: str, meses: str | int = MESES_PADRAO):
	"""Transações de contribuição de um associado no período apurado."""
	_assert_acesso_leitura()
	if not associado:
		frappe.throw(_("Parâmetro 'associado' é obrigatório."), frappe.ValidationError)

	quantidade_meses = normalizar_meses(meses)
	sequencia = construir_meses(quantidade_meses)
	transacoes = get_transacoes_do_associado(associado, sequencia[0], getdate(add_months(sequencia[-1], 1)))
	return {"success": True, "transacoes": transacoes}
