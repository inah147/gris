from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt

from gris.festas.doctype.festa.festa import AREA_PORTARIA_NOME
from gris.festas.utils.unidades import UNIDADES

ALLOWED_ROLES = {"Gestor de festas", "System Manager"}


def _ensure_gestor() -> None:
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & ALLOWED_ROLES):
		frappe.throw(_("Permissão negada."), frappe.PermissionError)


def _validate_festa(festa_name: str) -> None:
	if not frappe.db.exists("Festa", festa_name):
		frappe.throw(_("Festa não encontrada."), frappe.DoesNotExistError)


def _validate_tipo_coord(tipo: str) -> None:
	if tipo not in {"Responsavel", "Associado", "Outro"}:
		frappe.throw(_("Tipo de coordenador inválido."))


def _associado_email(name: str) -> str:
	"""E-mail preferencial do associado: usa o id@escoteiros quando preenchido,
	senão cai para o e-mail comum."""
	dados = frappe.db.get_value("Associado", name, ["id_escoteiros", "email"], as_dict=True) or {}
	return (dados.get("id_escoteiros") or dados.get("email") or "").strip()


# ---------------------------------------------------------------------------
# Coordenador da festa
# ---------------------------------------------------------------------------


@frappe.whitelist()
def update_coordenador(festa_name: str, tipo_coord: str, coordenador: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)
	_validate_tipo_coord(tipo_coord)

	coordenador = coordenador.strip()
	if not coordenador:
		frappe.throw(_("Informe o coordenador."))

	doc = frappe.get_doc("Festa", festa_name)

	if tipo_coord == "Responsavel":
		if not frappe.db.exists("Responsavel", coordenador):
			frappe.throw(_("Responsável não encontrado."))
		doc.tipo_coord_geral = "Responsavel"
		doc.responsavel_coord_geral = coordenador
		doc.associado_coord_geral = None
	else:
		if not frappe.db.exists("Associado", coordenador):
			frappe.throw(_("Associado não encontrado."))
		doc.tipo_coord_geral = "Associado"
		doc.associado_coord_geral = coordenador
		doc.responsavel_coord_geral = None

	doc.save()
	nome_coord = frappe.db.get_value(tipo_coord, coordenador, "nome_completo") or coordenador
	return {"ok": True, "nome_coord": nome_coord}


# ---------------------------------------------------------------------------
# Estimativas de participantes
# ---------------------------------------------------------------------------


@frappe.whitelist()
def update_estimativas(festa_name: str, min_val: str, intermediario_val: str, max_val: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)

	try:
		v_min = int(min_val)
		v_int = int(intermediario_val)
		v_max = int(max_val)
	except (ValueError, TypeError):
		frappe.throw(_("Os valores devem ser números inteiros."))

	if v_min < 0 or v_int < 0 or v_max < 0:
		frappe.throw(_("Os valores devem ser não-negativos."))

	frappe.db.set_value(
		"Festa",
		festa_name,
		{
			"expectativa_publico_min": v_min,
			"expectativa_publico_intermediario": v_int,
			"expectativa_publico_max": v_max,
		},
	)
	return {"ok": True}


# ---------------------------------------------------------------------------
# Cenário para simulação
# ---------------------------------------------------------------------------

_CENARIOS_VALIDOS = {"Mínimo", "Intermediário", "Máximo"}


@frappe.whitelist()
def update_cenario_simulacao(festa_name: str, cenario: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)

	if cenario not in _CENARIOS_VALIDOS:
		frappe.throw(_("Cenário inválido."))

	frappe.db.set_value("Festa", festa_name, "cenario_simulacao", cenario)
	return {"ok": True}


# ---------------------------------------------------------------------------
# Preço do convite e totais financeiros
# ---------------------------------------------------------------------------


_CENARIOS_KEYS = ("min", "intermediario", "max")


def totais_payload(doc) -> dict:
	"""Retorna receita/despesa/margem/saldo por cenário a partir do doc Festa.

	A receita de convites é segmentada em entrada e consumação usando a
	expectativa de vendas de cada lote (consumação média ponderada x público).
	A receita de produtos considera apenas o excedente sobre a consumação (ou a
	própria consumação, o que for maior), evitando contá-la duas vezes — mesma
	lógica de resultado aplicada no fechamento.
	"""
	consumacao_media = doc._consumacao_media_convite_por_lotes() if doc.convite_por_lotes else 0.0
	payload = {}
	for chave in _CENARIOS_KEYS:
		receita_convite = flt(doc.get(f"receita_convite_{chave}"))
		receita_produtos = flt(doc.get(f"receita_produtos_{chave}"))
		publico = flt(doc.get(f"expectativa_publico_{chave}"))
		consumacao = consumacao_media * publico
		entrada = receita_convite - consumacao
		receita_produtos_ajustada = max(consumacao, receita_produtos - consumacao)
		receita = entrada + consumacao + receita_produtos_ajustada
		despesa = flt(doc.get(f"despesa_total_{chave}"))
		margem = flt(doc.get(f"margem_seg_valor_{chave}"))
		payload[chave] = {
			"receita_convite": receita_convite,
			"receita_entrada": entrada,
			"receita_consumacao": consumacao,
			"receita_produtos": receita_produtos_ajustada,
			"receita": receita,
			"despesa": despesa,
			"margem": margem,
			"saldo": receita - despesa,
		}
	return payload


@frappe.whitelist()
def update_margem_seguranca(festa_name: str, margem: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)

	try:
		valor = flt(margem)
	except (ValueError, TypeError):
		frappe.throw(_("Valor da margem inválido."))

	if valor < 0 or valor > 100:
		frappe.throw(_("A margem de segurança deve estar entre 0 e 100."))

	doc = frappe.get_doc("Festa", festa_name)
	doc.margem_seguranca = valor
	doc.save()

	return {
		"ok": True,
		"margem_seguranca": flt(doc.margem_seguranca),
		"totais": totais_payload(doc),
	}


@frappe.whitelist()
def update_preco_convite(festa_name: str, preco: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)

	try:
		valor = flt(preco)
	except (ValueError, TypeError):
		frappe.throw(_("Valor do preço inválido."))

	if valor < 0:
		frappe.throw(_("O preço do convite deve ser não-negativo."))

	doc = frappe.get_doc("Festa", festa_name)
	doc.preco_convite = valor
	doc.save()

	return {
		"ok": True,
		"preco_convite": flt(doc.preco_convite),
		"preco_min_convite": flt(doc.preco_min_convite),
		"preco_sugerido_convite": flt(doc.preco_sugerido_convite),
		"totais": totais_payload(doc),
	}


def _parse_lotes_convite(raw) -> list[dict]:
	"""Normaliza os lotes de planejamento (Lote Convite Festa) do cliente."""
	if raw in (None, ""):
		return []
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except (ValueError, TypeError):
			frappe.throw(_("Lotes inválidos."))
	if not isinstance(raw, list):
		frappe.throw(_("Lotes inválidos."))

	lotes: list[dict] = []
	for item in raw:
		if not isinstance(item, dict):
			frappe.throw(_("Lote inválido."))
		valor_convite = _as_non_negative_float(item.get("valor_convite", 0), "Valor do convite")
		valor_consumacao = _as_non_negative_float(item.get("valor_consumacao", 0), "Valor de consumação")
		expectativa = _as_non_negative_float(item.get("expectativa_percentual", 0), "Expectativa de vendas")
		lotes.append(
			{
				"nome_lote": (item.get("nome_lote") or "").strip(),
				"valor_convite": valor_convite,
				"valor_consumacao": valor_consumacao,
				"expectativa_percentual": expectativa,
			}
		)
	return lotes


@frappe.whitelist()
def update_lotes_convite(festa_name: str, convite_por_lotes, lotes=None) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)

	ligado = 1 if convite_por_lotes in ("1", "true", "True", True, 1) else 0

	doc = frappe.get_doc("Festa", festa_name)
	doc.convite_por_lotes = ligado
	doc.set("lotes_convite", _parse_lotes_convite(lotes) if ligado else [])
	doc.save()  # validate() garante a soma de 100% quando ligado.

	return {
		"ok": True,
		"convite_por_lotes": bool(doc.convite_por_lotes),
		"lotes_convite": [
			{
				"nome_lote": lote.nome_lote or "",
				"valor_convite": flt(lote.valor_convite),
				"valor_consumacao": flt(lote.valor_consumacao),
				"expectativa_percentual": flt(lote.expectativa_percentual),
			}
			for lote in (doc.lotes_convite or [])
		],
		"totais": totais_payload(doc),
	}


@frappe.whitelist()
def salvar_fechamento_caixa(festa_name: str, valor) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)

	valor_arrecadado = _as_non_negative_float(valor, "Valor arrecadado na festa")
	frappe.db.set_value("Festa", festa_name, "valor_arrecadado_festa", valor_arrecadado)

	return {"ok": True, "valor_arrecadado_festa": valor_arrecadado}


# ---------------------------------------------------------------------------
# Áreas da festa
# ---------------------------------------------------------------------------


@frappe.whitelist()
def criar_area(festa_name: str, nome_area: str, descricao: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)

	nome_area = nome_area.strip()
	if not nome_area:
		frappe.throw(_("Informe o nome da área."))

	doc = frappe.new_doc("Area da Festa")
	doc.festa = festa_name
	doc.nome_area = nome_area
	doc.descricao = descricao.strip()
	doc.tipo_coord = "Outro"
	doc.nome_coord = ""
	doc.email_coord = ""
	doc.telefone_coord = ""
	doc.insert()
	return {"ok": True, "name": doc.name, "nome_area": doc.nome_area, "nome_coord": doc.nome_coord}


@frappe.whitelist()
def salvar_area(area_name: str, dados_json: str) -> dict:
	_ensure_gestor()

	try:
		dados = json.loads(dados_json) if isinstance(dados_json, str) else dados_json
	except (ValueError, TypeError):
		frappe.throw(_("Dados inválidos."))

	if not isinstance(dados, dict):
		frappe.throw(_("Dados inválidos."))

	doc = frappe.get_doc("Area da Festa", area_name)

	nome = (dados.get("nome_area") or "").strip()
	if not nome:
		frappe.throw(_("Informe o nome da área."))
	doc.nome_area = nome
	doc.descricao = (dados.get("descricao") or "").strip()

	tipo_coord = (dados.get("tipo_coord") or "Outro").strip()
	_validate_tipo_coord(tipo_coord)
	doc.tipo_coord = tipo_coord

	if tipo_coord == "Responsavel":
		coord = (dados.get("coordenador") or "").strip()
		if not frappe.db.exists("Responsavel", coord):
			frappe.throw(_("Responsável não encontrado."))
		doc.responsavel_coord = coord
		doc.associado_coord = None
		nome_coord = frappe.db.get_value("Responsavel", coord, "nome_completo") or coord
		doc.nome_coord = nome_coord
		doc.email_coord = frappe.db.get_value("Responsavel", coord, "email") or ""
		doc.telefone_coord = frappe.db.get_value("Responsavel", coord, "celular") or ""
	elif tipo_coord == "Associado":
		coord = (dados.get("coordenador") or "").strip()
		if not frappe.db.exists("Associado", coord):
			frappe.throw(_("Associado não encontrado."))
		doc.associado_coord = coord
		doc.responsavel_coord = None
		nome_coord = frappe.db.get_value("Associado", coord, "nome_completo") or coord
		doc.nome_coord = nome_coord
		doc.email_coord = _associado_email(coord)
		doc.telefone_coord = frappe.db.get_value("Associado", coord, "telefone") or ""
	else:
		doc.responsavel_coord = None
		doc.associado_coord = None
		doc.nome_coord = (dados.get("nome_coord") or "").strip()
		doc.email_coord = (dados.get("email_coord") or "").strip()
		doc.telefone_coord = (dados.get("telefone_coord") or "").strip()

	equipe_raw = dados.get("equipe") or []
	doc.equipe = []
	for row in equipe_raw:
		tipo_pessoa = (row.get("tipo_pessoa") or "Outro").strip()
		if tipo_pessoa not in {"Associado", "Responsavel", "Outro"}:
			tipo_pessoa = "Outro"
		entry = {
			"tipo_pessoa": tipo_pessoa,
			"nome": (row.get("nome") or "").strip(),
			"email": (row.get("email") or "").strip(),
			"telefone": (row.get("telefone") or "").strip(),
			"funcao": (row.get("funcao") or "").strip(),
		}
		if tipo_pessoa == "Associado":
			entry["associado"] = (row.get("associado") or "").strip() or None
			entry["responsavel"] = None
			if entry["associado"]:
				# Resolve no servidor para garantir o id@escoteiros quando houver,
				# em vez de confiar no e-mail enviado pelo client.
				entry["email"] = _associado_email(entry["associado"]) or entry["email"]
		elif tipo_pessoa == "Responsavel":
			entry["responsavel"] = (row.get("responsavel") or "").strip() or None
			entry["associado"] = None
		else:
			entry["associado"] = None
			entry["responsavel"] = None

		if not entry["nome"]:
			frappe.throw(_("Todo membro da equipe deve ter nome."))

		doc.append("equipe", entry)

	doc.save()
	return {"ok": True, "nome_coord": doc.nome_coord}


@frappe.whitelist()
def excluir_area(area_name: str, festa_name: str) -> dict:
	_ensure_gestor()

	doc = frappe.get_doc("Area da Festa", area_name)
	if doc.festa != festa_name:
		frappe.throw(_("Área não pertence a esta festa."))
	if doc.nome_area == AREA_PORTARIA_NOME:
		frappe.throw(f"A área {AREA_PORTARIA_NOME} é obrigatória e não pode ser excluída.")

	frappe.delete_doc("Area da Festa", area_name)
	return {"ok": True}


# ---------------------------------------------------------------------------
# Barracas da festa
# ---------------------------------------------------------------------------


@frappe.whitelist()
def criar_barraca(festa_name: str, nome_barraca: str, descricao: str, area: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)

	nome_barraca = nome_barraca.strip()
	if not nome_barraca:
		frappe.throw(_("Informe o nome da barraca."))

	area_validada = _validate_area_festa(area, festa_name)
	if not area_validada:
		frappe.throw(_("Selecione a área da barraca."))

	doc = frappe.new_doc("Barraca da Festa")
	doc.festa = festa_name
	doc.area = area_validada
	doc.nome_barraca = nome_barraca
	doc.descricao = descricao.strip()
	doc.tipo_coord = "Outro"
	doc.nome_coord = ""
	doc.email_coord = ""
	doc.telefone_coord = ""
	doc.insert()
	nome_area = frappe.db.get_value("Area da Festa", doc.area, "nome_area") or ""
	return {
		"ok": True,
		"name": doc.name,
		"nome_barraca": doc.nome_barraca,
		"nome_coord": doc.nome_coord,
		"area": doc.area,
		"nome_area": nome_area,
	}


@frappe.whitelist()
def salvar_barraca(barraca_name: str, dados_json: str) -> dict:
	_ensure_gestor()

	try:
		dados = json.loads(dados_json) if isinstance(dados_json, str) else dados_json
	except (ValueError, TypeError):
		frappe.throw(_("Dados inválidos."))

	if not isinstance(dados, dict):
		frappe.throw(_("Dados inválidos."))

	doc = frappe.get_doc("Barraca da Festa", barraca_name)

	nome = (dados.get("nome_barraca") or "").strip()
	if not nome:
		frappe.throw(_("Informe o nome da barraca."))
	doc.nome_barraca = nome
	doc.descricao = (dados.get("descricao") or "").strip()

	area_validada = _validate_area_festa(dados.get("area"), doc.festa)
	if not area_validada:
		frappe.throw(_("Selecione a área da barraca."))
	doc.area = area_validada

	tipo_coord = (dados.get("tipo_coord") or "Outro").strip()
	_validate_tipo_coord(tipo_coord)
	doc.tipo_coord = tipo_coord

	if tipo_coord == "Responsavel":
		coord = (dados.get("coordenador") or "").strip()
		if not frappe.db.exists("Responsavel", coord):
			frappe.throw(_("Responsável não encontrado."))
		doc.responsavel_coord = coord
		doc.associado_coord = None
		nome_coord = frappe.db.get_value("Responsavel", coord, "nome_completo") or coord
		doc.nome_coord = nome_coord
		doc.email_coord = frappe.db.get_value("Responsavel", coord, "email") or ""
		doc.telefone_coord = frappe.db.get_value("Responsavel", coord, "celular") or ""
	elif tipo_coord == "Associado":
		coord = (dados.get("coordenador") or "").strip()
		if not frappe.db.exists("Associado", coord):
			frappe.throw(_("Associado não encontrado."))
		doc.associado_coord = coord
		doc.responsavel_coord = None
		nome_coord = frappe.db.get_value("Associado", coord, "nome_completo") or coord
		doc.nome_coord = nome_coord
		doc.email_coord = _associado_email(coord)
		doc.telefone_coord = frappe.db.get_value("Associado", coord, "telefone") or ""
	else:
		doc.responsavel_coord = None
		doc.associado_coord = None
		doc.nome_coord = (dados.get("nome_coord") or "").strip()
		doc.email_coord = (dados.get("email_coord") or "").strip()
		doc.telefone_coord = (dados.get("telefone_coord") or "").strip()

	equipe_raw = dados.get("equipe") or []
	doc.equipe = []
	for row in equipe_raw:
		tipo_pessoa = (row.get("tipo_pessoa") or "Outro").strip()
		if tipo_pessoa not in {"Associado", "Responsavel", "Outro"}:
			tipo_pessoa = "Outro"
		entry = {
			"tipo_pessoa": tipo_pessoa,
			"nome": (row.get("nome") or "").strip(),
			"email": (row.get("email") or "").strip(),
			"telefone": (row.get("telefone") or "").strip(),
			"funcao": (row.get("funcao") or "").strip(),
		}
		if tipo_pessoa == "Associado":
			entry["associado"] = (row.get("associado") or "").strip() or None
			entry["responsavel"] = None
			if entry["associado"]:
				# Resolve no servidor para garantir o id@escoteiros quando houver,
				# em vez de confiar no e-mail enviado pelo client.
				entry["email"] = _associado_email(entry["associado"]) or entry["email"]
		elif tipo_pessoa == "Responsavel":
			entry["responsavel"] = (row.get("responsavel") or "").strip() or None
			entry["associado"] = None
		else:
			entry["associado"] = None
			entry["responsavel"] = None

		if not entry["nome"]:
			frappe.throw(_("Todo membro da equipe deve ter nome."))

		doc.append("equipe", entry)

	doc.save()
	return {"ok": True, "nome_coord": doc.nome_coord}


@frappe.whitelist()
def excluir_barraca(barraca_name: str, festa_name: str) -> dict:
	_ensure_gestor()

	doc = frappe.get_doc("Barraca da Festa", barraca_name)
	if doc.festa != festa_name:
		frappe.throw(_("Barraca não pertence a esta festa."))

	produtos = frappe.get_all(
		"Produto de Venda Festa",
		filters={"barraca": barraca_name},
		fields=["nome_produto"],
		order_by="nome_produto",
	)
	if produtos:
		return {
			"ok": False,
			"bloqueado": "produtos",
			"itens": [p.nome_produto for p in produtos],
		}

	# Sem produtos vinculados: a exclusão é permitida. As linhas de orçamento
	# (receitas/despesas por barraca da Festa) que referenciam a barraca são
	# removidas pela re-agregação disparada no on_trash da Barraca da Festa.
	frappe.delete_doc("Barraca da Festa", barraca_name)
	return {"ok": True}


# ---------------------------------------------------------------------------
# Produtos de venda da festa
# ---------------------------------------------------------------------------


def _hydrate_produto(doc) -> dict:
	from frappe.utils import flt

	return {
		"name": doc.name,
		"nome_produto": doc.nome_produto or "",
		"barraca": doc.barraca or "",
		"nome_barraca": frappe.db.get_value("Barraca da Festa", doc.barraca, "nome_barraca") or ""
		if doc.barraca
		else "",
		"faz_parte_convite": bool(doc.faz_parte_convite),
		"preco_custo": flt(doc.preco_custo),
		"preco_venda": flt(doc.preco_venda),
		"margem_lucro": flt(doc.margem_lucro),
		"expectativa_venda_por_pessoa": flt(doc.expectativa_venda_por_pessoa),
		"qtd_min": flt(doc.qtd_min),
		"custo_total_min": flt(doc.custo_total_min),
		"receita_total_min": flt(doc.receita_total_min),
		"superavit_min": flt(doc.superavit_min),
		"qtd_intermediario": flt(doc.qtd_intermediario),
		"custo_total_intermediario": flt(doc.custo_total_intermediario),
		"receita_total_intermediario": flt(doc.receita_total_intermediario),
		"superavit_intermediario": flt(doc.superavit_intermediario),
		"qtd_max": flt(doc.qtd_max),
		"custo_total_max": flt(doc.custo_total_max),
		"receita_total_max": flt(doc.receita_total_max),
		"superavit_max": flt(doc.superavit_max),
		"qtd_realizada_vendas": flt(doc.qtd_realizada_vendas),
		"valor_total_arrecadado": flt(doc.valor_total_arrecadado),
	}


@frappe.whitelist()
def criar_produto(
	festa_name: str,
	nome_produto: str,
	barraca: str,
	faz_parte_convite: str,
	preco_venda: str,
	expectativa_venda_por_pessoa: str,
) -> dict:
	from frappe.utils import flt

	_ensure_gestor()
	_validate_festa(festa_name)

	nome_produto = nome_produto.strip()
	if not nome_produto:
		frappe.throw(_("Informe o nome do produto."))

	barraca = (barraca or "").strip()
	if barraca and not frappe.db.exists("Barraca da Festa", barraca):
		frappe.throw(_("Barraca não encontrada."))
	if barraca:
		festa_da_barraca = frappe.db.get_value("Barraca da Festa", barraca, "festa")
		if festa_da_barraca != festa_name:
			frappe.throw(_("A barraca selecionada não pertence a esta festa."))

	try:
		v_preco_venda = flt(preco_venda)
		v_expectativa = flt(expectativa_venda_por_pessoa)
	except (ValueError, TypeError):
		frappe.throw(_("Valores numéricos inválidos."))

	if v_preco_venda < 0 or v_expectativa < 0:
		frappe.throw(_("Os valores devem ser não-negativos."))

	convite_flag = 1 if faz_parte_convite in ("1", "true", True) else 0
	if convite_flag and v_expectativa < 1:
		frappe.throw(_("Produtos do convite exigem expectativa de venda por pessoa maior ou igual a 1."))

	doc = frappe.new_doc("Produto de Venda Festa")
	doc.festa = festa_name
	doc.nome_produto = nome_produto
	doc.barraca = barraca or None
	doc.faz_parte_convite = convite_flag
	doc.preco_venda = v_preco_venda
	doc.expectativa_venda_por_pessoa = v_expectativa
	doc.insert()
	doc.reload()
	return {"ok": True, "produto": _hydrate_produto(doc)}


@frappe.whitelist()
def salvar_produto(produto_name: str, dados_json: str) -> dict:
	from frappe.utils import flt

	_ensure_gestor()

	try:
		dados = json.loads(dados_json) if isinstance(dados_json, str) else dados_json
	except (ValueError, TypeError):
		frappe.throw(_("Dados inválidos."))

	if not isinstance(dados, dict):
		frappe.throw(_("Dados inválidos."))

	doc = frappe.get_doc("Produto de Venda Festa", produto_name)

	nome_produto = (dados.get("nome_produto") or "").strip()
	if not nome_produto:
		frappe.throw(_("Informe o nome do produto."))
	doc.nome_produto = nome_produto

	barraca = (dados.get("barraca") or "").strip()
	if barraca and not frappe.db.exists("Barraca da Festa", barraca):
		frappe.throw(_("Barraca não encontrada."))
	if barraca:
		festa_da_barraca = frappe.db.get_value("Barraca da Festa", barraca, "festa")
		if festa_da_barraca != doc.festa:
			frappe.throw(_("A barraca selecionada não pertence a esta festa."))
	doc.barraca = barraca or None

	faz_parte = dados.get("faz_parte_convite")
	doc.faz_parte_convite = 1 if faz_parte in ("1", "true", True, 1) else 0

	try:
		v_preco_venda = flt(dados.get("preco_venda", 0))
		v_expectativa = flt(dados.get("expectativa_venda_por_pessoa", 0))
	except (ValueError, TypeError):
		frappe.throw(_("Valores numéricos inválidos."))

	if v_preco_venda < 0 or v_expectativa < 0:
		frappe.throw(_("Os valores devem ser não-negativos."))

	if doc.faz_parte_convite and v_expectativa < 1:
		frappe.throw(_("Produtos do convite exigem expectativa de venda por pessoa maior ou igual a 1."))

	doc.preco_venda = v_preco_venda
	doc.expectativa_venda_por_pessoa = v_expectativa
	doc.save()
	doc.reload()
	return {"ok": True, "produto": _hydrate_produto(doc)}


@frappe.whitelist()
def excluir_produto(produto_name: str, festa_name: str) -> dict:
	_ensure_gestor()

	doc = frappe.get_doc("Produto de Venda Festa", produto_name)
	if doc.festa != festa_name:
		frappe.throw(_("Produto não pertence a esta festa."))

	usos = frappe.get_all(
		"Uso em Produto Festa",
		filters={"produto": produto_name},
		fields=["parent"],
		distinct=True,
	)
	if usos:
		compras = frappe.get_all(
			"Compra Festa",
			filters={"name": ["in", [u.parent for u in usos]]},
			fields=["nome_item"],
			order_by="nome_item",
		)
		return {
			"ok": False,
			"bloqueado": "compras",
			"itens": [c.nome_item for c in compras],
		}

	frappe.delete_doc("Produto de Venda Festa", produto_name)
	return {"ok": True}


# ---------------------------------------------------------------------------
# Compras da festa
# ---------------------------------------------------------------------------


def _parse_json_dict(dados_json) -> dict:
	try:
		dados = json.loads(dados_json) if isinstance(dados_json, str) else dados_json
	except (ValueError, TypeError):
		frappe.throw(_("Dados inválidos."))

	if not isinstance(dados, dict):
		frappe.throw(_("Dados inválidos."))
	return dados


def _as_bool(value) -> int:
	return 1 if value in ("1", "true", "True", True, 1) else 0


def _as_non_negative_float(value, label: str) -> float:
	if value in (None, ""):
		return 0.0
	try:
		number = float(value)
	except (ValueError, TypeError):
		frappe.throw(f"{label} deve ser um número.")
	if number < 0:
		frappe.throw(f"{label} deve ser não-negativo.")
	return flt(number)


def _validate_unidade(unidade: str, label: str = "Unidade") -> str:
	unidade = (unidade or "").strip()
	if unidade not in UNIDADES:
		frappe.throw(f"{label} inválida.")
	return unidade


def _validate_area_festa(area: str, festa_name: str) -> str | None:
	area = (area or "").strip()
	if not area:
		return None
	if not frappe.db.exists("Area da Festa", area):
		frappe.throw(_("Área não encontrada."))
	festa_da_area = frappe.db.get_value("Area da Festa", area, "festa")
	if festa_da_area != festa_name:
		frappe.throw(_("A área selecionada não pertence a esta festa."))
	return area


def _validate_produto_festa(produto: str, festa_name: str) -> str:
	produto = (produto or "").strip()
	if not produto:
		frappe.throw(_("Selecione o produto usado."))
	if not frappe.db.exists("Produto de Venda Festa", produto):
		frappe.throw(_("Produto não encontrado."))
	festa_do_produto = frappe.db.get_value("Produto de Venda Festa", produto, "festa")
	if festa_do_produto != festa_name:
		frappe.throw(_("O produto selecionado não pertence a esta festa."))
	return produto


def _hydrate_cotacao(row) -> dict:
	return {
		"fornecedor": row.fornecedor or "",
		"valor": flt(row.valor),
		"quantidade": flt(row.quantidade),
		"unidade_medida": row.unidade_medida or "unidade",
		"escolhida": bool(row.escolhida),
		"doacao": bool(row.doacao),
	}


def _hydrate_uso(row, produto_labels: dict[str, str] | None = None) -> dict:
	produto_labels = produto_labels or {}
	return {
		"produto": row.produto or "",
		"produto_label": produto_labels.get(row.produto) or row.produto or "",
		"quantidade_usada": flt(row.quantidade_usada),
		"unidade_medida_uso": row.unidade_medida_uso or "unidade",
		"fracao_item": flt(row.fracao_item),
		"valor_uso": flt(row.valor_uso),
	}


def _hydrate_compra(doc) -> dict:
	produtos = [u.produto for u in (doc.usos_em_produto or []) if u.produto]
	produto_labels = {}
	if produtos:
		for row in frappe.get_all(
			"Produto de Venda Festa",
			filters={"name": ("in", produtos)},
			fields=["name", "nome_produto"],
		):
			produto_labels[row.name] = row.nome_produto or row.name
	nome_area = ""
	if doc.area:
		nome_area = frappe.db.get_value("Area da Festa", doc.area, "nome_area") or ""

	return {
		"name": doc.name,
		"festa": doc.festa or "",
		"area": doc.area or "",
		"nome_area": nome_area,
		"nome_item": doc.nome_item or "",
		"previsto": bool(doc.previsto),
		"varia_com_publico": bool(doc.varia_com_publico),
		"usado_em_produtos": bool(doc.usado_em_produtos),
		"unidade_compra": doc.unidade_compra or "unidade",
		"quantidade_compra": flt(doc.quantidade_compra),
		"quantidade_compra_final": flt(doc.quantidade_compra_final),
		"cotacao_escolhida_valor": flt(doc.cotacao_escolhida_valor),
		"valor_total_compra": flt(doc.valor_total_compra),
		"valor_individual_realizado": flt(doc.valor_individual_realizado),
		"quantidade_cotacao_realizada": flt(doc.quantidade_cotacao_realizada),
		"unidade_medida_realizado": doc.unidade_medida_realizado or "unidade",
		"quantidade_realizada": flt(doc.quantidade_realizada),
		"valor_total_realizado": flt(doc.valor_total_realizado),
		"fornecedor_realizado": doc.fornecedor_realizado or "",
		"observacoes_realizado": doc.observacoes_realizado or "",
		"cancelado": bool(doc.cancelado),
		"qtd_sugerida_min": flt(doc.qtd_sugerida_min),
		"valor_total_min": flt(doc.valor_total_min),
		"qtd_sobra_individual_min": flt(doc.qtd_sobra_individual_min),
		"valor_sobra_min": flt(doc.valor_sobra_min),
		"qtd_sugerida_intermediario": flt(doc.qtd_sugerida_intermediario),
		"valor_total_intermediario": flt(doc.valor_total_intermediario),
		"qtd_sobra_individual_intermediario": flt(doc.qtd_sobra_individual_intermediario),
		"valor_sobra_intermediario": flt(doc.valor_sobra_intermediario),
		"qtd_sugerida_max": flt(doc.qtd_sugerida_max),
		"valor_total_max": flt(doc.valor_total_max),
		"qtd_sobra_individual_max": flt(doc.qtd_sobra_individual_max),
		"valor_sobra_max": flt(doc.valor_sobra_max),
		"cotacoes": [_hydrate_cotacao(c) for c in (doc.cotacoes or [])],
		"usos_em_produto": [_hydrate_uso(uso, produto_labels) for uso in (doc.usos_em_produto or [])],
	}


def _apply_compra_dados(doc, dados: dict, festa_name: str) -> set[str]:
	nome_item = (dados.get("nome_item") or "").strip()
	if not nome_item:
		frappe.throw(_("Informe o nome do item."))

	doc.nome_item = nome_item
	doc.area = _validate_area_festa(dados.get("area"), festa_name)
	doc.unidade_compra = _validate_unidade(dados.get("unidade_compra") or "unidade")
	doc.varia_com_publico = _as_bool(dados.get("varia_com_publico"))
	doc.usado_em_produtos = _as_bool(dados.get("usado_em_produtos"))
	doc.quantidade_compra_final = _as_non_negative_float(
		dados.get("quantidade_compra_final", 0),
		"Quantidade final",
	)

	cotacoes = dados.get("cotacoes") or []
	if not isinstance(cotacoes, list):
		frappe.throw(_("Cotações inválidas."))
	if sum(1 for row in cotacoes if _as_bool(row.get("escolhida"))) > 1:
		frappe.throw(_("Apenas uma cotação pode ser marcada como escolhida."))

	doc.cotacoes = []
	for row in cotacoes:
		if not isinstance(row, dict):
			frappe.throw(_("Cotação inválida."))
		fornecedor = (row.get("fornecedor") or "").strip()
		if not fornecedor:
			frappe.throw(_("Informe o fornecedor de todas as cotações."))
		doc.append(
			"cotacoes",
			{
				"fornecedor": fornecedor,
				"valor": _as_non_negative_float(row.get("valor", 0), "Valor da cotação"),
				"quantidade": _as_non_negative_float(
					row.get("quantidade", 0),
					"Quantidade da cotação",
				),
				"unidade_medida": _validate_unidade(
					row.get("unidade_medida") or "unidade",
					"Unidade da cotação",
				),
				"escolhida": _as_bool(row.get("escolhida")),
				"doacao": _as_bool(row.get("doacao")),
			},
		)

	produtos_anteriores = {uso.produto for uso in (doc.usos_em_produto or []) if uso.produto}
	doc.usos_em_produto = []
	if doc.usado_em_produtos:
		usos = dados.get("usos_em_produto") or []
		if not isinstance(usos, list):
			frappe.throw(_("Usos em produto inválidos."))
		for row in usos:
			if not isinstance(row, dict):
				frappe.throw(_("Uso em produto inválido."))
			doc.append(
				"usos_em_produto",
				{
					"produto": _validate_produto_festa(row.get("produto"), festa_name),
					"quantidade_usada": _as_non_negative_float(
						row.get("quantidade_usada", 0),
						"Quantidade usada",
					),
					"unidade_medida_uso": _validate_unidade(
						row.get("unidade_medida_uso") or "unidade",
						"Unidade de uso",
					),
				},
			)

	return produtos_anteriores


def _reagregar_produtos_por_nome(produtos: set[str]) -> None:
	for nome in produtos:
		try:
			prod = frappe.get_doc("Produto de Venda Festa", nome)
			prod.save(ignore_permissions=True)
		except frappe.DoesNotExistError:
			continue


@frappe.whitelist()
def criar_compra(festa_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)
	dados = _parse_json_dict(dados_json)

	doc = frappe.new_doc("Compra Festa")
	doc.festa = festa_name
	doc.previsto = 1
	_apply_compra_dados(doc, dados, festa_name)
	doc.insert()
	doc.reload()
	return {"ok": True, "compra": _hydrate_compra(doc)}


@frappe.whitelist()
def salvar_compra(compra_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	dados = _parse_json_dict(dados_json)

	doc = frappe.get_doc("Compra Festa", compra_name)
	produtos_anteriores = _apply_compra_dados(doc, dados, doc.festa)
	doc.save()
	doc.reload()

	produtos_atuais = {uso.produto for uso in (doc.usos_em_produto or []) if uso.produto}
	_reagregar_produtos_por_nome(produtos_anteriores - produtos_atuais)
	doc.reload()
	return {"ok": True, "compra": _hydrate_compra(doc)}


@frappe.whitelist()
def excluir_compra(compra_name: str, festa_name: str) -> dict:
	_ensure_gestor()

	doc = frappe.get_doc("Compra Festa", compra_name)
	if doc.festa != festa_name:
		frappe.throw(_("Compra não pertence a esta festa."))

	frappe.delete_doc("Compra Festa", compra_name)
	return {"ok": True}


# ---------------------------------------------------------------------------
# Contratações da festa
# ---------------------------------------------------------------------------


def _hydrate_cotacao_contratacao(row) -> dict:
	return {
		"fornecedor": row.fornecedor or "",
		"valor": flt(row.valor),
		"escolhida": bool(row.escolhida),
	}


def _hydrate_contratacao(doc) -> dict:
	nome_area = ""
	if doc.area:
		nome_area = frappe.db.get_value("Area da Festa", doc.area, "nome_area") or ""
	return {
		"name": doc.name,
		"festa": doc.festa or "",
		"area": doc.area or "",
		"nome_area": nome_area,
		"nome_item": doc.nome_item or "",
		"previsto": bool(doc.previsto),
		"valor_total_contratacao": flt(doc.valor_total_contratacao),
		"valor_total_realizado": flt(doc.valor_total_realizado),
		"fornecedor_realizado": doc.fornecedor_realizado or "",
		"observacoes_realizado": doc.observacoes_realizado or "",
		"cancelado": bool(doc.cancelado),
		"cotacoes": [_hydrate_cotacao_contratacao(c) for c in (doc.cotacoes or [])],
	}


def _apply_contratacao_dados(doc, dados: dict, festa_name: str) -> None:
	nome_item = (dados.get("nome_item") or "").strip()
	if not nome_item:
		frappe.throw(_("Informe o nome do item."))
	doc.nome_item = nome_item
	doc.area = _validate_area_festa(dados.get("area"), festa_name)

	cotacoes = dados.get("cotacoes") or []
	if not isinstance(cotacoes, list):
		frappe.throw(_("Cotações inválidas."))
	if sum(1 for row in cotacoes if _as_bool(row.get("escolhida"))) > 1:
		frappe.throw(_("Apenas uma cotação pode ser marcada como escolhida."))

	doc.cotacoes = []
	for row in cotacoes:
		if not isinstance(row, dict):
			frappe.throw(_("Cotação inválida."))
		fornecedor = (row.get("fornecedor") or "").strip()
		if not fornecedor:
			frappe.throw(_("Informe o fornecedor de todas as cotações."))
		doc.append(
			"cotacoes",
			{
				"fornecedor": fornecedor,
				"valor": _as_non_negative_float(row.get("valor", 0), "Valor da cotação"),
				"escolhida": _as_bool(row.get("escolhida")),
			},
		)


@frappe.whitelist()
def criar_contratacao(festa_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)
	dados = _parse_json_dict(dados_json)

	doc = frappe.new_doc("Contratacao Festa")
	doc.festa = festa_name
	doc.previsto = 1
	_apply_contratacao_dados(doc, dados, festa_name)
	doc.insert()
	doc.reload()
	return {"ok": True, "contratacao": _hydrate_contratacao(doc)}


@frappe.whitelist()
def salvar_contratacao(contratacao_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	dados = _parse_json_dict(dados_json)

	doc = frappe.get_doc("Contratacao Festa", contratacao_name)
	_apply_contratacao_dados(doc, dados, doc.festa)
	doc.save()
	doc.reload()
	return {"ok": True, "contratacao": _hydrate_contratacao(doc)}


@frappe.whitelist()
def excluir_contratacao(contratacao_name: str, festa_name: str) -> dict:
	_ensure_gestor()

	doc = frappe.get_doc("Contratacao Festa", contratacao_name)
	if doc.festa != festa_name:
		frappe.throw(_("Contratação não pertence a esta festa."))

	frappe.delete_doc("Contratacao Festa", contratacao_name)
	return {"ok": True}


# ---------------------------------------------------------------------------
# Fechamento — realizado de compras, contratações e barracas
# ---------------------------------------------------------------------------


def _apply_compra_realizado(doc, dados: dict) -> None:
	doc.valor_individual_realizado = _as_non_negative_float(
		dados.get("valor_individual_realizado", 0), "Valor individual realizado"
	)
	doc.quantidade_cotacao_realizada = _as_non_negative_float(
		dados.get("quantidade_cotacao_realizada", 0), "Quantidade da cotação realizada"
	)
	doc.unidade_medida_realizado = _validate_unidade(
		dados.get("unidade_medida_realizado") or "unidade", "Unidade realizada"
	)
	doc.quantidade_realizada = _as_non_negative_float(
		dados.get("quantidade_realizada", 0), "Quantidade realizada"
	)
	doc.valor_total_realizado = _as_non_negative_float(
		dados.get("valor_total_realizado", 0), "Valor total realizado"
	)
	doc.fornecedor_realizado = (dados.get("fornecedor_realizado") or "").strip()
	doc.observacoes_realizado = (dados.get("observacoes_realizado") or "").strip()
	doc.cancelado = _as_bool(dados.get("cancelado"))


def _apply_contratacao_realizado(doc, dados: dict) -> None:
	doc.valor_total_realizado = _as_non_negative_float(
		dados.get("valor_total_realizado", 0), "Valor total realizado"
	)
	doc.fornecedor_realizado = (dados.get("fornecedor_realizado") or "").strip()
	doc.observacoes_realizado = (dados.get("observacoes_realizado") or "").strip()
	doc.cancelado = _as_bool(dados.get("cancelado"))


def _apply_compra_usos_sem_previsao(doc, dados: dict, festa_name: str) -> None:
	doc.usos_em_produto = []
	if not doc.usado_em_produtos:
		return
	usos = dados.get("usos_em_produto") or []
	if not isinstance(usos, list):
		frappe.throw(_("Usos em produto inválidos."))
	for row in usos:
		if not isinstance(row, dict):
			frappe.throw(_("Uso em produto inválido."))
		doc.append(
			"usos_em_produto",
			{
				"produto": _validate_produto_festa(row.get("produto"), festa_name),
				"quantidade_usada": _as_non_negative_float(
					row.get("quantidade_usada", 0), "Quantidade usada"
				),
				"unidade_medida_uso": _validate_unidade(
					row.get("unidade_medida_uso") or "unidade", "Unidade de uso"
				),
			},
		)


@frappe.whitelist()
def salvar_realizado_compra(compra_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	dados = _parse_json_dict(dados_json)

	doc = frappe.get_doc("Compra Festa", compra_name)
	_apply_compra_realizado(doc, dados)
	doc.save()
	doc.reload()
	return {"ok": True, "compra": _hydrate_compra(doc)}


@frappe.whitelist()
def criar_compra_sem_previsao(festa_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)
	dados = _parse_json_dict(dados_json)

	nome_item = (dados.get("nome_item") or "").strip()
	if not nome_item:
		frappe.throw(_("Informe o nome do item."))

	doc = frappe.new_doc("Compra Festa")
	doc.festa = festa_name
	doc.previsto = 0
	doc.nome_item = nome_item
	doc.area = _validate_area_festa(dados.get("area"), festa_name)
	doc.usado_em_produtos = _as_bool(dados.get("usado_em_produtos"))
	doc.unidade_compra = _validate_unidade(dados.get("unidade_medida_realizado") or "unidade")
	_apply_compra_usos_sem_previsao(doc, dados, festa_name)
	_apply_compra_realizado(doc, dados)
	doc.insert()
	doc.reload()
	return {"ok": True, "compra": _hydrate_compra(doc)}


@frappe.whitelist()
def salvar_compra_sem_previsao(compra_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	dados = _parse_json_dict(dados_json)

	doc = frappe.get_doc("Compra Festa", compra_name)
	if doc.previsto:
		frappe.throw(_("Apenas itens sem previsão podem ser editados aqui."))

	nome_item = (dados.get("nome_item") or "").strip()
	if not nome_item:
		frappe.throw(_("Informe o nome do item."))

	doc.nome_item = nome_item
	doc.area = _validate_area_festa(dados.get("area"), doc.festa)
	doc.usado_em_produtos = _as_bool(dados.get("usado_em_produtos"))
	doc.unidade_compra = _validate_unidade(dados.get("unidade_medida_realizado") or "unidade")
	_apply_compra_usos_sem_previsao(doc, dados, doc.festa)
	_apply_compra_realizado(doc, dados)
	doc.save()
	doc.reload()
	return {"ok": True, "compra": _hydrate_compra(doc)}


@frappe.whitelist()
def salvar_realizado_contratacao(contratacao_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	dados = _parse_json_dict(dados_json)

	doc = frappe.get_doc("Contratacao Festa", contratacao_name)
	_apply_contratacao_realizado(doc, dados)
	doc.save()
	doc.reload()
	return {"ok": True, "contratacao": _hydrate_contratacao(doc)}


@frappe.whitelist()
def criar_contratacao_sem_previsao(festa_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)
	dados = _parse_json_dict(dados_json)

	nome_item = (dados.get("nome_item") or "").strip()
	if not nome_item:
		frappe.throw(_("Informe o nome do item."))

	doc = frappe.new_doc("Contratacao Festa")
	doc.festa = festa_name
	doc.previsto = 0
	doc.nome_item = nome_item
	doc.area = _validate_area_festa(dados.get("area"), festa_name)
	_apply_contratacao_realizado(doc, dados)
	doc.insert()
	doc.reload()
	return {"ok": True, "contratacao": _hydrate_contratacao(doc)}


@frappe.whitelist()
def salvar_contratacao_sem_previsao(contratacao_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	dados = _parse_json_dict(dados_json)

	doc = frappe.get_doc("Contratacao Festa", contratacao_name)
	if doc.previsto:
		frappe.throw(_("Apenas itens sem previsão podem ser editados aqui."))

	nome_item = (dados.get("nome_item") or "").strip()
	if not nome_item:
		frappe.throw(_("Informe o nome do item."))

	doc.nome_item = nome_item
	doc.area = _validate_area_festa(dados.get("area"), doc.festa)
	_apply_contratacao_realizado(doc, dados)
	doc.save()
	doc.reload()
	return {"ok": True, "contratacao": _hydrate_contratacao(doc)}


@frappe.whitelist()
def salvar_fechamento_barraca(festa_name: str, barraca_name: str, dados_json: str) -> dict:
	_ensure_gestor()
	_validate_festa(festa_name)
	dados = _parse_json_dict(dados_json)

	if frappe.db.get_value("Barraca da Festa", barraca_name, "festa") != festa_name:
		frappe.throw(_("Barraca não pertence a esta festa."))

	precos = {
		p.name: flt(p.preco_venda)
		for p in frappe.get_all(
			"Produto de Venda Festa",
			filters={"festa": festa_name, "barraca": barraca_name},
			fields=["name", "preco_venda"],
		)
	}

	itens = dados.get("itens") or []
	if not isinstance(itens, list):
		frappe.throw(_("Itens inválidos."))
	for row in itens:
		if not isinstance(row, dict):
			frappe.throw(_("Item inválido."))
		produto = (row.get("produto") or "").strip()
		if produto not in precos:
			frappe.throw(_("Produto não pertence a esta barraca."))
		qtd = _as_non_negative_float(row.get("qtd_realizada", 0), "Quantidade realizada")
		frappe.db.set_value(
			"Produto de Venda Festa",
			produto,
			{
				"qtd_realizada_vendas": qtd,
				"valor_total_arrecadado": qtd * precos[produto],
			},
		)

	valor_real = _as_non_negative_float(
		dados.get("valor_realizado_real", 0), "Valor arrecadado realizado real"
	)
	frappe.db.set_value("Barraca da Festa", barraca_name, "valor_arrecadado_realizado_real", valor_real)

	return {"ok": True}
