# Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import hashlib
import re

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today

from gris.utils.job_logger import definir_resumo, metrica, obter_logger

# Ramos em ordem crescente de idade e o campo do Single ``Vagas`` que guarda a
# idade de transição (limite superior) de cada um. O último ramo (Pioneiro)
# acolhe qualquer idade acima da sua própria transição.
CAMPOS_DE_TRANSICAO = (
	("Filhotes", "idade_transicao_filhotes"),
	("Lobinho", "idade_transicao_lobinho"),
	("Escoteiro", "idade_transicao_escoteiro"),
	("Sênior", "idade_transicao_senior"),
	("Pioneiro", "idade_transicao_pioneiro"),
)

STATUS_AGUARDAR_DADOS = "Aguardar Dados"


class NovoAssociado(Document):
	def autoname(self):
		if self.cpf:
			cpf_clean = re.sub(r"\D", "", self.cpf)
			self.name = hashlib.md5(cpf_clean.encode("utf-8")).hexdigest()

	def before_insert(self):
		ramo = ramo_por_data_de_nascimento(self.data_de_nascimento)
		if ramo:
			self.ramo = ramo

	def validate(self):
		self._sincronizar_data_registro_provisorio()
		self._sincronizar_data_aguardar_dados()

	def _sincronizar_data_aguardar_dados(self):
		"""Marca desde quando o jovem está parado em "Aguardar Dados".

		A data é a base da escada de lembretes de preenchimento (ver
		``gris.api.recepcao_mensagens.enviar_lembretes_dados_registro``). Sair do status
		zera a data e o controle de envio para que um retorno recomece a cadência do zero.
		"""
		if self.status == STATUS_AGUARDAR_DADOS:
			if not self.data_status_aguardar_dados:
				self.data_status_aguardar_dados = today()
		else:
			self.data_status_aguardar_dados = None
			self.data_lembrete_dados = None

	def _sincronizar_data_registro_provisorio(self):
		"""Mantém a data de ativação do registro provisório em sincronia com o flag.

		A data alimenta o aviso automático de seguimento (ver
		``gris.api.registro_provisorio_notificacoes``). Ao desmarcar o flag, a data e o
		controle de aviso são limpos para que um novo ciclo recomece do zero.
		"""
		if self.registro_provisorio_efetivado:
			if not self.data_registro_provisorio_efetivado:
				self.data_registro_provisorio_efetivado = today()
		else:
			self.data_registro_provisorio_efetivado = None
			self.data_aviso_seguimento_provisorio = None

	def on_trash(self):
		"""Limpa referências em Responsavel Vinculo ao excluir Novo Associado."""
		vinculos = frappe.get_all(
			"Responsavel Vinculo",
			filters={"beneficiario_novo_associado": self.name},
			pluck="name",
		)
		for vinculo_name in vinculos:
			frappe.db.set_value("Responsavel Vinculo", vinculo_name, "beneficiario_novo_associado", None)


def obter_faixas_de_ramo():
	"""Idades de transição configuradas no Single ``Vagas``, do ramo mais novo ao mais velho.

	Lida uma vez por rotina e repassada para ``ramo_por_data_de_nascimento`` para
	evitar uma consulta ao Single por registro avaliado.
	"""
	vagas = frappe.get_single("Vagas")
	return [(ramo, float(vagas.get(campo) or 0)) for ramo, campo in CAMPOS_DE_TRANSICAO]


def idade_decimal(data_de_nascimento, hoje=None):
	"""Idade em anos com a fração de meses (10 anos e 6 meses -> 10.5)."""
	nascimento = getdate(data_de_nascimento)
	hoje = getdate(hoje or today())

	anos = hoje.year - nascimento.year
	meses = hoje.month - nascimento.month
	if hoje.day < nascimento.day:
		meses -= 1
	if meses < 0:
		anos -= 1
		meses += 12

	return anos + meses / 12


def ramo_por_data_de_nascimento(data_de_nascimento, faixas=None, hoje=None):
	"""Retorna o ramo correspondente à idade decimal calculada da data de nascimento.

	Usa as idades de transição definidas no Single ``Vagas`` como limite superior
	de cada ramo: se a idade for maior que a idade de transição, o jovem é
	promovido ao próximo ramo. O último ramo (Pioneiro) acolhe qualquer idade acima.
	"""
	if not data_de_nascimento:
		return None

	faixas = faixas or obter_faixas_de_ramo()
	idade = idade_decimal(data_de_nascimento, hoje)

	for nome, idade_transicao in faixas[:-1]:
		if idade <= idade_transicao:
			return nome
	return faixas[-1][0]


def atualizar_ramos_por_idade():
	"""Recalcula diariamente o ramo de todos os Novo Associado pela idade atual.

	O ramo é gravado uma vez em ``before_insert`` e envelhece junto com o jovem: sem
	esta rotina, quem cruza a idade de transição continua registrado no ramo antigo e
	distorce a ocupação de vagas e a fila de espera. As linhas de ``Fila de Espera``
	que apontam para o registro são sincronizadas com o mesmo ramo.

	Rodada pelo scheduler (``daily`` em ``hooks.py``). Recalcular é a regra: um ramo
	definido manualmente (ex.: pela recepção em ``gris.api.recepcao``) volta para o
	ramo da idade no próximo ciclo.
	"""
	logger = obter_logger("novos_associados")
	faixas = obter_faixas_de_ramo()
	hoje = getdate(today())

	registros = frappe.get_all(
		"Novo Associado",
		fields=["name", "nome_completo", "data_de_nascimento", "ramo"],
	)

	# Uma consulta só: a fila é pequena e evita um get_value por registro avaliado.
	fila_por_associado = {}
	for linha in frappe.get_all("Fila de Espera", fields=["name", "associado", "ramo"]):
		if linha.associado:
			fila_por_associado.setdefault(linha.associado, []).append(linha)

	logger.info(f"Avaliando o ramo de {len(registros)} novo(s) associado(s).")

	promovidos = 0
	sem_dados = 0
	fila_sincronizada = 0
	for registro in registros:
		if not registro.data_de_nascimento:
			sem_dados += 1
			logger.warning(
				f"{registro.nome_completo or registro.name} sem data de nascimento — ramo nao recalculado."
			)
			continue

		ramo = ramo_por_data_de_nascimento(registro.data_de_nascimento, faixas, hoje)
		linhas_desatualizadas = [
			linha for linha in fila_por_associado.get(registro.name, []) if linha.ramo != ramo
		]
		if registro.ramo == ramo and not linhas_desatualizadas:
			continue

		if registro.ramo != ramo:
			frappe.db.set_value("Novo Associado", registro.name, "ramo", ramo)
			promovidos += 1
			logger.info(
				f"{registro.nome_completo or registro.name} mudou de {registro.ramo or '—'} "
				f"para {ramo} ({idade_decimal(registro.data_de_nascimento, hoje):.1f} anos)."
			)

		for linha in linhas_desatualizadas:
			frappe.db.set_value("Fila de Espera", linha.name, "ramo", ramo)
			fila_sincronizada += 1

		# Commit por registro: a promoção de ramo de cada jovem é independente.
		# Um erro em um registro adiante não pode desfazer os já promovidos.
		frappe.db.commit()  # nosemgrep

	metrica("avaliados", len(registros), incrementar=False)
	metrica("promovidos", promovidos, incrementar=False)
	metrica("fila_sincronizada", fila_sincronizada, incrementar=False)
	metrica("sem_dados", sem_dados, incrementar=False)
	definir_resumo(
		f"{promovidos} novo(s) associado(s) mudaram de ramo (de {len(registros)} avaliados; "
		f"{fila_sincronizada} linha(s) da fila de espera sincronizada(s); "
		f"{sem_dados} sem data de nascimento)."
	)
