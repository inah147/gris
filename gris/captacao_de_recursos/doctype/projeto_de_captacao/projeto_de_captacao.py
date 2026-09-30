# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Projeto do banco de captação de recursos e a máquina de estados dele.

As transições vivem aqui, como métodos do documento, e não nos endpoints: quem
chama (`gris.api.captacao.endpoints`) decide **quem** pode agir; o documento decide
**se** a ação cabe no status atual e o que ela muda. Nenhum método daqui grava: o
endpoint chama `save()` depois, para que uma ação recusada não deixe meio caminho
persistido.

Toda ação deixa uma linha em `decisoes` — é a linha do tempo do projeto, com o
motivo de cada decisão. O diff campo a campo fica no `Version` (track_changes).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_fullname, now_datetime

from gris.api.gestao_adultos import identidade
from gris.utils.diretoria import pessoas_do_usuario

STATUS_PRELIMINAR = "Preliminar"
STATUS_APROVADO_INICIALMENTE = "Aprovado inicialmente"
STATUS_EM_DETALHAMENTO = "Em detalhamento"
STATUS_REVISAO_TECNICA = "Revisão técnica"
STATUS_APROVACAO_FINAL = "Aprovação final"
STATUS_PRONTO = "Pronto para captação"
STATUS_EM_CAPTACAO = "Captação em andamento"
STATUS_CAPTACAO_FINALIZADA = "Captação finalizada"
STATUS_CANCELADO = "Cancelado"

#: Ordem das colunas do kanban.
STATUS_ORDENADOS = (
	STATUS_PRELIMINAR,
	STATUS_APROVADO_INICIALMENTE,
	STATUS_EM_DETALHAMENTO,
	STATUS_REVISAO_TECNICA,
	STATUS_APROVACAO_FINAL,
	STATUS_PRONTO,
	STATUS_EM_CAPTACAO,
	STATUS_CAPTACAO_FINALIZADA,
	STATUS_CANCELADO,
)

#: Colunas entre as quais o card anda livremente, arrastando.
STATUS_DE_CAPTACAO = (STATUS_PRONTO, STATUS_EM_CAPTACAO, STATUS_CAPTACAO_FINALIZADA, STATUS_CANCELADO)

#: Status em que o proponente ainda escreve o detalhamento.
STATUS_DETALHAVEIS = (STATUS_APROVADO_INICIALMENTE, STATUS_EM_DETALHAMENTO)

#: Status em que o projeto ainda não chegou ao banco e pode ser cancelado por decisão.
STATUS_CANCELAVEIS = (
	STATUS_PRELIMINAR,
	STATUS_APROVADO_INICIALMENTE,
	STATUS_EM_DETALHAMENTO,
	STATUS_REVISAO_TECNICA,
	STATUS_APROVACAO_FINAL,
)

ETAPA_IDEIA = "Ideia"
ETAPA_APROVACAO_INICIAL = "Aprovação inicial"
ETAPA_DETALHAMENTO = "Detalhamento"
ETAPA_REVISAO_TECNICA = "Revisão técnica"
ETAPA_APROVACAO_FINAL = "Aprovação final"
ETAPA_CAPTACAO = "Captação"

DECISAO_IDEIA_ENVIADA = "Ideia enviada"
DECISAO_IDEIA_REENVIADA = "Ideia reenviada"
DECISAO_ENVIAR_DETALHAMENTO = "Enviar para detalhamento"
DECISAO_SOLICITAR_ALTERACAO = "Solicitar alteração"
DECISAO_NAO_CABE = "Não cabe em projetos de captação"
DECISAO_OUTRA_MANEIRA = "Realizado de outra maneira"
DECISAO_DETALHAMENTO_ENVIADO = "Detalhamento enviado"
DECISAO_PENDENCIA_RESOLVIDA = "Pendência resolvida"
DECISAO_ALTERACAO_MANUAL = "Alteração manual"
DECISAO_APROVAR = "Aprovar"
DECISAO_MUDANCA_DE_STATUS = "Mudança de status"

DECISOES_DO_PRELIMINAR = (
	DECISAO_ENVIAR_DETALHAMENTO,
	DECISAO_SOLICITAR_ALTERACAO,
	DECISAO_NAO_CABE,
	DECISAO_OUTRA_MANEIRA,
)
DECISOES_DA_APROVACAO_FINAL = (DECISAO_APROVAR, DECISAO_SOLICITAR_ALTERACAO)

ENCERRAMENTO_CANCELADO = "Cancelado"

#: Partes do projeto, na ordem do formulário. É a lista que a RI usa para pedir
#: alteração por seção e a que o envio para revisão confere.
SECOES = {
	"titulo": "Título",
	"resumo": "Resumo",
	"objetivos": "Objetivos",
	"equipe": "Apresentação dos responsáveis",
	"descricao": "Descrição do projeto",
	"publico_alvo": "Público-alvo",
	"justificativa": "Justificativa",
	"metodologia": "Metodologia",
	"atividades": "Atividades e cronograma",
	"impacto_social": "Impacto social",
	"recursos": "Recursos",
}

CAMPOS_DE_TEXTO_DO_DETALHAMENTO = (
	"descricao",
	"publico_alvo",
	"justificativa",
	"metodologia",
	"impacto_social",
)
CAMPOS_DAS_TABELAS = {
	"objetivos": ("objetivo", "metrica_de_sucesso"),
	"equipe": ("nome", "papel", "apresentacao"),
	"atividades": ("atividade", "descricao", "dia_inicio", "dia_termino"),
	"recursos": ("categoria", "descricao", "quantidade", "valor_unitario"),
}
CATEGORIAS_DE_RECURSO = ("Humano", "Material", "Financeiro")

#: O cronograma conta dias a partir do início do projeto (dia 0), que só existe de
#: verdade quando um edital o financia. Dez anos bastam para qualquer edital.
MAIOR_DIA_DO_CRONOGRAMA = 3650

CAMPOS_DO_PROPONENTE = (
	"proponente_user",
	"proponente_tipo",
	"proponente_associado",
	"proponente_responsavel",
)


class ProjetodeCaptacao(Document):
	def before_insert(self):
		# O proponente é quem envia a ideia, qualquer que seja o caminho (portal,
		# Desk ou API): nunca vem do formulário.
		preencher_proponente(self, frappe.session.user)

	def validate(self):
		self._manter_proponente()
		self._preencher_nome_do_proponente()
		self._calcular_recursos()
		self._validar_atividades()

	# ------------------------------------------------------------------
	# Integridade
	# ------------------------------------------------------------------

	def _manter_proponente(self):
		if self.is_new():
			return
		antes = self.get_doc_before_save()
		if antes and any(self.get(campo) != antes.get(campo) for campo in CAMPOS_DO_PROPONENTE):
			frappe.throw(_("O proponente é quem enviou a ideia e não pode ser trocado."))

	def _preencher_nome_do_proponente(self):
		nome = ""
		if self.proponente_tipo == "Associado" and self.proponente_associado:
			nome = frappe.db.get_value("Associado", self.proponente_associado, "nome_completo")
		elif self.proponente_tipo == "Responsavel" and self.proponente_responsavel:
			nome = frappe.db.get_value("Responsavel", self.proponente_responsavel, "nome_completo")
		self.proponente_nome = nome or self.proponente_nome or get_fullname(self.proponente_user)

	def _calcular_recursos(self):
		total = 0.0
		for linha in self.recursos or []:
			if linha.categoria and linha.categoria not in CATEGORIAS_DE_RECURSO:
				frappe.throw(_("Categoria de recurso inválida: {0}.").format(linha.categoria))
			if flt(linha.quantidade) < 0 or flt(linha.valor_unitario) < 0:
				frappe.throw(_("Quantidade e valor dos recursos não podem ser negativos."))
			linha.valor_total = flt(linha.quantidade) * flt(linha.valor_unitario)
			total += flt(linha.valor_total)
		self.valor_total = total

	def _validar_atividades(self):
		"""Dias relativos: `[dia_inicio, dia_termino]`, com duração `término - início`.

		0 a 0 é o que o campo inteiro guarda quando nada foi digitado; o rascunho
		aceita, e o envio para revisão cobra (ver `secoes_incompletas`).
		"""
		for linha in self.atividades or []:
			inicio, termino = cint(linha.dia_inicio), cint(linha.dia_termino)
			nome = linha.atividade or linha.idx
			if inicio < 0 or termino < 0:
				frappe.throw(_("Os dias da atividade {0} não podem ser negativos.").format(nome))
			if inicio > MAIOR_DIA_DO_CRONOGRAMA or termino > MAIOR_DIA_DO_CRONOGRAMA:
				frappe.throw(
					_("O cronograma vai até o dia {0}; revise a atividade {1}.").format(
						MAIOR_DIA_DO_CRONOGRAMA, nome
					)
				)
			if inicio > termino:
				frappe.throw(_("A atividade {0} termina antes de começar.").format(nome))

	# ------------------------------------------------------------------
	# Leitura
	# ------------------------------------------------------------------

	def pendencias_abertas(self, etapas: tuple[str, ...] | None = None) -> list:
		"""Pedidos de alteração que o proponente ainda não marcou como atendidos."""
		return [
			linha
			for linha in self.decisoes or []
			if linha.decisao == DECISAO_SOLICITAR_ALTERACAO
			and not cint(linha.resolvido)
			and (etapas is None or linha.etapa in etapas)
		]

	def secoes_incompletas(self) -> list[str]:
		"""Rótulos das partes obrigatórias que ainda faltam para a revisão técnica."""
		faltando = [
			SECOES[campo] for campo in CAMPOS_DE_TEXTO_DO_DETALHAMENTO if not (self.get(campo) or "").strip()
		]
		if not self.objetivos:
			faltando.append(SECOES["objetivos"])
		if not [
			linha
			for linha in self.equipe or []
			if (linha.nome or "").strip() and (linha.apresentacao or "").strip()
		]:
			faltando.append(SECOES["equipe"])
		# O cronograma é o período de cada atividade, em dias do projeto: é ele que
		# desenha o Gantt. Terminar no mesmo dia em que começa é duração zero — na
		# prática, dias que não foram preenchidos.
		atividades = self.atividades or []
		if not atividades or any(
			not (linha.atividade or "").strip() or cint(linha.dia_termino) <= cint(linha.dia_inicio)
			for linha in atividades
		):
			faltando.append(SECOES["atividades"])
		recursos = self.recursos or []
		if not recursos or any(
			not linha.categoria or not (linha.descricao or "").strip() for linha in recursos
		):
			faltando.append(SECOES["recursos"])
		return sorted(faltando, key=list(SECOES.values()).index)

	# ------------------------------------------------------------------
	# Transições
	# ------------------------------------------------------------------

	def registrar_ideia(self, user: str) -> None:
		self._registrar(etapa=ETAPA_IDEIA, decisao=DECISAO_IDEIA_ENVIADA, user=user, status_anterior="")

	def reenviar_ideia(self, user: str) -> None:
		"""O proponente atendeu ao pedido da Diretoria: as pendências da ideia fecham."""
		self._exigir_status(STATUS_PRELIMINAR)
		for linha in self.pendencias_abertas((ETAPA_APROVACAO_INICIAL,)):
			linha.resolvido = 1
		self._registrar(etapa=ETAPA_IDEIA, decisao=DECISAO_IDEIA_REENVIADA, user=user)

	def decidir_preliminar(self, decisao: str, comentario: str, user: str) -> None:
		self._exigir_status(STATUS_PRELIMINAR)
		if decisao not in DECISOES_DO_PRELIMINAR:
			frappe.throw(_("Decisão inválida para uma ideia preliminar."))
		comentario = (comentario or "").strip()
		if decisao != DECISAO_ENVIAR_DETALHAMENTO and not comentario:
			frappe.throw(_("Descreva o motivo da decisão."))

		status_anterior = self.status
		if decisao == DECISAO_ENVIAR_DETALHAMENTO:
			# Aprovar a ideia supera o pedido de alteração que estava em aberto.
			for linha in self.pendencias_abertas((ETAPA_APROVACAO_INICIAL,)):
				linha.resolvido = 1
			self.status = STATUS_APROVADO_INICIALMENTE
			self.aprovado_inicialmente_em = now_datetime()
		elif decisao in (DECISAO_NAO_CABE, DECISAO_OUTRA_MANEIRA):
			self._encerrar(decisao, comentario)

		self._registrar(
			etapa=ETAPA_APROVACAO_INICIAL,
			decisao=decisao,
			user=user,
			comentario=comentario,
			status_anterior=status_anterior,
			resolvido=0 if decisao == DECISAO_SOLICITAR_ALTERACAO else 1,
		)

	def iniciar_detalhamento(self) -> None:
		"""O primeiro salvamento do detalhamento tira o card de "Aprovado inicialmente"."""
		self._exigir_status(*STATUS_DETALHAVEIS)
		self.status = STATUS_EM_DETALHAMENTO

	def enviar_para_revisao(self, user: str) -> None:
		self._exigir_status(*STATUS_DETALHAVEIS)
		faltando = self.secoes_incompletas()
		if faltando:
			frappe.throw(_("Preencha antes de enviar: {0}.").format(", ".join(faltando)))
		if self.pendencias_abertas((ETAPA_REVISAO_TECNICA, ETAPA_APROVACAO_FINAL)):
			frappe.throw(_("Marque como atendidos todos os pedidos de alteração antes de enviar."))

		status_anterior = self.status
		self.status = STATUS_REVISAO_TECNICA
		self._registrar(
			etapa=ETAPA_DETALHAMENTO,
			decisao=DECISAO_DETALHAMENTO_ENVIADO,
			user=user,
			status_anterior=status_anterior,
		)

	def solicitar_alteracoes(self, etapa: str, pedidos: list[dict], user: str) -> None:
		"""Um pedido por parte do projeto, cada um com a justificativa. Volta ao proponente.

		A revisão técnica e a aprovação final pedem alteração do mesmo jeito; muda só
		a etapa registrada e o status de onde o projeto sai.
		"""
		esperado = {
			ETAPA_REVISAO_TECNICA: STATUS_REVISAO_TECNICA,
			ETAPA_APROVACAO_FINAL: STATUS_APROVACAO_FINAL,
		}
		if etapa not in esperado:
			frappe.throw(_("Etapa inválida para pedir alterações."))
		self._exigir_status(esperado[etapa])

		pedidos_validos = []
		for pedido in pedidos or []:
			secao = (pedido.get("secao") or "").strip()
			comentario = (pedido.get("comentario") or "").strip()
			if secao and secao not in SECOES:
				frappe.throw(_("Parte do projeto inválida: {0}.").format(secao))
			if not comentario:
				frappe.throw(_("Justifique cada pedido de alteração."))
			pedidos_validos.append((secao, comentario))
		if not pedidos_validos:
			frappe.throw(_("Informe ao menos um pedido de alteração."))

		status_anterior = self.status
		self.status = STATUS_EM_DETALHAMENTO
		for secao, comentario in pedidos_validos:
			self._registrar(
				etapa=etapa,
				decisao=DECISAO_SOLICITAR_ALTERACAO,
				user=user,
				comentario=comentario,
				secao=secao,
				status_anterior=status_anterior,
				resolvido=0,
			)

	def resolver_pendencia(self, linha_name: str, user: str) -> None:
		linha = next((linha for linha in self.decisoes or [] if linha.name == linha_name), None)
		if not linha or linha.decisao != DECISAO_SOLICITAR_ALTERACAO:
			frappe.throw(_("Pedido de alteração não encontrado."))
		if cint(linha.resolvido):
			frappe.throw(_("Este pedido já foi marcado como atendido."))
		if linha.etapa == ETAPA_APROVACAO_INICIAL:
			frappe.throw(_("Para atender a Diretoria, edite a ideia e envie de novo."))
		self._exigir_status(*STATUS_DETALHAVEIS)

		linha.resolvido = 1
		self._registrar(
			etapa=ETAPA_DETALHAMENTO,
			decisao=DECISAO_PENDENCIA_RESOLVIDA,
			user=user,
			secao=linha.secao,
			comentario=linha.comentario,
		)

	def registrar_alteracao_manual(self, antes: dict, motivo: str, user: str) -> None:
		"""A RI editou o projeto: guarda o motivo e o que mudou, legível na linha do tempo."""
		self._exigir_status(STATUS_REVISAO_TECNICA)
		motivo = (motivo or "").strip()
		if not motivo:
			frappe.throw(_("Informe o motivo da alteração."))

		alteradas = [SECOES[campo] for campo, valor in fotografar(self).items() if antes.get(campo) != valor]
		if not alteradas:
			frappe.throw(_("Nenhuma parte do projeto foi alterada."))

		self._registrar(
			etapa=ETAPA_REVISAO_TECNICA,
			decisao=DECISAO_ALTERACAO_MANUAL,
			user=user,
			comentario=motivo,
			resumo_alteracoes=", ".join(alteradas),
		)

	def aprovar_revisao(self, comentario: str, user: str) -> None:
		self._exigir_status(STATUS_REVISAO_TECNICA)
		status_anterior = self.status
		self.status = STATUS_APROVACAO_FINAL
		self._registrar(
			etapa=ETAPA_REVISAO_TECNICA,
			decisao=DECISAO_APROVAR,
			user=user,
			comentario=(comentario or "").strip(),
			status_anterior=status_anterior,
		)

	def aprovar_final(self, comentario: str, user: str) -> None:
		"""Ciência da Diretoria. Não existe reprovar: a ideia já foi aprovada lá atrás."""
		self._exigir_status(STATUS_APROVACAO_FINAL)
		status_anterior = self.status
		self.status = STATUS_PRONTO
		self.aprovado_final_em = now_datetime()
		self._registrar(
			etapa=ETAPA_APROVACAO_FINAL,
			decisao=DECISAO_APROVAR,
			user=user,
			comentario=(comentario or "").strip(),
			status_anterior=status_anterior,
		)

	def cancelar(self, motivo: str, user: str) -> None:
		self._exigir_status(*STATUS_CANCELAVEIS)
		motivo = (motivo or "").strip()
		if not motivo:
			frappe.throw(_("Informe o motivo do cancelamento."))
		status_anterior = self.status
		self._encerrar(ENCERRAMENTO_CANCELADO, motivo)
		self._registrar(
			etapa=self._etapa_do_status(status_anterior),
			decisao=DECISAO_MUDANCA_DE_STATUS,
			user=user,
			comentario=motivo,
			status_anterior=status_anterior,
		)

	def mover_para(self, status_novo: str, user: str) -> bool:
		"""Arraste entre as colunas de captação. Devolve `False` quando nada muda."""
		if self.status not in STATUS_DE_CAPTACAO or status_novo not in STATUS_DE_CAPTACAO:
			frappe.throw(
				_(
					"Só é possível arrastar entre Pronto para captação, Captação em andamento, Captação finalizada e Cancelado."
				)
			)
		if status_novo == self.status:
			return False
		# Um projeto cancelado antes da aprovação final nunca passou pelo fluxo; não
		# pode entrar no banco pelo arraste.
		if self.status == STATUS_CANCELADO and status_novo != STATUS_CANCELADO and not self.aprovado_final_em:
			frappe.throw(_("Este projeto foi cancelado antes da aprovação final e não pode voltar ao banco."))

		status_anterior = self.status
		self.status = status_novo
		if status_novo == STATUS_CANCELADO:
			self.categoria_encerramento = ENCERRAMENTO_CANCELADO
		elif status_anterior == STATUS_CANCELADO:
			self.categoria_encerramento = None
			self.motivo_encerramento = None
		self._registrar(
			etapa=ETAPA_CAPTACAO,
			decisao=DECISAO_MUDANCA_DE_STATUS,
			user=user,
			status_anterior=status_anterior,
		)
		return True

	# ------------------------------------------------------------------
	# Apoio
	# ------------------------------------------------------------------

	def _exigir_status(self, *permitidos: str) -> None:
		if self.status not in permitidos:
			frappe.throw(
				_("Ação indisponível: o projeto está em {0}.").format(self.status),
				frappe.ValidationError,
			)

	def _encerrar(self, categoria: str, motivo: str) -> None:
		self.status = STATUS_CANCELADO
		self.categoria_encerramento = categoria
		self.motivo_encerramento = motivo

	@staticmethod
	def _etapa_do_status(status: str) -> str:
		return {
			STATUS_PRELIMINAR: ETAPA_APROVACAO_INICIAL,
			STATUS_APROVADO_INICIALMENTE: ETAPA_DETALHAMENTO,
			STATUS_EM_DETALHAMENTO: ETAPA_DETALHAMENTO,
			STATUS_REVISAO_TECNICA: ETAPA_REVISAO_TECNICA,
			STATUS_APROVACAO_FINAL: ETAPA_APROVACAO_FINAL,
		}.get(status, ETAPA_CAPTACAO)

	def _registrar(
		self,
		*,
		etapa: str,
		decisao: str,
		user: str,
		comentario: str = "",
		secao: str = "",
		status_anterior: str | None = None,
		resumo_alteracoes: str = "",
		resolvido: int = 1,
	) -> None:
		self.append(
			"decisoes",
			{
				"data": now_datetime(),
				"etapa": etapa,
				"decisao": decisao,
				"secao": secao or None,
				"status_anterior": self.status if status_anterior is None else status_anterior,
				"status_novo": self.status,
				"comentario": comentario or None,
				"resumo_alteracoes": resumo_alteracoes or None,
				"autor_user": user,
				"autor_nome": get_fullname(user),
				"resolvido": 1 if resolvido else 0,
			},
		)


def identificar_proponente(user: str) -> dict:
	"""Quem é `user` como proponente: o associado ou, na falta dele, o responsável.

	`{tipo, associado, responsavel, nome}`. Quem não tem cadastro de pessoa (um
	administrador, por exemplo) fica só com o nome do usuário.
	"""
	proponente = {"tipo": None, "associado": None, "responsavel": None, "nome": get_fullname(user)}
	chaves = pessoas_do_usuario(user)
	for doctype, campo in (
		(identidade.DOCTYPE_ASSOCIADO, "associado"),
		(identidade.DOCTYPE_RESPONSAVEL, "responsavel"),
	):
		for chave in chaves:
			tipo, name = identidade.separar(chave)
			if tipo == doctype:
				proponente.update(
					{
						"tipo": "Associado" if campo == "associado" else "Responsavel",
						campo: name,
						"nome": frappe.db.get_value(doctype, name, "nome_completo") or proponente["nome"],
					}
				)
				return proponente
	return proponente


def preencher_proponente(doc: Document, user: str) -> None:
	proponente = identificar_proponente(user)
	doc.proponente_user = user
	doc.proponente_tipo = proponente["tipo"]
	doc.proponente_associado = proponente["associado"]
	doc.proponente_responsavel = proponente["responsavel"]
	doc.proponente_nome = proponente["nome"]


def fotografar(doc: Document) -> dict:
	"""Valor comparável de cada parte do projeto, para achar o que uma edição mudou."""
	foto: dict = {}
	for campo in SECOES:
		if campo in CAMPOS_DAS_TABELAS:
			foto[campo] = [
				tuple(_normalizar(linha.get(coluna)) for coluna in CAMPOS_DAS_TABELAS[campo])
				for linha in doc.get(campo) or []
			]
		else:
			foto[campo] = _normalizar(doc.get(campo))
	return foto


def definir_tabela(doc: Document, campo: str, linhas: list[dict]) -> None:
	"""Troca as linhas de uma tabela só quando o conteúdo muda.

	Recriar linhas iguais gera nomes novos, e o `Version` registraria como alterada
	uma parte que ninguém tocou — o histórico passaria a mentir.
	"""
	colunas = CAMPOS_DAS_TABELAS[campo]
	atuais = [tuple(_normalizar(linha.get(coluna)) for coluna in colunas) for linha in doc.get(campo) or []]
	novas = [tuple(_normalizar(linha.get(coluna)) for coluna in colunas) for linha in linhas]
	if atuais != novas:
		doc.set(campo, linhas)


def _normalizar(valor):
	if valor is None:
		return ""
	if isinstance(valor, float | int):
		return flt(valor)
	return str(valor).strip()
