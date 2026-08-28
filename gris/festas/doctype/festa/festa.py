# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

import math
from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from gris.festas.utils.unidades import converter
from gris.utils.job_logger import definir_resumo, metrica, obter_logger

CENARIOS = ("min", "intermediario", "max")
AREA_PORTARIA_NOME = "Portaria"


class Festa(Document):
	def validate(self):
		self._garantir_status_padrao()
		self._cache_cenario_antes()
		self._normalizar_coordenador_geral()
		self._validar_coordenador_geral()
		self._preencher_dados_coordenador_geral()
		self._validar_data_limite_vendas()
		self._validar_portaria_completa()
		self._sincronizar_receitas_e_despesas()
		self._sincronizar_receitas_e_despesas_barraca()
		self._calcular_precos_convite()
		self._validar_lotes_convite()
		self._calcular_totais_financeiros()
		self._gerar_lista_de_compras()

	def after_insert(self):
		_ensure_festa_board(self)
		_garantir_area_portaria(self.name)
		_enqueue_festa_drive_folder_creation(self.name)

	def on_trash(self):
		_excluir_dependencias_da_festa(self)
		_desvincular_board_da_festa(self)

	def on_update(self):
		if getattr(self, "_cenario_antes", None) != (self.cenario_simulacao or "Intermediário"):
			_enqueue_recalcular_compras(self.name)

	# ---------- Cenario ----------

	def _cache_cenario_antes(self):
		if self.is_new():
			self._cenario_antes = self.cenario_simulacao or "Intermediário"
			return
		self._cenario_antes = frappe.db.get_value("Festa", self.name, "cenario_simulacao") or "Intermediário"

	# ---------- Status ----------

	def _garantir_status_padrao(self):
		if not self.status:
			self.status = "Em andamento"

	# ---------- Coordenador Geral ----------

	def _normalizar_coordenador_geral(self):
		if self.tipo_coord_geral == "Associado":
			self.responsavel_coord_geral = None
		elif self.tipo_coord_geral == "Responsavel":
			self.associado_coord_geral = None

	def _validar_coordenador_geral(self):
		if self.tipo_coord_geral != "Associado" or not self.associado_coord_geral:
			return

		nascimento = frappe.db.get_value("Associado", self.associado_coord_geral, "data_de_nascimento")
		if not nascimento:
			frappe.throw(_("Associado selecionado nao possui data de nascimento cadastrada."))

		referencia = self.data or date.today()
		_calcular_idade(getdate(nascimento), getdate(referencia))

	def _preencher_dados_coordenador_geral(self):
		"""Persiste nome/email/telefone do coordenador geral a partir do link selecionado.

		Os campos `nome_coord_geral`, `email_coord_geral` e `telefone_coord_geral`
		são read-only e usados pela página de portal; precisam ser materializados
		aqui para sobreviverem ao recarregamento da página.
		"""
		nome = email = telefone = ""

		if self.tipo_coord_geral == "Responsavel" and self.responsavel_coord_geral:
			dados = frappe.db.get_value(
				"Responsavel",
				self.responsavel_coord_geral,
				["nome_completo", "email", "celular"],
				as_dict=True,
			)
			if dados:
				nome, email, telefone = dados.nome_completo, dados.email, dados.celular
		elif self.tipo_coord_geral == "Associado" and self.associado_coord_geral:
			dados = frappe.db.get_value(
				"Associado",
				self.associado_coord_geral,
				["nome_completo", "email", "telefone"],
				as_dict=True,
			)
			if dados:
				nome, email, telefone = dados.nome_completo, dados.email, dados.telefone

		self.nome_coord_geral = nome or ""
		self.email_coord_geral = email or ""
		self.telefone_coord_geral = telefone or ""

	# ---------- Data limite de vendas ----------

	def _validar_data_limite_vendas(self):
		if not self.data_limite_vendas:
			return
		if self.data and getdate(self.data_limite_vendas) > getdate(self.data):
			frappe.throw(_("A data limite de vendas não pode ser posterior à data da festa."))

	# ---------- Portaria obrigatória ----------

	def _validar_portaria_completa(self):
		if self.is_new():
			return
		nome_doc = f"{self.name} - {AREA_PORTARIA_NOME}"
		portaria = frappe.db.get_value(
			"Area da Festa",
			nome_doc,
			[
				"tipo_coord",
				"responsavel_coord",
				"associado_coord",
				"nome_coord",
				"email_coord",
				"telefone_coord",
			],
			as_dict=True,
		)
		if not portaria:
			frappe.throw(_("A área Portaria é obrigatória e ainda não foi criada para esta festa."))

		if portaria.tipo_coord == "Responsavel" and not portaria.responsavel_coord:
			frappe.throw(_("A área Portaria precisa de um coordenador responsável."))
		if portaria.tipo_coord == "Associado" and not portaria.associado_coord:
			frappe.throw(_("A área Portaria precisa de um coordenador associado."))
		if portaria.tipo_coord == "Outro" and not (
			portaria.nome_coord and portaria.email_coord and portaria.telefone_coord
		):
			frappe.throw(_("A área Portaria precisa de coordenador com nome, e-mail e telefone preenchidos."))

	# ---------- Receitas / Despesas por area ----------

	def _sincronizar_receitas_e_despesas(self):
		if self.is_new():
			return

		areas = frappe.get_all(
			"Area da Festa",
			filters={"festa": self.name},
			fields=["name", "nome_area"],
			order_by="creation",
		)
		nomes_areas = [a.name for a in areas]

		barracas = frappe.get_all(
			"Barraca da Festa",
			filters={"festa": self.name},
			fields=["name", "area"],
		)
		barraca_to_area = {b.name: b.area for b in barracas}

		produtos = frappe.get_all(
			"Produto de Venda Festa",
			filters={"festa": self.name},
			fields=[
				"name",
				"barraca",
				"faz_parte_convite",
				"preco_venda",
				"receita_total_min",
				"receita_total_intermediario",
				"receita_total_max",
			],
		)
		compras = frappe.get_all(
			"Compra Festa",
			filters={"festa": self.name},
			fields=[
				"name",
				"area",
				"valor_total_min",
				"valor_total_intermediario",
				"valor_total_max",
			],
		)
		contratacoes = frappe.get_all(
			"Contratacao Festa",
			filters={"festa": self.name},
			fields=["name", "area", "valor_total_contratacao"],
		)

		receitas = {a: _zeros() for a in nomes_areas}
		despesas = {a: _zeros() for a in nomes_areas}

		publico_min = flt(self.expectativa_publico_min)
		publico_inter = flt(self.expectativa_publico_intermediario)
		publico_max = flt(self.expectativa_publico_max)

		for p in produtos:
			area = barraca_to_area.get(p.barraca)
			if area not in receitas:
				continue
			ajuste = flt(p.preco_venda) if p.faz_parte_convite else 0.0
			receitas[area]["min"] += flt(p.receita_total_min) - ajuste * publico_min
			receitas[area]["intermediario"] += flt(p.receita_total_intermediario) - ajuste * publico_inter
			receitas[area]["max"] += flt(p.receita_total_max) - ajuste * publico_max

		for c in compras:
			if c.area not in despesas:
				continue
			despesas[c.area]["min"] += flt(c.valor_total_min)
			despesas[c.area]["intermediario"] += flt(c.valor_total_intermediario)
			despesas[c.area]["max"] += flt(c.valor_total_max)

		for ct in contratacoes:
			if ct.area not in despesas:
				continue
			valor = flt(ct.valor_total_contratacao)
			despesas[ct.area]["min"] += valor
			despesas[ct.area]["intermediario"] += valor
			despesas[ct.area]["max"] += valor

		# Preserva valores realizados existentes
		receitas_existentes = {r.area: r for r in self.receitas_por_area or []}
		despesas_existentes = {d.area: d for d in self.despesas_por_area or []}

		self.receitas_por_area = []
		self.despesas_por_area = []

		for nome_area in nomes_areas:
			existente = receitas_existentes.get(nome_area)
			self.append(
				"receitas_por_area",
				{
					"area": nome_area,
					"esperado_min": receitas[nome_area]["min"],
					"esperado_intermediario": receitas[nome_area]["intermediario"],
					"esperado_max": receitas[nome_area]["max"],
					"realizado_min": existente.realizado_min if existente else 0,
					"realizado_intermediario": existente.realizado_intermediario if existente else 0,
					"realizado_max": existente.realizado_max if existente else 0,
				},
			)
			existente_d = despesas_existentes.get(nome_area)
			self.append(
				"despesas_por_area",
				{
					"area": nome_area,
					"esperado_min": despesas[nome_area]["min"],
					"esperado_intermediario": despesas[nome_area]["intermediario"],
					"esperado_max": despesas[nome_area]["max"],
					"realizado_min": existente_d.realizado_min if existente_d else 0,
					"realizado_intermediario": existente_d.realizado_intermediario if existente_d else 0,
					"realizado_max": existente_d.realizado_max if existente_d else 0,
				},
			)

	# ---------- Receitas / Despesas por barraca ----------

	def _sincronizar_receitas_e_despesas_barraca(self):
		if self.is_new():
			return

		barracas = frappe.get_all(
			"Barraca da Festa",
			filters={"festa": self.name},
			fields=["name"],
			order_by="creation",
		)
		# Barraca em processo de exclusão: ignora para não recriar as linhas de
		# orçamento que a referenciam (evita LinkExistsError no on_trash).
		ignorar_barraca = self.flags.get("ignorar_barraca")
		nomes_barracas = [b.name for b in barracas if b.name != ignorar_barraca]

		produtos = frappe.get_all(
			"Produto de Venda Festa",
			filters={"festa": self.name},
			fields=[
				"name",
				"barraca",
				"faz_parte_convite",
				"preco_venda",
				"receita_total_min",
				"receita_total_intermediario",
				"receita_total_max",
				"custo_total_min",
				"custo_total_intermediario",
				"custo_total_max",
			],
		)

		receitas = {b: _zeros() for b in nomes_barracas}
		despesas = {b: _zeros() for b in nomes_barracas}

		publico_min = flt(self.expectativa_publico_min)
		publico_inter = flt(self.expectativa_publico_intermediario)
		publico_max = flt(self.expectativa_publico_max)

		for p in produtos:
			if p.barraca not in receitas:
				continue
			ajuste = flt(p.preco_venda) if p.faz_parte_convite else 0.0
			receitas[p.barraca]["min"] += flt(p.receita_total_min) - ajuste * publico_min
			receitas[p.barraca]["intermediario"] += (
				flt(p.receita_total_intermediario) - ajuste * publico_inter
			)
			receitas[p.barraca]["max"] += flt(p.receita_total_max) - ajuste * publico_max
			despesas[p.barraca]["min"] += flt(p.custo_total_min)
			despesas[p.barraca]["intermediario"] += flt(p.custo_total_intermediario)
			despesas[p.barraca]["max"] += flt(p.custo_total_max)

		receitas_existentes = {r.barraca: r for r in self.receitas_por_barraca or []}
		despesas_existentes = {d.barraca: d for d in self.despesas_por_barraca or []}

		self.receitas_por_barraca = []
		self.despesas_por_barraca = []

		for nome_barraca in nomes_barracas:
			existente = receitas_existentes.get(nome_barraca)
			self.append(
				"receitas_por_barraca",
				{
					"barraca": nome_barraca,
					"esperado_min": receitas[nome_barraca]["min"],
					"esperado_intermediario": receitas[nome_barraca]["intermediario"],
					"esperado_max": receitas[nome_barraca]["max"],
					"realizado_min": existente.realizado_min if existente else 0,
					"realizado_intermediario": existente.realizado_intermediario if existente else 0,
					"realizado_max": existente.realizado_max if existente else 0,
				},
			)
			existente_d = despesas_existentes.get(nome_barraca)
			self.append(
				"despesas_por_barraca",
				{
					"barraca": nome_barraca,
					"esperado_min": despesas[nome_barraca]["min"],
					"esperado_intermediario": despesas[nome_barraca]["intermediario"],
					"esperado_max": despesas[nome_barraca]["max"],
					"realizado_min": existente_d.realizado_min if existente_d else 0,
					"realizado_intermediario": existente_d.realizado_intermediario if existente_d else 0,
					"realizado_max": existente_d.realizado_max if existente_d else 0,
				},
			)

	# ---------- Precos do convite ----------

	def _calcular_precos_convite(self):
		if self.is_new():
			self.preco_min_convite = 0
			self.preco_sugerido_convite = 0
			return

		produtos = frappe.get_all(
			"Produto de Venda Festa",
			filters={"festa": self.name, "faz_parte_convite": 1},
			fields=["preco_custo", "preco_venda", "qtd_no_convite"],
		)
		self.preco_min_convite = sum(flt(p.preco_custo) * (flt(p.qtd_no_convite) or 1) for p in produtos)
		self.preco_sugerido_convite = sum(flt(p.preco_venda) * (flt(p.qtd_no_convite) or 1) for p in produtos)

	# ---------- Lotes de convite (planejamento) ----------

	def _validar_lotes_convite(self):
		if not self.convite_por_lotes:
			return
		if not self.lotes_convite:
			frappe.throw(_("Cadastre ao menos um lote de convite ou desligue 'Convite por lotes'."))
		total_pct = sum(flt(lote.expectativa_percentual) for lote in self.lotes_convite)
		# Tolerância para arredondamento de percentuais.
		if abs(total_pct - 100.0) > 0.01:
			frappe.throw(
				_("A soma das expectativas de vendas dos lotes deve ser 100% (atual: {0}%).").format(
					flt(total_pct, 2)
				)
			)
		for lote in self.lotes_convite:
			if flt(lote.valor_consumacao) > flt(lote.valor_convite):
				frappe.throw(_("O valor de consumação de um lote não pode ser maior que o valor do convite."))

	def _preco_medio_convite_por_lotes(self) -> float:
		"""Preço médio ponderado do convite pela expectativa de vendas de cada lote."""
		total_pct = sum(flt(lote.expectativa_percentual) for lote in self.lotes_convite or [])
		if total_pct <= 0:
			return 0.0
		soma = sum(
			flt(lote.valor_convite) * flt(lote.expectativa_percentual) for lote in self.lotes_convite or []
		)
		return soma / total_pct

	def _consumacao_media_convite_por_lotes(self) -> float:
		"""Consumação média ponderada do convite pela expectativa de vendas de cada lote."""
		total_pct = sum(flt(lote.expectativa_percentual) for lote in self.lotes_convite or [])
		if total_pct <= 0:
			return 0.0
		soma = sum(
			flt(lote.valor_consumacao) * flt(lote.expectativa_percentual) for lote in self.lotes_convite or []
		)
		return soma / total_pct

	# ---------- Totais por cenario ----------

	def _calcular_totais_financeiros(self):
		margem_decimal = flt(self.margem_seguranca) / 100.0
		if self.convite_por_lotes:
			preco_convite = self._preco_medio_convite_por_lotes()
		else:
			preco_convite = flt(self.preco_convite)

		for chave in CENARIOS:
			receita_produtos = sum(flt(r.get(f"esperado_{chave}")) for r in self.receitas_por_area or [])
			despesa_area = sum(flt(d.get(f"esperado_{chave}")) for d in self.despesas_por_area or [])
			publico = flt(self.get(f"expectativa_publico_{chave}"))
			receita_convite = preco_convite * publico
			receita_total = receita_produtos + receita_convite

			margem_valor = despesa_area * margem_decimal

			self.set(f"margem_seg_valor_{chave}", margem_valor)
			self.set(f"receita_produtos_{chave}", receita_produtos)
			self.set(f"receita_convite_{chave}", receita_convite)
			self.set(f"receita_total_{chave}", receita_total)
			self.set(f"despesa_total_{chave}", despesa_area + margem_valor)

	# ---------- Lista de compras ----------

	def _gerar_lista_de_compras(self):
		self.lista_compras = []
		if self.is_new():
			return

		compras = frappe.get_all(
			"Compra Festa",
			filters={"festa": self.name},
			fields=["name", "nome_item", "unidade_compra", "quantidade_compra_final"],
		)
		if not compras:
			return

		nomes = [c.name for c in compras]
		cotacoes_escolhidas = frappe.get_all(
			"Cotacao Compra Festa",
			filters={"parent": ("in", nomes), "escolhida": 1, "doacao": 0},
			fields=["parent", "valor", "quantidade", "unidade_medida", "fornecedor"],
		)
		cot_por_compra = {c.parent: c for c in cotacoes_escolhidas}

		agregadas: dict[tuple[str, str, str], dict] = {}
		for compra in compras:
			cot = cot_por_compra.get(compra.name)
			if not cot:
				continue
			try:
				qtd_cot_em_compra = converter(flt(cot.quantidade), cot.unidade_medida, compra.unidade_compra)
			except Exception:
				continue
			if qtd_cot_em_compra <= 0:
				continue

			valor_unit = flt(cot.valor) / qtd_cot_em_compra
			qtd_arredondada = math.ceil(flt(compra.quantidade_compra_final) or 0)

			key = (compra.nome_item or "", cot.fornecedor or "", compra.unidade_compra or "")
			if key not in agregadas:
				agregadas[key] = {
					"item": compra.nome_item,
					"fornecedor": cot.fornecedor,
					"unidade": compra.unidade_compra,
					"quantidade": 0,
					"valor_unitario": valor_unit,
					"valor_total": 0.0,
				}
			agregadas[key]["quantidade"] += qtd_arredondada

		for entry in agregadas.values():
			entry["valor_total"] = entry["quantidade"] * entry["valor_unitario"]
			self.append("lista_compras", entry)


# ---------- Helpers ----------


def _calcular_idade(nascimento: date, referencia: date) -> int:
	anos = referencia.year - nascimento.year
	if (referencia.month, referencia.day) < (nascimento.month, nascimento.day):
		anos -= 1
	return anos


def _zeros() -> dict[str, float]:
	return {"min": 0.0, "intermediario": 0.0, "max": 0.0}


def _ensure_festa_board(doc: Document) -> None:
	"""Cria automaticamente o Board de tarefas vinculado a festa recem-criada.

	Usa ignore_permissions porque after_insert pode ser disparado em fluxos
	(portal, importacao) em que o usuario nao tem permissao direta de criar
	Board, mas tem permissao para criar Festa. O Board.before_insert ja
	popula `usuarios_autorizados` com o coordenador geral da festa.
	"""
	if doc.get("board_tarefas"):
		return

	board = frappe.get_doc(
		{
			"doctype": "Board",
			"titulo": f"Tarefas — {doc.nome_festa or doc.name}",
			"referencia_doctype": "Festa",
			"referencia_nome": doc.name,
		}
	).insert(ignore_permissions=True)

	frappe.db.set_value("Festa", doc.name, "board_tarefas", board.name, update_modified=False)
	doc.board_tarefas = board.name


def _excluir_dependencias_da_festa(doc: Document) -> None:
	delete_plan = (
		("Lista Entrada Festa", None),
		("Convite Festa", None),
		("Opcao Convite Festa", None),
		("Compra Festa", None),
		("Contratacao Festa", None),
		("Produto de Venda Festa", None),
		("Barraca da Festa", None),
		("Avaliacao Festa", None),
		("Area da Festa", {"from_festa_delete": True}),
	)

	for doctype, flags in delete_plan:
		nomes = frappe.get_all(
			doctype,
			filters={"festa": doc.name},
			pluck="name",
			order_by="creation desc",
		)
		for nome in nomes:
			frappe.delete_doc(doctype, nome, ignore_permissions=True, flags=flags)


def _desvincular_board_da_festa(doc: Document) -> None:
	board_names: list[str] = []
	if doc.get("board_tarefas"):
		board_names.append(doc.board_tarefas)

	board_names.extend(
		nome
		for nome in frappe.get_all(
			"Board",
			filters={"referencia_doctype": "Festa", "referencia_nome": doc.name},
			pluck="name",
		)
		if nome not in board_names
	)

	for board_name in board_names:
		frappe.db.set_value(
			"Board",
			board_name,
			{"referencia_doctype": "", "referencia_nome": ""},
			update_modified=False,
		)


def _garantir_area_portaria(festa_name: str) -> None:
	if not festa_name:
		return
	nome_doc = f"{festa_name} - {AREA_PORTARIA_NOME}"
	if frappe.db.exists("Area da Festa", nome_doc):
		return
	doc = frappe.new_doc("Area da Festa")
	doc.festa = festa_name
	doc.nome_area = AREA_PORTARIA_NOME
	doc.descricao = "Area da portaria. Recebe a arrecadacao dos convites."
	doc.tipo_coord = "Outro"
	doc.flags.in_portaria_auto_create = True
	doc.insert(ignore_permissions=True)


def _enqueue_festa_drive_folder_creation(festa_name: str) -> None:
	if not festa_name:
		return

	try:
		frappe.enqueue(
			method="gris.api.google_workspace.festa_drive.create_festa_folder_async",
			queue="long",
			timeout=300,
			enqueue_after_commit=True,
			festa_name=festa_name,
		)
	except Exception:
		frappe.log_error(
			message=frappe.get_traceback(),
			title="Falha ao enfileirar criacao de pasta da festa no Google Drive",
		)


def _enqueue_recalcular_compras(festa_name: str) -> None:
	"""Enfileira o recálculo de todos os CompraFesta quando o cenário da Festa muda."""
	compras = frappe.get_all(
		"Compra Festa",
		filters={"festa": festa_name},
		fields=["name"],
	)
	for compra in compras:
		try:
			frappe.enqueue(
				method="gris.festas.doctype.festa.festa._recalcular_compra",
				queue="default",
				timeout=120,
				enqueue_after_commit=True,
				compra_name=compra.name,
			)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Falha ao enfileirar recálculo de CompraFesta: {compra.name}",
			)


def _recalcular_compra(compra_name: str) -> None:
	"""Job de background: salva um CompraFesta para recalcular cenários."""
	try:
		doc = frappe.get_doc("Compra Festa", compra_name)
		doc.save(ignore_permissions=True)
	except frappe.DoesNotExistError:
		pass


def marcar_festas_realizadas() -> dict[str, int]:
	"""Job diario: festas com data passada e status 'Em andamento' viram 'Realizada'."""
	logger = obter_logger("festas")
	hoje = getdate()
	pendentes = frappe.get_all(
		"Festa",
		filters={"status": "Em andamento", "data": ["<", hoje]},
		fields=["name", "data"],
	)
	if not pendentes:
		logger.info(f"Nenhuma festa em andamento com data anterior a {hoje}.")
		definir_resumo("Nenhuma festa a marcar como realizada.")
		return {"atualizadas": 0}

	for festa in pendentes:
		frappe.db.set_value("Festa", festa.name, "status", "Realizada", update_modified=False)
		logger.info(f"Festa {festa.name} ({festa.data}) marcada como Realizada.")

	metrica("atualizadas", len(pendentes), incrementar=False)
	definir_resumo(f"{len(pendentes)} festa(s) marcada(s) como realizada(s).")
	return {"atualizadas": len(pendentes)}
