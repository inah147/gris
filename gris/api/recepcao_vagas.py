"""Ocupação de vagas por ramo.

A Fila de Espera mostra quantas vagas cada ramo tem e a visão geral marca os cards de
ramos sem vaga. As duas telas leem a mesma conta daqui, senão a recepção veria dois
números diferentes para o mesmo ramo.

Ocupam vaga os associados ativos (beneficiários) e os novos associados da visita
agendada em diante. Cada pessoa conta uma vez só: ``Associado`` e ``Novo Associado``
são nomeados pelo md5 dos dígitos do CPF, então o jovem que já tem registro e ainda
está no funil é reconhecido pelo mesmo identificador e conta pelo Associado.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_months, getdate, today

from gris.api.recepcao_funil import (
	RAMOS,
	STATUS_AGUARDAR_DADOS,
	STATUS_ANTES_DA_VISITA,
	STATUS_FAZER_REGISTRO,
	STATUS_VISITA_AGENDADA,
)
from gris.utils.documento import id_por_cpf

# Sufixo dos campos do Single ``Vagas`` (``limite_de_vagas_<slug>``, ``idade_maxima_<slug>``).
RAMO_SLUGS: dict[str, str] = {
	"Filhotes": "filhotes",
	"Lobinho": "lobinho",
	"Escoteiro": "escoteiro",
	"Sênior": "senior",
	"Pioneiro": "pioneiro",
}

STATUS_NOVO_CONTATO = "Novo Contato"

# Quem ainda não agendou a visita não segura vaga, e quem foi para a fila está
# justamente esperando uma. A grafia é a da opção do Select ("Fila de espera").
STATUS_QUE_NAO_OCUPAM_VAGA: tuple[str, ...] = (
	STATUS_NOVO_CONTATO,
	STATUS_ANTES_DA_VISITA,
	"Fila de espera",
)

# Colunas anteriores ao acompanhamento: é nelas que a recepção ainda decide se traz o
# jovem, então é nelas que o ramo lotado precisa aparecer no card.
STATUS_COM_SELO_SEM_VAGAS: tuple[str, ...] = (
	STATUS_NOVO_CONTATO,
	STATUS_ANTES_DA_VISITA,
	STATUS_VISITA_AGENDADA,
	STATUS_AGUARDAR_DADOS,
	STATUS_FAZER_REGISTRO,
)

# Horizonte das saídas por idade que já contam como vaga disponível.
MESES_DE_SAIDA_PREVISTA = 6

# Meses do gráfico "Previsão de vagas" do dialog "Cálculo de Vagas".
MESES_DE_PREVISAO = 12
MESES_CURTOS = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")

# O que o dialog "Cálculo de Vagas" mostra de cada ramo. As datas de saída ficam de fora:
# só servem à previsão de posição da fila e não viajam para o navegador.
CAMPOS_DO_DIALOG = ("limite", "ativos", "novos", "saindo", "disponiveis", "chart_labels", "chart_values")


def ocupa_vaga(status: str | None) -> bool:
	return bool(status) and status not in STATUS_QUE_NAO_OCUPAM_VAGA


def saindo_ate(saidas_futuras: list, hoje, meses_a_frente: int = 0) -> int:
	"""Associados que atingem a idade máxima de hoje até ``meses_a_frente`` + 6 meses.

	É o "(+) Atingindo idade limite (6 meses)" do total disponível — com
	``meses_a_frente`` o mesmo termo visto daquele mês. Quem já passou da idade e continua
	ativo segue ocupando a vaga, então só conta saída de hoje em diante.
	"""
	hoje = getdate(hoje)
	fim_do_horizonte = getdate(add_months(hoje, meses_a_frente + MESES_DE_SAIDA_PREVISTA))
	return sum(1 for saida in saidas_futuras if hoje <= saida <= fim_do_horizonte)


def previsao_mensal(vagas_agora: int, saidas_futuras: list, hoje) -> tuple[list[str], list[int]]:
	"""Rótulos e valores do gráfico de previsão, mês a mês, a partir do mês atual.

	Cada ponto é o total disponível calculado naquele mês, com a mesma fórmula do
	dialog: ``limite - ativos - novos`` (``vagas_agora``) mais quem atinge a idade máxima
	até 6 meses depois dele (``saindo_ate``). O ponto do mês atual é o próprio total.
	"""
	hoje = getdate(hoje)
	rotulos, valores = [], []
	for i in range(MESES_DE_PREVISAO):
		mes = getdate(add_months(hoje, i))
		rotulos.append(f"{MESES_CURTOS[mes.month - 1]}/{str(mes.year)[2:]}")
		valores.append(vagas_agora + saindo_ate(saidas_futuras, hoje, meses_a_frente=i))
	return rotulos, valores


def calcular_vagas_por_ramo(novos_associados: list | None = None, hoje=None) -> dict[str, frappe._dict]:
	"""Limite, ocupação e vagas disponíveis de cada ramo.

	``novos_associados`` evita reconsultar o funil quando quem chama já tem as linhas em
	mãos (a visão geral carrega todas). Cada linha precisa de ``name``, ``cpf``, ``ramo``
	e ``status``; as que não ocupam vaga são ignoradas aqui.

	Devolve, por ramo: ``limite``, ``ativos``, ``novos``, ``saindo`` (associados que
	atingem a idade máxima nos próximos 6 meses), ``disponiveis``
	(``limite - ativos - novos + saindo``), ``chart_labels``/``chart_values`` (gráfico de
	``previsao_mensal``) e ``saidas_futuras`` (datas de saída por idade, em ordem), que a
	Fila de Espera usa na previsão de posição.
	"""
	hoje = getdate(hoje or today())
	vagas = frappe.get_single("Vagas")

	associados = frappe.get_all(
		"Associado",
		filters={"status_no_grupo": "Ativo", "categoria": "Beneficiário", "ramo": ["in", list(RAMOS)]},
		fields=["name", "ramo", "data_de_nascimento"],
	)

	if novos_associados is None:
		novos_associados = frappe.get_all(
			"Novo Associado",
			filters={"status": ["not in", list(STATUS_QUE_NAO_OCUPAM_VAGA)], "ramo": ["in", list(RAMOS)]},
			fields=["name", "cpf", "ramo", "status"],
		)

	# Identificadores (md5 do CPF) de quem já ocupa vaga. O Novo Associado de quem já
	# está aqui não conta de novo — nem em outro ramo, se os dois cadastros divergirem.
	contados = {associado.name for associado in associados}
	novos_por_ramo = dict.fromkeys(RAMOS, 0)
	for novo in novos_associados:
		ramo = novo.get("ramo")
		if ramo not in novos_por_ramo or not ocupa_vaga(novo.get("status")):
			continue

		chave = id_por_cpf(novo.get("cpf")) or novo.get("name")
		if chave in contados:
			continue

		contados.add(chave)
		novos_por_ramo[ramo] += 1

	associados_por_ramo = {ramo: [] for ramo in RAMOS}
	for associado in associados:
		associados_por_ramo[associado.ramo].append(associado)

	resultado = {}
	for ramo in RAMOS:
		slug = RAMO_SLUGS[ramo]
		limite = vagas.get(f"limite_de_vagas_{slug}") or 0
		idade_maxima = vagas.get(f"idade_maxima_{slug}") or 0
		ativos = associados_por_ramo[ramo]
		novos = novos_por_ramo[ramo]

		saidas_futuras = []
		if idade_maxima:
			saidas_futuras = sorted(
				getdate(add_months(getdate(associado.data_de_nascimento), int(idade_maxima) * 12))
				for associado in ativos
				if associado.data_de_nascimento
			)

		saindo = saindo_ate(saidas_futuras, hoje)
		vagas_agora = limite - len(ativos) - novos
		chart_labels, chart_values = previsao_mensal(vagas_agora, saidas_futuras, hoje)

		resultado[ramo] = frappe._dict(
			limite=limite,
			ativos=len(ativos),
			novos=novos,
			saindo=saindo,
			disponiveis=vagas_agora + saindo,
			chart_labels=chart_labels,
			chart_values=chart_values,
			saidas_futuras=saidas_futuras,
		)

	return resultado


def dados_do_dialog(vagas_por_ramo: dict) -> dict[str, dict]:
	"""O que o dialog "Cálculo de Vagas" mostra de cada ramo.

	A Fila de Espera e os modais dos cards da visão geral abrem o mesmo dialog
	(``templates/includes/vagas_do_ramo_dialog.html``), que recebe isto como JSON.
	"""
	return {
		ramo: {campo: dados.get(campo) for campo in CAMPOS_DO_DIALOG}
		for ramo, dados in vagas_por_ramo.items()
	}


def ramo_sem_vagas(vagas_por_ramo: dict, ramo: str | None, status: str | None) -> bool:
	"""Se o card leva o selo "Seção sem vagas" na visão geral.

	Só marca: nada no funil é bloqueado por isso.
	"""
	if status not in STATUS_COM_SELO_SEM_VAGAS:
		return False

	vagas_do_ramo = vagas_por_ramo.get(ramo)
	if not vagas_do_ramo:
		return False

	return vagas_do_ramo.disponiveis <= 0
