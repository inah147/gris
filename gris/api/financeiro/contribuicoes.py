"""Apuração da contribuição mensal a partir das transações do extrato geral.

A fonte de verdade desta apuração é o DocType `Transacao Extrato Geral`: toda
transação de crédito com `categoria = "Contribuição Mensal"` e `beneficiario`
preenchido conta como contribuição recebida do associado no mês de competência.

O DocType `Pagamento Contribuicao Mensal` continua existindo para o fluxo de
cobrança (os schedulers que geram e atualizam os registros), mas **não**
participa do cálculo feito aqui — o dinheiro que entrou é o que manda. Desde a
migração do painel financeiro, nenhum gráfico lê mais aquele DocType: tudo passa
por esta apuração.

Três regras de negócio governam o cálculo, todas parametrizáveis em
`Configuracoes Contribuicao Mensal`:

1. **Valor do mês.** A contribuição custa o valor base (R$ 60) enquanto está
   dentro do prazo e passa a custar o valor de atraso (R$ 70) quando o mês vence
   sem ter sido quitado. Quem tem valor próprio no cadastro paga o mesmo
   acréscimo, não o valor de atraso fixo. O acréscimo é o que se **cobra**: o mês
   é dado por quitado assim que a cobertura alcança o valor em dia, porque pagar
   os 60 em atraso é comum e fecha o mês.
2. **Carência de registro.** O associado não deve contribuição nos primeiros
   meses depois do ingresso: quem entra como provisório paga o registro
   provisório no 1º mês, o definitivo mais o uniforme no 2º e só contribui a
   partir do 3º; quem entra como definitivo paga o registro no 1º mês e
   contribui a partir do 2º. `inicio_do_pagamento` no cadastro do associado
   continua mandando quando está preenchido.
3. **Quitação retroativa.** Pagamento da InfinitePay em múltiplo de mensalidade
   quita os meses anteriores em aberto, do mais antigo para o mais novo, antes de
   sobrar como crédito para os meses seguintes.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import add_months, getdate

from gris.api.portal_access import user_has_access

# Categoria da transação que representa a contribuição mensal.
CATEGORIA_CONTRIBUICAO = "Contribuição Mensal"

# Categorias de associado que contribuem. Só Beneficiário paga contribuição
# mensal — Dirigente e Escotista não estão nesta tupla e jamais entram na
# apuração nem nos totais.
CATEGORIAS_CONTRIBUINTES = ("Beneficiário",)

# Data de competência da contribuição. `mes_competencia` vem primeiro porque é o
# único campo que diz explicitamente a qual mês a contribuição se refere — é ele
# que separa a data em que o dinheiro entrou do mês que está sendo quitado, no
# pagamento em atraso e no adiantamento. Sem ele, a data da transação é a
# informação mais confiável do extrato; depósito e timestamp entram só como fallback.
SQL_DATA_COMPETENCIA = (
	"COALESCE(mes_competencia, data_transacao, DATE(data_deposito), DATE(timestamp_transacao))"
)

# Data em que o dinheiro efetivamente entrou. Diferente da competência: é ela que
# diz se o mês foi quitado dentro do prazo (contribuição normal) ou depois dele
# (contribuição em atraso, que custa mais).
SQL_DATA_PAGAMENTO = "COALESCE(data_transacao, DATE(data_deposito), DATE(timestamp_transacao))"

# Carteiras/instituições cujos pagamentos quitam meses anteriores antes de virar
# crédito para os próximos. Na InfinitePay o responsável paga o link de cobrança
# com o valor cheio da dívida, então um pagamento de 180 é "três meses atrasados",
# nunca "este mês e mais dois adiantados".
CARTEIRAS_RETROATIVAS = ("infinitepay",)

# Tolerância de centavos nas comparações de dinheiro.
TOLERANCIA = 0.005

# Diferença máxima, em reais, que ainda conta como "centavo quebrado" de tarifa
# bancária/PIX. Contribuição é sempre em real cheio (R$ 60, R$ 70…); um Pix que
# chega como R$ 59,97 ou R$ 140,02 é o mesmo pagamento de sempre com um resíduo
# de tarifa — arredondar para o real cheio evita que esse resíduo vire "falta"
# ou crédito fracionado que nunca fecha no batimento seguinte.
TOLERANCIA_ARREDONDAMENTO_CENTAVOS = 0.05


def arredondar_centavos_quebrados(valor: float) -> float:
	"""Arredonda para o real cheio quando a diferença é só resíduo de tarifa."""
	valor = float(valor or 0)
	mais_proximo = round(valor)
	if abs(valor - mais_proximo) <= TOLERANCIA_ARREDONDAMENTO_CENTAVOS:
		return float(mais_proximo)
	return round(valor, 2)


# Carência padrão, em meses cheios contados do ingresso, antes da primeira
# contribuição mensal:
#
# - Provisório: 1º mês paga o registro provisório, 2º o registro definitivo mais
#   o uniforme e só no 3º começa a contribuição mensal (carência de 2 meses).
# - Definitivo: 1º mês paga o registro definitivo e no 2º começa a contribuição
#   mensal (carência de 1 mês).
#
# Ambas são parametrizáveis em `Configuracoes Contribuicao Mensal`.
CARENCIA_PROVISORIO = 2
CARENCIA_DEFINITIVO = 1

# O que se paga em cada mês de carência, na ordem em que eles acontecem.
MOTIVOS_CARENCIA_PROVISORIO = ("Registro provisório", "Registro definitivo + uniforme")
MOTIVOS_CARENCIA_DEFINITIVO = ("Registro definitivo",)
MOTIVO_CARENCIA_GENERICO = "Carência de registro"

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

# Situações de um mês que já venceu sem ter sido quitado. Atrasado é sempre
# vencido por construção; Parcial só entra quando o prazo passou — quem pagou
# parte do mês corrente antes do vencimento ainda não é inadimplente.
SITUACOES_INADIMPLENTES = (STATUS_ATRASADO, STATUS_PARCIAL)

# Situações que um mês devido pode assumir, na ordem em que empilham no gráfico.
SITUACOES_DO_MES_DEVIDO = (STATUS_PAGO, STATUS_PARCIAL, STATUS_EM_ABERTO, STATUS_ATRASADO)

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


@dataclass(frozen=True)
class ParametrosContribuicao:
	"""Regras parametrizáveis da contribuição mensal.

	Tudo o que muda de valor com o tempo (quanto custa o mês, quanto custa o mês
	em atraso, quando vence e quanta carência o novato tem) mora aqui, para que a
	apuração continue sendo uma função pura de dados de entrada.
	"""

	valor_base: float = 0.0
	valor_atraso: float = 0.0
	dia_vencimento: int = 10
	carencia_provisorio: int = CARENCIA_PROVISORIO
	carencia_definitivo: int = CARENCIA_DEFINITIVO

	@property
	def acrescimo_atraso(self) -> float:
		"""Quanto o mês encarece quando vence sem quitação."""
		return max(0.0, round(float(self.valor_atraso) - float(self.valor_base), 2))

	def valor_em_atraso(self, esperado_mensal: float) -> float:
		"""Valor do mês vencido sem quitação.

		Quem tem valor próprio no cadastro paga o mesmo acréscimo de quem paga o
		valor base — é o acréscimo que a configuração define, não um valor fixo.
		"""
		return round(float(esperado_mensal) + self.acrescimo_atraso, 2)

	def unidades_de_pagamento(self) -> tuple[float, ...]:
		"""Valores de um mês avulso, do maior para o menor.

		É contra eles que se testa se um pagamento da InfinitePay é múltiplo de
		mensalidades: o responsável tanto paga 70 pelo mês atrasado quanto 60 pelo
		mês em dia, e as duas coisas são pagamento de mês.
		"""
		valores = {round(float(self.valor_base), 2), round(float(self.valor_atraso), 2)}
		return tuple(sorted((valor for valor in valores if valor > 0), reverse=True))


def get_parametros() -> ParametrosContribuicao:
	"""Lê as configurações da contribuição mensal numa única consulta."""
	valor_base = 0.0
	valor_atraso = 0.0
	dia = 10
	carencia_provisorio = CARENCIA_PROVISORIO
	carencia_definitivo = CARENCIA_DEFINITIVO
	try:
		config = frappe.get_single("Configuracoes Contribuicao Mensal")
		valor_base = float(getattr(config, "valor_base", 0) or 0)
		valor_atraso = float(getattr(config, "valor_atraso", 0) or 0)
		dia = int(getattr(config, "dia_vencimento", 10) or 10)
		carencia_provisorio = int(
			getattr(config, "meses_carencia_provisorio", CARENCIA_PROVISORIO) or CARENCIA_PROVISORIO
		)
		carencia_definitivo = int(
			getattr(config, "meses_carencia_definitivo", CARENCIA_DEFINITIVO) or CARENCIA_DEFINITIVO
		)
	except Exception:
		pass
	if dia < 1 or dia > 28:
		dia = 10
	# Sem valor de atraso configurado, o mês atrasado custa o mesmo do mês em dia.
	if valor_atraso < valor_base:
		valor_atraso = valor_base
	return ParametrosContribuicao(
		valor_base=valor_base,
		valor_atraso=valor_atraso,
		dia_vencimento=dia,
		carencia_provisorio=max(0, carencia_provisorio),
		carencia_definitivo=max(0, carencia_definitivo),
	)


def get_dia_vencimento() -> int:
	"""Dia de vencimento configurado, limitado à janela segura do mês."""
	return get_parametros().dia_vencimento


def get_valor_base() -> float:
	"""Valor base da contribuição, usado quando o associado não tem valor próprio."""
	return get_parametros().valor_base


def get_valor_atraso() -> float:
	"""Valor da contribuição depois do vencimento."""
	return get_parametros().valor_atraso


def calcular_vencimento(mes: datetime.date, dia_vencimento: int) -> datetime.date:
	"""Vencimento do mês, adiado para o próximo dia útil quando cai em fim de semana/feriado."""
	vencimento = datetime.date(mes.year, mes.month, dia_vencimento)
	while vencimento.weekday() >= 5 or _e_feriado(vencimento):
		vencimento += datetime.timedelta(days=1)
	return vencimento


CAMPOS_CONTRIBUINTE = (
	"name",
	"nome_completo",
	"categoria",
	"secao",
	"tipo_registro",
	"inicio_do_pagamento",
	"valor_contribuicao",
	"status_no_grupo",
	"status_cobranca",
	"email_cobranca",
	"telefone_cobranca",
)


def get_datas_de_ingresso(nomes: list[str]) -> dict[str, datetime.date]:
	"""Data de ingresso vigente de cada associado, numa consulta só.

	É dela que sai a carência de registro de quem ainda não tem
	`inicio_do_pagamento` preenchido. Entre vários históricos, vale o ingresso
	mais recente ainda sem desligamento; se todos estiverem encerrados, vale o
	mais recente deles.
	"""
	if not nomes:
		return {}

	linhas = frappe.get_all(
		"Historico no Grupo",
		filters={
			"parenttype": "Associado",
			"parent": ["in", list(nomes)],
			"data_de_ingresso": ["is", "set"],
		},
		fields=["parent", "data_de_ingresso", "data_de_desligamento"],
		limit_page_length=0,
	)

	melhores: dict[str, tuple[int, datetime.date]] = {}
	for linha in linhas:
		data = getdate(linha["data_de_ingresso"])
		# Um período ainda aberto vence qualquer período já encerrado; entre iguais,
		# vence o ingresso mais recente.
		candidato = (0 if linha.get("data_de_desligamento") else 1, data)
		atual = melhores.get(linha["parent"])
		if atual is None or candidato > atual:
			melhores[linha["parent"]] = candidato
	return {nome: candidato[1] for nome, candidato in melhores.items()}


def _com_datas_de_ingresso(contribuintes: list[dict]) -> list[dict]:
	"""Anexa a data de ingresso a cada contribuinte (usada na carência)."""
	ingressos = get_datas_de_ingresso([c["name"] for c in contribuintes])
	for contribuinte in contribuintes:
		contribuinte["data_de_ingresso"] = ingressos.get(contribuinte["name"])
	return contribuintes


def primeiro_dia_do_mes(data: datetime.date) -> datetime.date:
	return datetime.date(data.year, data.month, 1)


def _e_provisorio(tipo_registro) -> bool:
	return (tipo_registro or "").strip().lower().startswith("provis")


def meses_de_carencia(tipo_registro, parametros: ParametrosContribuicao) -> int:
	"""Meses entre o ingresso e a primeira contribuição mensal."""
	if _e_provisorio(tipo_registro):
		return max(0, int(parametros.carencia_provisorio))
	return max(0, int(parametros.carencia_definitivo))


def resolver_inicio_do_pagamento(
	contribuinte: dict, parametros: ParametrosContribuicao | None = None
) -> datetime.date | None:
	"""Primeiro mês em que o associado deve a contribuição mensal.

	O cadastro manda quando `inicio_do_pagamento` está preenchido. Sem ele, a data
	sai do ingresso mais a carência do tipo de registro — é o que evita cobrar
	contribuição de quem ainda está pagando registro e uniforme.
	"""
	parametros = parametros or ParametrosContribuicao()
	inicio = contribuinte.get("inicio_do_pagamento")
	if inicio:
		return getdate(inicio)

	ingresso = contribuinte.get("data_de_ingresso")
	if not ingresso:
		return None

	carencia = meses_de_carencia(contribuinte.get("tipo_registro"), parametros)
	return getdate(add_months(primeiro_dia_do_mes(getdate(ingresso)), carencia))


def motivos_de_carencia(
	contribuinte: dict,
	parametros: ParametrosContribuicao,
	inicio: datetime.date | None,
) -> dict[str, str]:
	"""O que o associado paga em cada mês antes da primeira contribuição.

	Serve para a tela não mostrar um "não aplicável" mudo nos primeiros meses: o
	mês tem, sim, uma cobrança — registro provisório, registro definitivo, uniforme
	—, só não é a contribuição mensal.
	"""
	ingresso = contribuinte.get("data_de_ingresso")
	if not ingresso:
		return {}

	carencia = meses_de_carencia(contribuinte.get("tipo_registro"), parametros)
	if carencia <= 0:
		return {}

	rotulos = (
		MOTIVOS_CARENCIA_PROVISORIO
		if _e_provisorio(contribuinte.get("tipo_registro"))
		else MOTIVOS_CARENCIA_DEFINITIVO
	)
	ingresso_mes = primeiro_dia_do_mes(getdate(ingresso))

	motivos: dict[str, str] = {}
	for indice in range(carencia):
		mes = getdate(add_months(ingresso_mes, indice))
		# Início manual anterior ao fim da carência: quem manda é o cadastro, e o
		# mês já cobrado não recebe rótulo de carência.
		if inicio is not None and mes >= primeiro_dia_do_mes(inicio):
			break
		motivos[chave_mes(mes)] = rotulos[indice] if indice < len(rotulos) else MOTIVO_CARENCIA_GENERICO
	return motivos


def get_contribuintes() -> list[dict]:
	"""Associados que devem contribuir.

	Inclui os ativos das categorias contribuintes e também os inativos que ainda
	estão com cobrança ativa — são justamente os que precisam ser cancelados e
	sumiriam da tela se filtrássemos só por ativos.
	"""
	campos = list(CAMPOS_CONTRIBUINTE)
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
	primeiro_dia: datetime.date,
	proximo_mes: datetime.date,
	associados: list[str] | None = None,
) -> dict[str, dict[str, dict]]:
	"""Soma as contribuições recebidas por associado e mês de competência.

	`associados` restringe a consulta a um conjunto conhecido de associados — é o
	caminho usado pelas telas que apuram poucas pessoas (o responsável vendo os
	filhos, a cobrança de um contribuinte) em vez do grupo inteiro.

	Retorna `{associado: {"YYYY-MM": {"valor": float, "qtd": int, "transacoes": [...]}}}`.
	Cada transação carrega a data em que o dinheiro entrou e se ela veio de uma
	carteira de quitação retroativa — as duas informações que a apuração precisa
	para saber se o mês foi pago dentro do prazo e se o excedente quita meses
	anteriores em vez de adiantar os próximos.
	"""
	params: dict = {
		"categoria": CATEGORIA_CONTRIBUICAO,
		"primeiro_dia": primeiro_dia,
		"proximo_mes": proximo_mes,
	}
	filtro_associados = ""
	if associados is not None:
		if not associados:
			return {}
		filtro_associados = "AND beneficiario IN %(associados)s"
		params["associados"] = tuple(associados)

	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	linhas = frappe.db.sql(
		f"""
		SELECT beneficiario,
		       DATE_FORMAT({SQL_DATA_COMPETENCIA}, '%%Y-%%m') AS ym,
		       ABS(valor) AS valor,
		       {SQL_DATA_PAGAMENTO} AS data_pagamento,
		       carteira,
		       instituicao
		FROM `tabTransacao Extrato Geral`
		WHERE categoria = %(categoria)s
		  AND debito_credito = 'Crédito'
		  AND COALESCE(excluir_do_total, 0) = 0
		  AND COALESCE(beneficiario, '') != ''
		  AND {SQL_DATA_COMPETENCIA} >= %(primeiro_dia)s
		  AND {SQL_DATA_COMPETENCIA} < %(proximo_mes)s
		  {filtro_associados}
		ORDER BY beneficiario, ym, data_pagamento
		""",
		params,
		as_dict=True,
	)

	recebimentos: dict[str, dict[str, dict]] = {}
	for linha in linhas:
		por_mes = recebimentos.setdefault(linha.beneficiario, {})
		mes = por_mes.setdefault(linha.ym, {"valor": 0.0, "qtd": 0, "transacoes": []})
		valor = arredondar_centavos_quebrados(linha.valor)
		mes["valor"] += valor
		mes["qtd"] += 1
		mes["transacoes"].append(
			{
				"valor": valor,
				"data": getdate(linha.data_pagamento) if linha.data_pagamento else None,
				"retroativa": e_carteira_retroativa(linha.carteira, linha.instituicao),
			}
		)
	for por_mes in recebimentos.values():
		for mes in por_mes.values():
			mes["valor"] = round(mes["valor"], 2)
	return recebimentos


def e_carteira_retroativa(carteira, instituicao) -> bool:
	"""A transação veio de uma carteira cujo pagamento quita meses anteriores?"""
	alvo = f"{carteira or ''} {instituicao or ''}".lower()
	return any(nome in alvo for nome in CARTEIRAS_RETROATIVAS)


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
			"valor": arredondar_centavos_quebrados(linha.valor),
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
			"valor": arredondar_centavos_quebrados(linha.valor),
			"descricao": linha.descricao or "",
			"metodo": linha.metodo or "",
			"carteira": linha.carteira or "",
		}
		for linha in linhas
	]


def _acao_de_cadastro(
	contribuinte: dict, hoje: datetime.date, inicio: datetime.date | None = None
) -> str | None:
	"""Pendência de cadastro da cobrança, independente do que as transações mostram.

	- "Cancelar": saiu do grupo mas a cobrança continua ativa.
	- "Cadastrar": está ativo, começa a pagar em até 30 dias e a cobrança ainda não foi criada.
	"""
	status_grupo = contribuinte.get("status_no_grupo")
	status_cobranca = contribuinte.get("status_cobranca")

	if status_grupo == "Inativo" and status_cobranca == "Ativo":
		return "Cancelar"

	if status_grupo == "Ativo" and status_cobranca != "Ativo":
		# Sem início no cadastro, vale o mês que a carência de registro calcula.
		if inicio is None:
			inicio = resolver_inicio_do_pagamento(contribuinte)
		if not inicio:
			return "Cadastrar"
		inicio = getdate(inicio)
		if hoje >= inicio - datetime.timedelta(days=30):
			return "Cadastrar"

	return None


def _e_multiplo(valor: float, unidades: tuple[float, ...]) -> bool:
	"""O pagamento fecha um número inteiro de mensalidades?"""
	for unidade in unidades:
		if unidade <= 0:
			continue
		multiplo = valor / unidade
		if multiplo < 1:
			continue
		if abs(multiplo - round(multiplo)) * unidade <= 0.01:
			return True
	return False


def _valor_retroativo(transacoes: list[dict], unidades: tuple[float, ...]) -> float:
	"""Quanto do mês veio em pagamentos que quitam meses anteriores.

	Só entram as transações de carteira retroativa cujo valor é múltiplo de uma
	mensalidade — tanto do valor em dia quanto do valor em atraso, porque o
	responsável às vezes paga o mês atrasado pelo valor cheio e às vezes pelo
	valor normal.
	"""
	total = 0.0
	for transacao in transacoes:
		if not transacao.get("retroativa"):
			continue
		valor = float(transacao.get("valor") or 0)
		if valor > 0 and _e_multiplo(valor, unidades):
			total += valor
	return round(total, 2)


def _recebido_ate(transacoes: list[dict], limite: datetime.date) -> float:
	"""Quanto do mês entrou até a data limite (transação sem data conta como em dia)."""
	total = 0.0
	for transacao in transacoes:
		data = transacao.get("data")
		if data is None or getdate(data) <= limite:
			total += float(transacao.get("valor") or 0)
	return round(total, 2)


def _ultima_data(transacoes: list[dict]) -> datetime.date | None:
	datas = [getdate(transacao["data"]) for transacao in transacoes if transacao.get("data")]
	return max(datas) if datas else None


def _maior_data(atual: datetime.date | None, nova: datetime.date | None) -> datetime.date | None:
	if atual is None:
		return nova
	if nova is None:
		return atual
	return max(atual, nova)


def _quitar_meses_anteriores(linhas: list[dict], valor: float) -> float:
	"""Aplica o pagamento aos meses anteriores em aberto, do mais antigo ao mais novo.

	Três passadas, nesta ordem, porque quitar mais um mês vale mais do que pagar o
	acréscimo de atraso de outro:

	1. quita cada mês pelo mínimo (o valor em dia), enquanto sobrar dinheiro para um
	   mês inteiro — é o que faz um pagamento de 180 fechar três meses atrasados;
	2. completa o acréscimo de atraso dos meses já quitados — é o que faz um
	   pagamento de 210 fechar os mesmos três meses pelo valor cheio, em vez de
	   deixar um quarto mês pela metade;
	3. o que ainda sobrar cobre parcialmente os meses mais antigos que restarem.

	Devolve o que sobrou depois disso — é esse resto que fica disponível para o mês
	da própria transação e, só então, para os próximos.
	"""
	restante = round(float(valor or 0), 2)
	if restante <= TOLERANCIA:
		return 0.0

	devidos = [linha for linha in linhas if linha["esperado"] > 0]

	def aplicar(linha: dict, quanto: float) -> None:
		nonlocal restante
		if quanto <= TOLERANCIA:
			return
		linha["coberto"] = round(linha["coberto"] + quanto, 2)
		linha["quitacao_retroativa"] = True
		restante = round(restante - quanto, 2)

	# 1) quitação: mês por mês, só quando dá para fechar um mês inteiro.
	for linha in devidos:
		falta_minimo = round(linha["minimo"] - linha["coberto"], 2)
		if falta_minimo <= TOLERANCIA:
			continue
		if falta_minimo > restante + TOLERANCIA:
			break
		aplicar(linha, falta_minimo)
		if restante <= TOLERANCIA:
			return 0.0

	# 2) acréscimo de atraso dos meses que a passada anterior já fechou.
	for linha in devidos:
		if linha["coberto"] + TOLERANCIA < linha["minimo"]:
			continue
		falta = round(linha["esperado"] - linha["coberto"], 2)
		if falta <= TOLERANCIA:
			continue
		aplicar(linha, min(falta, restante))
		if restante <= TOLERANCIA:
			return 0.0

	# 3) o resto abate o que puder, do mês mais antigo em diante.
	for linha in devidos:
		falta = round(linha["esperado"] - linha["coberto"], 2)
		if falta <= TOLERANCIA:
			continue
		aplicar(linha, min(falta, restante))
		if restante <= TOLERANCIA:
			return 0.0

	return max(0.0, restante)


def _status_do_mes(linha: dict) -> str:
	"""Situação do mês a partir do que já foi coberto.

	O que quita é o mínimo (o valor em dia), não o valor cobrado: quem paga 60
	depois do vencimento fecha o mês, ainda que a cobrança fosse de 70.
	"""
	if linha["coberto"] + TOLERANCIA >= linha["minimo"]:
		return STATUS_PAGO
	if linha["coberto"] > TOLERANCIA:
		return STATUS_PARCIAL
	return STATUS_ATRASADO if linha["vencido"] else STATUS_EM_ABERTO


def montar_grade(
	contribuinte: dict,
	meses: list[datetime.date],
	recebido_por_mes: dict[str, dict],
	hoje: datetime.date,
	vencimentos: dict[str, datetime.date],
	valor_base: float = 0.0,
	parametros: ParametrosContribuicao | None = None,
) -> dict:
	"""Apura mês a mês a situação de um associado a partir do que ele pagou.

	Três regras governam a apuração:

	1. **Valor do mês.** Vale o valor do cadastro do associado ou, na falta dele, o
	   valor base configurado. O mês que vence sem dinheiro suficiente passa a valer
	   o valor de atraso — o acréscimo é o mesmo para quem tem valor próprio —, mas
	   quita com o valor em dia: `esperado` é o que se cobra e `minimo` é o que
	   fecha o mês.
	2. **Carência de registro.** Os primeiros meses depois do ingresso não têm
	   contribuição mensal: quem entra como provisório paga o registro provisório,
	   depois o definitivo mais o uniforme, e só então começa a contribuir; quem
	   entra como definitivo paga o registro e contribui a partir do mês seguinte.
	3. **Quitação retroativa.** Pagamento de carteira retroativa (InfinitePay) em
	   múltiplo de mensalidade quita primeiro os meses anteriores em aberto; só o
	   que sobra depois disso fica no mês da transação e, aí sim, vira crédito para
	   os meses seguintes.
	"""
	parametros = parametros or ParametrosContribuicao(valor_base=valor_base, valor_atraso=valor_base)
	esperado_mensal = float(contribuinte.get("valor_contribuicao") or 0) or float(parametros.valor_base or 0)
	inicio = resolver_inicio_do_pagamento(contribuinte, parametros)
	inicio_mes = primeiro_dia_do_mes(inicio) if inicio else None
	mes_atual = primeiro_dia_do_mes(hoje)
	unidades = parametros.unidades_de_pagamento()
	motivos = motivos_de_carencia(contribuinte, parametros, inicio)

	linhas: list[dict] = []
	credito = 0.0
	# Data do dinheiro que virou crédito: é ela que diz se o crédito já estava
	# disponível antes do vencimento do mês que ele vai quitar.
	credito_data: datetime.date | None = None
	total_recebido = 0.0

	for mes in meses:
		ym = chave_mes(mes)
		dados = recebido_por_mes.get(ym) or {}
		recebido = float(dados.get("valor") or 0)
		qtd = int(dados.get("qtd") or 0)
		transacoes = dados.get("transacoes") or []
		total_recebido += recebido
		vencimento = vencimentos[ym]

		antes_do_inicio = inicio_mes is not None and mes < inicio_mes
		comeca_no_futuro = inicio is not None and mes == inicio_mes and inicio > hoje

		if antes_do_inicio or comeca_no_futuro:
			# Fora da vigência da cobrança: o que porventura entrou vira crédito.
			credito += recebido
			if transacoes:
				credito_data = _maior_data(credito_data, _ultima_data(transacoes))
			status = STATUS_AGUARDANDO if comeca_no_futuro else STATUS_NAO_APLICAVEL
			linhas.append(
				{
					"ym": ym,
					"rotulo": rotulo_mes(mes),
					"esperado": 0.0,
					"minimo": 0.0,
					"recebido": recebido,
					"coberto": 0.0,
					"qtd_transacoes": qtd,
					"status_fixo": status,
					"usou_credito": False,
					"quitacao_retroativa": False,
					"em_atraso": False,
					"motivo": motivos.get(ym),
					"vencido": False,
				}
			)
			continue

		# 1) o dinheiro da carteira retroativa quita a dívida mais antiga primeiro.
		retroativo = _valor_retroativo(transacoes, unidades)
		sobra_retroativa = _quitar_meses_anteriores(linhas, retroativo)
		do_mes = round(recebido - retroativo + sobra_retroativa, 2)

		vencido = mes < mes_atual or hoje > vencimento
		esperado = esperado_mensal
		em_atraso = False

		# 2) o mês que vence sem dinheiro suficiente passa a valer o valor de atraso.
		if esperado > 0 and vencido:
			credito_em_dia = credito if (credito_data is None or credito_data <= vencimento) else 0.0
			disponivel_em_dia = min(do_mes, _recebido_ate(transacoes, vencimento)) + credito_em_dia
			if disponivel_em_dia + TOLERANCIA < esperado_mensal:
				esperado = parametros.valor_em_atraso(esperado_mensal)
				em_atraso = esperado > esperado_mensal

		disponivel = round(do_mes + credito, 2)
		status_fixo = None
		if esperado <= 0:
			coberto = 0.0
			usou_credito = False
			credito = disponivel
			status_fixo = STATUS_PAGO if recebido > 0 else STATUS_NAO_APLICAVEL
		else:
			coberto = round(min(disponivel, esperado), 2)
			usou_credito = coberto > do_mes + TOLERANCIA
			credito = round(disponivel - coberto, 2)

		if credito <= TOLERANCIA:
			credito = 0.0
			credito_data = None
		elif transacoes:
			credito_data = _maior_data(credito_data, _ultima_data(transacoes))

		linhas.append(
			{
				"ym": ym,
				"rotulo": rotulo_mes(mes),
				"esperado": esperado,
				# O que se cobra é `esperado`; o que fecha o mês é `minimo`.
				"minimo": esperado_mensal,
				"recebido": recebido,
				"coberto": coberto,
				"qtd_transacoes": qtd,
				"status_fixo": status_fixo,
				"usou_credito": usou_credito,
				"quitacao_retroativa": False,
				"em_atraso": em_atraso,
				"motivo": motivos.get(ym),
				"vencido": vencido,
			}
		)

	# A situação de cada mês só fecha no fim: um mês já percorrido ainda pode ser
	# quitado pelo pagamento retroativo de um mês posterior.
	total_esperado = 0.0
	meses_devidos = 0
	meses_quitados = 0
	for linha in linhas:
		status = linha.pop("status_fixo", None) or _status_do_mes(linha)
		linha["status"] = status
		linha["status_slug"] = SLUG_SITUACAO[status]
		# Mês quitado não deve nada, nem o acréscimo de atraso que ninguém pagou.
		linha["falta"] = (
			0.0 if status == STATUS_PAGO else round(max(0.0, linha["esperado"] - linha["coberto"]), 2)
		)
		linha["quitado_sem_acrescimo"] = bool(
			status == STATUS_PAGO and linha["coberto"] + TOLERANCIA < linha["esperado"]
		)
		total_esperado += linha["esperado"]
		if linha["esperado"] > 0:
			meses_devidos += 1
			if status == STATUS_PAGO:
				meses_quitados += 1

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
		"valor_em_atraso": parametros.valor_em_atraso(esperado_mensal),
		"inicio_do_pagamento": inicio.isoformat() if inicio else None,
		"inicio_calculado": bool(inicio and not contribuinte.get("inicio_do_pagamento")),
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

	parametros = get_parametros()
	dia_vencimento = parametros.dia_vencimento
	vencimentos = {chave_mes(mes): calcular_vencimento(mes, dia_vencimento) for mes in sequencia}
	valor_base = parametros.valor_base

	contribuintes = _com_datas_de_ingresso(get_contribuintes())
	recebimentos = get_recebimentos_por_associado(primeiro_dia, proximo_mes)
	nao_vinculadas = get_transacoes_nao_vinculadas(primeiro_dia, proximo_mes)

	chaves = [chave_mes(mes) for mes in sequencia]
	recebido_mes = dict.fromkeys(chaves, 0.0)
	esperado_mes = dict.fromkeys(chaves, 0.0)
	devidos_mes = dict.fromkeys(chaves, 0)
	quitados_mes = dict.fromkeys(chaves, 0)
	inadimplentes_mes = dict.fromkeys(chaves, 0)
	status_mes = {situacao: dict.fromkeys(chaves, 0) for situacao in SITUACOES_DO_MES_DEVIDO}

	associados = []
	for contribuinte in contribuintes:
		grade = montar_grade(
			contribuinte,
			sequencia,
			recebimentos.get(contribuinte["name"], {}),
			hoje,
			vencimentos,
			valor_base,
			parametros,
		)
		for linha in grade["linhas"]:
			ym = linha["ym"]
			recebido_mes[ym] += linha["recebido"]
			esperado_mes[ym] += linha["esperado"]
			if linha["esperado"] > 0:
				devidos_mes[ym] += 1
				if linha["status"] == STATUS_PAGO:
					quitados_mes[ym] += 1
				if linha["status"] in status_mes:
					status_mes[linha["status"]][ym] += 1
				if linha["status"] in SITUACOES_INADIMPLENTES and linha["vencido"]:
					inadimplentes_mes[ym] += 1

		inicio = grade["inicio_do_pagamento"]
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
				"acao_cadastro": _acao_de_cadastro(contribuinte, hoje, getdate(inicio) if inicio else None),
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

	com_pendencia = [a for a in associados if a["situacao"] in SITUACOES_INADIMPLENTES]
	# Inadimplente é quem tem ao menos um mês vencido e não quitado — a situação
	# resumida sozinha não basta, porque ela também marca o parcial no prazo.
	inadimplentes = [
		a
		for a in associados
		if any(linha["status"] in SITUACOES_INADIMPLENTES and linha["vencido"] for linha in a["linhas"])
	]

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
			"inadimplencia": [
				round((inadimplentes_mes[ym] / devidos_mes[ym]) * 100, 2) if devidos_mes[ym] else 0.0
				for ym in chaves
			],
			"meses_devidos": [devidos_mes[ym] for ym in chaves],
			"por_situacao": {
				situacao: [status_mes[situacao][ym] for ym in chaves] for situacao in SITUACOES_DO_MES_DEVIDO
			},
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
			"inadimplentes": len(inadimplentes),
			"inadimplencia_associados": (
				round((len(inadimplentes) / len(associados)) * 100, 2) if associados else 0.0
			),
			"a_cadastrar": len([a for a in associados if a["acao_cadastro"] == "Cadastrar"]),
			"a_cancelar": len([a for a in associados if a["acao_cadastro"] == "Cancelar"]),
			"transacoes_nao_vinculadas": len(nao_vinculadas),
		},
	}


def apurar_associados(
	nomes: list[str],
	meses=MESES_PADRAO,
	hoje: datetime.date | None = None,
	incluir_gestao: bool = False,
) -> list[dict]:
	"""Apura a contribuição de um conjunto fechado de associados.

	Mesma regra da apuração geral, mas sem varrer o grupo inteiro: serve às telas
	que já sabem de quem estão falando — o responsável olhando os beneficiários
	vinculados a ele, a cobrança de um contribuinte específico e o detalhe de um
	associado no financeiro.

	`incluir_gestao` acrescenta a pendência de cadastro e os dados de cobrança
	(e-mail/telefone) — informação de gestão, que só a tela do financeiro mostra
	e só para quem tem a role de gestor da contribuição mensal.

	Associados de categoria não contribuinte (Dirigente, Escotista) são
	descartados aqui pelo mesmo motivo de sempre: eles não pagam contribuição
	mensal.
	"""
	if not nomes:
		return []

	quantidade_meses = normalizar_meses(meses)
	hoje = hoje or getdate()
	sequencia = construir_meses(quantidade_meses, hoje)
	primeiro_dia = sequencia[0]
	proximo_mes = getdate(add_months(sequencia[-1], 1))

	parametros = get_parametros()
	dia_vencimento = parametros.dia_vencimento
	vencimentos = {chave_mes(mes): calcular_vencimento(mes, dia_vencimento) for mes in sequencia}
	valor_base = parametros.valor_base

	contribuintes = frappe.get_all(
		"Associado",
		filters={
			"name": ["in", list(nomes)],
			"categoria": ["in", list(CATEGORIAS_CONTRIBUINTES)],
		},
		fields=list(CAMPOS_CONTRIBUINTE),
		order_by="nome_completo asc",
		limit_page_length=0,
	)
	if not contribuintes:
		return []

	contribuintes = _com_datas_de_ingresso(contribuintes)
	recebimentos = get_recebimentos_por_associado(
		primeiro_dia, proximo_mes, [c["name"] for c in contribuintes]
	)

	apurados = []
	for contribuinte in contribuintes:
		grade = montar_grade(
			contribuinte,
			sequencia,
			recebimentos.get(contribuinte["name"], {}),
			hoje,
			vencimentos,
			valor_base,
			parametros,
		)
		dados_gestao = {}
		if incluir_gestao:
			inicio = grade["inicio_do_pagamento"]
			dados_gestao = {
				"acao_cadastro": _acao_de_cadastro(contribuinte, hoje, getdate(inicio) if inicio else None),
				"email_cobranca": contribuinte.get("email_cobranca"),
				"telefone_cobranca": contribuinte.get("telefone_cobranca"),
			}
		apurados.append(
			{
				"id": contribuinte["name"],
				"nome": contribuinte.get("nome_completo") or contribuinte["name"],
				"categoria": contribuinte.get("categoria"),
				"secao": contribuinte.get("secao"),
				"status_no_grupo": contribuinte.get("status_no_grupo"),
				"status_cobranca": contribuinte.get("status_cobranca"),
				"dia_vencimento": dia_vencimento,
				**dados_gestao,
				**grade,
			}
		)
	return apurados


def competencias_pendentes(apuracao: dict) -> list[dict]:
	"""Meses do associado que ainda não foram quitados, do mais antigo ao mais novo.

	Um mês parcial entra pelo que falta, não pelo valor cheio — cobrar de novo o
	que já foi pago viraria crédito e empurraria a dívida para o mês seguinte.
	"""
	pendentes = []
	for linha in apuracao.get("linhas", []):
		if linha["status"] not in (STATUS_ATRASADO, STATUS_EM_ABERTO, STATUS_PARCIAL):
			continue
		# `coberto` (e não `recebido`) é o que já quitou o mês: ele inclui o crédito
		# de meses anteriores e o pagamento retroativo feito num mês posterior.
		coberto = float(linha.get("coberto", linha["recebido"]))
		falta = round(float(linha.get("falta", float(linha["esperado"]) - coberto)), 2)
		if falta <= 0:
			continue
		pendentes.append(
			{
				"ym": linha["ym"],
				"rotulo": linha["rotulo"],
				"status": linha["status"],
				"status_slug": linha["status_slug"],
				"esperado": linha["esperado"],
				"recebido": linha["recebido"],
				"coberto": coberto,
				"valor": falta,
			}
		)
	return pendentes


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
