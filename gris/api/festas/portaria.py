# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt

"""Endpoints da página /festas/portaria.

ACL: System Manager, Gestor de festas, role Portaria (acesso global) OU
coordenador/membro da Area Portaria da festa em questão (acesso por festa).
Implementada em `gris.festas.utils.portaria.user_pode_operar_portaria`.
"""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import flt, get_datetime, now

from gris.festas.doctype.lista_entrada_festa.lista_entrada_festa import (
	STATUS_ENTROU,
	STATUS_NAO_ENTROU,
	ListaEntradaFesta,
)
from gris.festas.utils.portaria import (
	ensure_user_pode_operar_portaria,
	festas_que_user_pode_operar,
)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PORTARIA_CONVITE_URL_BASE = "/festas/venda_convite"


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _carregar_entrada(name: str) -> frappe._dict | None:
	return frappe.db.get_value(
		"Lista Entrada Festa",
		name,
		[
			"name",
			"festa",
			"convite",
			"convidado_row",
			"codigo_convite",
			"nome_convidado",
			"email",
			"telefone",
			"status",
			"hora_entrada",
			"entrada_registrada_por",
		],
		as_dict=True,
	)


def _buscar_por_codigo(festa: str, codigo: str) -> frappe._dict | None:
	# get_value retorna a primeira linha que casa; codigo_convite é unique.
	name = frappe.db.get_value(
		"Lista Entrada Festa",
		{"festa": festa, "codigo_convite": codigo},
		"name",
	)
	if not name:
		return None
	return _carregar_entrada(name)


def _hidratar_entrada(row, *, pagador: dict | None = None) -> dict:
	pagador = pagador or {}
	return {
		"name": row.name,
		"festa": row.festa,
		"convite": row.convite,
		"codigo": row.codigo_convite,
		"nome_convidado": row.nome_convidado or "",
		"nome_pagador": pagador.get("nome") or "",
		"email_pagador": pagador.get("email") or "",
		"telefone_pagador": pagador.get("telefone") or "",
		"email": row.email or "",
		"telefone": row.telefone or "",
		"status": row.status,
		"hora_entrada": row.hora_entrada.isoformat() if row.hora_entrada else "",
		"registrado_por": row.entrada_registrada_por or "",
		"ja_entrou": row.status == STATUS_ENTROU,
	}


def _dados_pagador(convite_name: str) -> dict:
	if not convite_name:
		return {}
	row = frappe.db.get_value(
		"Convite Festa",
		convite_name,
		["nome_pagador", "email_pagador", "telefone_pagador"],
		as_dict=True,
	)
	if not row:
		return {}
	return {
		"nome": row.nome_pagador or "",
		"email": row.email_pagador or "",
		"telefone": row.telefone_pagador or "",
	}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist()
def listar_festas_para_user() -> list[dict]:
	"""Lista as festas ativas que o usuário atual pode operar (para o picker)."""
	return festas_que_user_pode_operar(frappe.session.user)


@frappe.whitelist()
@rate_limit(key="portaria-consulta", limit=120, seconds=60)
def consultar_convite(festa: str, codigo: str) -> dict:
	"""Consulta convite por código QR. Não altera estado.

	"Código não encontrado" é resultado esperado da operação (não exceção):
	retornamos HTTP 200 com {valido: False} para o frontend exibir o dialog
	sem ruído de HTTP 417 no console. A resposta é idêntica para "não existe"
	vs. "existe em outra festa" — mantém o invariante de não vazar enumeração.
	"""
	festa = (festa or "").strip()
	codigo = (codigo or "").strip()
	if not festa or not codigo:
		frappe.throw(_("Festa e código são obrigatórios."))

	ensure_user_pode_operar_portaria(festa)

	row = _buscar_por_codigo(festa, codigo)
	if not row:
		return {"valido": False}

	return {"valido": True, **_hidratar_entrada(row, pagador=_dados_pagador(row.convite))}


@frappe.whitelist()
@rate_limit(key="portaria-marcar", limit=120, seconds=60)
def marcar_entrada(festa: str, codigo: str) -> dict:
	"""Marca entrada de forma atômica. Idempotente para duplo scan."""
	festa = (festa or "").strip()
	codigo = (codigo or "").strip()
	if not festa or not codigo:
		frappe.throw(_("Festa e código são obrigatórios."))

	ensure_user_pode_operar_portaria(festa)

	row = _buscar_por_codigo(festa, codigo)
	if not row:
		return {"valido": False}

	resultado = ListaEntradaFesta.marcar_entrada(row.name, user=frappe.session.user)

	# Recarrega para devolver estado consistente.
	row = _carregar_entrada(row.name)
	hidratado = _hidratar_entrada(row, pagador=_dados_pagador(row.convite))
	hidratado["valido"] = True
	hidratado["ja_entrou_antes"] = resultado.get("ja_entrou_antes", False)
	return hidratado


@frappe.whitelist()
@rate_limit(key="portaria-marcar-manual", limit=30, seconds=60)
def marcar_entrada_manual(festa: str, codigo: str) -> dict:
	"""Confirma a entrada de um convidado sem apresentação do QR code.

	Usado quando o convidado realmente comprou o convite mas não tem o QR à
	mão. Mesma semântica atômica de `marcar_entrada`, mas seta
	`entrada_manual=1` para auditoria.
	"""
	festa = (festa or "").strip()
	codigo = (codigo or "").strip()
	if not festa or not codigo:
		frappe.throw(_("Festa e código são obrigatórios."))

	ensure_user_pode_operar_portaria(festa)

	row = _buscar_por_codigo(festa, codigo)
	if not row:
		return {"valido": False}

	resultado = ListaEntradaFesta.marcar_entrada(row.name, user=frappe.session.user, manual=True)

	row = _carregar_entrada(row.name)
	hidratado = _hidratar_entrada(row, pagador=_dados_pagador(row.convite))
	hidratado["valido"] = True
	hidratado["ja_entrou_antes"] = resultado.get("ja_entrou_antes", False)
	return hidratado


@frappe.whitelist()
def listar_entradas(
	festa: str,
	nome: str = "",
	status: str = "",
	limit: int = 200,
	offset: int = 0,
) -> dict:
	"""Lista entradas de uma festa, com filtros por nome e status."""
	festa = (festa or "").strip()
	if not festa:
		frappe.throw(_("Festa é obrigatória."))

	ensure_user_pode_operar_portaria(festa)

	try:
		limit_int = max(1, min(int(limit), 500))
		offset_int = max(0, int(offset))
	except (ValueError, TypeError):
		frappe.throw(_("Paginação inválida."))

	params: dict = {
		"festa": festa,
		"limit": limit_int,
		"offset": offset_int,
	}
	extra_where = ""
	if status and status in (STATUS_ENTROU, STATUS_NAO_ENTROU):
		extra_where += " AND lef.status = %(status)s"
		params["status"] = status
	nome_norm = (nome or "").strip()
	if nome_norm:
		extra_where += " AND lef.nome_convidado LIKE %(nome_like)s"
		params["nome_like"] = f"%{nome_norm}%"

	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	rows = frappe.db.sql(
		f"""
		SELECT
			lef.name, lef.convite, lef.codigo_convite,
			lef.nome_convidado, lef.email, lef.telefone,
			lef.nome_pagador, lef.email_pagador, lef.telefone_pagador,
			lef.status, lef.hora_entrada, lef.entrada_registrada_por,
			lef.presencial,
			MAX(COALESCE(opc.portaria, 0)) AS origem_portaria_opcao
		  FROM `tabLista Entrada Festa` lef
		  LEFT JOIN `tabItem Convite Festa` it
			ON it.parent = lef.convite
			AND it.parenttype = 'Convite Festa'
			AND it.eh_convite = 1
		  LEFT JOIN `tabOpcao Convite Festa` opc
			ON opc.name = it.opcao_convite
		 WHERE lef.festa = %(festa)s{extra_where}
		 GROUP BY lef.name
		 ORDER BY lef.nome_convidado ASC
		 LIMIT %(limit)s OFFSET %(offset)s
		""",
		params,
		as_dict=True,
	)

	count_params = {"festa": festa}
	count_where = ""
	if "status" in params:
		count_where += " AND status = %(status)s"
		count_params["status"] = params["status"]
	if "nome_like" in params:
		count_where += " AND nome_convidado LIKE %(nome_like)s"
		count_params["nome_like"] = params["nome_like"]
	# Interpolação auditada: só entram fragmentos SQL montados neste módulo (nomes de coluna e
	# condições literais). Todo valor vindo do usuário é passado por `params`.
	# nosemgrep
	total_row = frappe.db.sql(
		f"SELECT COUNT(*) AS qtd FROM `tabLista Entrada Festa` WHERE festa = %(festa)s{count_where}",
		count_params,
		as_dict=True,
	)
	total = int(total_row[0].qtd) if total_row else 0

	entradas = []
	for r in rows:
		eh_portaria = bool(int(r.presencial or 0)) or bool(int(r.origem_portaria_opcao or 0))
		entradas.append(
			{
				"name": r.name,
				"convite": r.convite or "",
				"codigo": r.codigo_convite or "",
				"nome_convidado": r.nome_convidado or "",
				"email": r.email or "",
				"telefone": r.telefone or "",
				"nome_pagador": r.nome_pagador or "",
				"email_pagador": r.email_pagador or "",
				"telefone_pagador": r.telefone_pagador or "",
				"status": r.status,
				"hora_entrada": r.hora_entrada.isoformat() if r.hora_entrada else "",
				"registrado_por": r.entrada_registrada_por or "",
				"ja_entrou": r.status == STATUS_ENTROU,
				"origem": "portaria" if eh_portaria else "previa",
			}
		)

	return {"entradas": entradas, "total": total}


@frappe.whitelist()
def editar_dados_convidado(
	lista_entrada_name: str,
	email: str | None = None,
	telefone: str | None = None,
) -> dict:
	"""Atualiza email e/ou telefone do convidado.

	Reflete em Lista Entrada Festa e na linha de Convidado Convite Festa.
	Nome do convidado e código não são editáveis (proteção contra fraude).
	"""
	lista_entrada_name = (lista_entrada_name or "").strip()
	if not lista_entrada_name:
		frappe.throw(_("Registro inválido."))

	row = _carregar_entrada(lista_entrada_name)
	if not row:
		frappe.throw(_("Entrada não encontrada."))

	ensure_user_pode_operar_portaria(row.festa)

	email_norm: str | None = None
	if email is not None:
		email_strip = (email or "").strip().lower()
		if email_strip:
			if not EMAIL_REGEX.match(email_strip):
				frappe.throw(_("E-mail inválido."))
			email_norm = email_strip

	telefone_norm: str | None = None
	if telefone is not None:
		telefone_digits = re.sub(r"\D", "", telefone or "")
		telefone_norm = telefone_digits or None

	# Atualiza Lista Entrada Festa.
	updates: dict = {}
	if email is not None:
		updates["email"] = email_norm
	if telefone is not None:
		updates["telefone"] = telefone_norm
	if updates:
		frappe.db.set_value("Lista Entrada Festa", lista_entrada_name, updates)

	# Atualiza a linha de Convidado Convite Festa para manter consistência.
	if row.convidado_row and updates:
		# Confirma que a row pertence ao convite esperado antes de tocar.
		dono = frappe.db.get_value(
			"Convidado Convite Festa",
			row.convidado_row,
			["parent", "parenttype"],
			as_dict=True,
		)
		if dono and dono.parenttype == "Convite Festa" and dono.parent == row.convite:
			frappe.db.set_value("Convidado Convite Festa", row.convidado_row, updates)

	atualizado = _carregar_entrada(lista_entrada_name)
	return {
		"ok": True,
		"entrada": _hidratar_entrada(atualizado, pagador=_dados_pagador(atualizado.convite)),
	}


@frappe.whitelist()
@rate_limit(key="portaria-reenvio", limit=10, seconds=60)
def reenviar_convite(lista_entrada_name: str) -> dict:
	"""Reenvia o QR code do convidado específico para o e-mail dele.

	Rate-limited para evitar abuso. O envio é assíncrono via fila.
	"""
	lista_entrada_name = (lista_entrada_name or "").strip()
	if not lista_entrada_name:
		frappe.throw(_("Registro inválido."))

	row = _carregar_entrada(lista_entrada_name)
	if not row:
		frappe.throw(_("Entrada não encontrada."))

	ensure_user_pode_operar_portaria(row.festa)

	if not row.email:
		frappe.throw(_("Convidado não possui e-mail cadastrado."))

	from gris.festas.doctype.convite_festa.convite_festa import (
		STATUS_PAGAMENTO_PAGO,
	)

	status = frappe.db.get_value(
		"Cobranca Infinitepay",
		frappe.db.get_value("Convite Festa", row.convite, "cobranca_infinitepay"),
		"status",
	)
	if status != STATUS_PAGAMENTO_PAGO:
		frappe.throw(_("O pagamento deste convite ainda não foi confirmado."))

	frappe.enqueue(
		"gris.festas.doctype.convite_festa.convite_festa.enviar_qr_codes",
		queue="long",
		enqueue_after_commit=True,
		convite_name=row.convite,
		convidado_row_name=row.convidado_row,
		forcar_todos=True,
	)
	return {"ok": True}


@frappe.whitelist()
def get_acompanhamento(festa: str) -> dict:
	"""Métricas para a aba Acompanhamento (pizza + linha por 15min + origem)."""
	festa = (festa or "").strip()
	if not festa:
		frappe.throw(_("Festa é obrigatória."))

	ensure_user_pode_operar_portaria(festa)
	return build_acompanhamento_data(festa)


def build_acompanhamento_data(festa: str) -> dict:
	"""Pizza/linha/origem das entradas de uma festa, sem checagem de permissão.

	O chamador é responsável por autorizar o acesso. Reutilizado pela página de
	relatório (`/festas/relatorio`), que já valida a permissão de leitura da Festa.
	"""
	# Contagem por (status, origem_portaria). É considerado "portaria" quando:
	#  - lef.presencial = 1 (venda presencial física, marca o entrou no after_insert), OU
	#  - o convite contém ao menos um Item Convite Festa cuja Opcao Convite Festa
	#    tem portaria=1 (cobre vendas via link de pagamento da portaria).
	contagem_rows = frappe.db.sql(
		"""
		SELECT
			lef.status,
			CASE
				WHEN lef.presencial = 1
				  OR EXISTS (
					  SELECT 1
						FROM `tabItem Convite Festa` it
						JOIN `tabOpcao Convite Festa` opc
						  ON opc.name = it.opcao_convite
					   WHERE it.parent = lef.convite
						 AND it.parenttype = 'Convite Festa'
						 AND it.eh_convite = 1
						 AND opc.portaria = 1
				  ) THEN 1
				ELSE 0
			END AS origem_portaria,
			COUNT(*) AS qtd
		  FROM `tabLista Entrada Festa` lef
		 WHERE lef.festa = %s
		 GROUP BY lef.status, origem_portaria
		""",
		(festa,),
		as_dict=True,
	)
	entrou_previo = 0
	comprou_portaria = 0
	nao_entrou = 0
	for row in contagem_rows:
		qtd = int(row.qtd or 0)
		if row.status == STATUS_NAO_ENTROU:
			nao_entrou += qtd
		elif row.status == STATUS_ENTROU:
			if int(row.origem_portaria or 0):
				comprou_portaria += qtd
			else:
				entrou_previo += qtd
	total = entrou_previo + nao_entrou + comprou_portaria
	total_entrou = entrou_previo + comprou_portaria

	# Linha: bins de 15 minutos contando entradas.
	# Truncamento para 15min via floor(unix_timestamp/900)*900.
	linha_rows = frappe.db.sql(
		"""
		SELECT FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(hora_entrada) / 900) * 900) AS bin,
		       COUNT(*) AS qtd
		  FROM `tabLista Entrada Festa`
		 WHERE festa = %s
		   AND status = %s
		   AND hora_entrada IS NOT NULL
		 GROUP BY bin
		 ORDER BY bin ASC
		""",
		(festa, STATUS_ENTROU),
		as_dict=True,
	)
	linha = []
	acumulado = 0
	for row in linha_rows:
		valor = int(row.qtd or 0)
		acumulado += valor
		bin_dt = get_datetime(row.bin) if row.bin else None
		linha.append(
			{
				"bin": bin_dt.isoformat() if bin_dt else "",
				"qtd": valor,
				"acumulado": acumulado,
			}
		)

	return {
		"pizza": {
			"entrou": entrou_previo,
			"nao_entrou": nao_entrou,
			"comprou_portaria": comprou_portaria,
			"total": total,
			"total_entrou": total_entrou,
			"pct_entrou": round((total_entrou / total) * 100, 1) if total else 0.0,
		},
		"linha": linha,
		"origem_entradas": {
			"compra_previa": entrou_previo,
			"compra_portaria": comprou_portaria,
			"total_entrou": total_entrou,
		},
	}


@frappe.whitelist()
def get_url_venda_porta(festa: str) -> dict:
	"""Retorna a URL pública de venda pré-selecionada e o QR code (PNG base64).

	Usada pelo dialog 'Vender na porta'. Reutiliza `gerar_png` do utilitário
	de QR para garantir consistência visual com os QR codes de convite.
	"""
	import base64
	import urllib.parse

	from gris.festas.utils.convite_qr import gerar_png

	festa = (festa or "").strip()
	if not festa:
		frappe.throw(_("Festa é obrigatória."))

	ensure_user_pode_operar_portaria(festa)

	venda_ativa = frappe.db.get_value("Festa", festa, "venda_na_portaria")
	if not venda_ativa:
		frappe.throw(_("O modo 'Venda na portaria' não está ativo para esta festa."))

	host = frappe.utils.get_url().rstrip("/")
	# urlencode evita XSS/quebra para nomes de festa com espaços ou acentos.
	caminho = f"{PORTARIA_CONVITE_URL_BASE}?festa={urllib.parse.quote(festa, safe='')}"
	url = f"{host}{caminho}"

	png_bytes = gerar_png(url, com_logo=False)
	qr_b64 = base64.b64encode(png_bytes).decode("ascii")

	return {
		"url": url,
		"path": caminho,
		"qr_data_uri": f"data:image/png;base64,{qr_b64}",
		"preco": flt(
			frappe.db.get_value(
				"Opcao Convite Festa",
				{"festa": festa, "portaria": 1, "ativo": 1},
				"valor",
			)
		),
	}


_MEIOS_PAGAMENTO_PRESENCIAL = ("Dinheiro", "Cartão")


def _nome_completo(valor: str) -> bool:
	return len([p for p in (valor or "").split() if p]) >= 2


def _sanitizar_pagador_presencial(pagador) -> dict:
	if isinstance(pagador, str):
		try:
			pagador = frappe.parse_json(pagador) or {}
		except Exception:
			frappe.throw(_("Dados do pagador inválidos."))
	if not isinstance(pagador, dict):
		frappe.throw(_("Dados do pagador inválidos."))
	nome = (pagador.get("nome") or "").strip()
	if not nome:
		frappe.throw(_("Nome do pagador é obrigatório."))
	if not _nome_completo(nome):
		frappe.throw(_("Informe o nome completo do pagador (nome e sobrenome)."))
	email_raw = (pagador.get("email") or "").strip().lower()
	email: str | None = None
	if email_raw:
		if not EMAIL_REGEX.match(email_raw):
			frappe.throw(_("E-mail do pagador inválido."))
		email = email_raw
	telefone_digits = re.sub(r"\D", "", pagador.get("telefone") or "")
	telefone: str | None = telefone_digits or None
	return {"nome": nome, "email": email, "telefone": telefone}


def _sanitizar_convidados_presencial(convidados, quantidade: int) -> list[dict]:
	if isinstance(convidados, str):
		try:
			convidados = frappe.parse_json(convidados) or []
		except Exception:
			frappe.throw(_("Lista de convidados inválida."))
	if not isinstance(convidados, list):
		frappe.throw(_("Lista de convidados inválida."))
	if len(convidados) != quantidade:
		frappe.throw(_("Informe exatamente {0} convidado(s) (1 por convite).").format(quantidade))
	resultado: list[dict] = []
	for idx, item in enumerate(convidados, start=1):
		if not isinstance(item, dict):
			frappe.throw(_("Convidado #{0} inválido.").format(idx))
		nome = (item.get("nome") or "").strip()
		if not nome:
			frappe.throw(_("Convidado #{0} precisa de nome.").format(idx))
		if not _nome_completo(nome):
			frappe.throw(_("Convidado #{0}: informe o nome completo (nome e sobrenome).").format(idx))
		resultado.append({"nome": nome})
	return resultado


@frappe.whitelist()
@rate_limit(key="portaria-presencial", limit=30, seconds=60)
def criar_convite_presencial(
	festa: str,
	pagador,
	quantidade,
	meio_pagamento: str,
	convidados,
) -> dict:
	"""Registra uma venda presencial (dinheiro/cartão físico) na portaria.

	- Usa a Opcao Convite Festa ativa com `portaria=1` da festa selecionada.
	- ACL: somente quem opera a portaria da festa (System Manager, role
	  Portaria ou coordenador/membro da Area Portaria).
	- Não cria Cobranca Infinitepay e não dispara e-mail/WhatsApp; a
	  presença dos convidados é registrada automaticamente pelo
	  `after_insert` do Convite Festa.
	"""
	festa = (festa or "").strip()
	if not festa:
		frappe.throw(_("Festa é obrigatória."))

	ensure_user_pode_operar_portaria(festa)

	venda_ativa = frappe.db.get_value("Festa", festa, "venda_na_portaria")
	if not venda_ativa:
		frappe.throw(_("O modo 'Venda na portaria' não está ativo para esta festa."))

	meio_pagamento = (meio_pagamento or "").strip()
	if meio_pagamento not in _MEIOS_PAGAMENTO_PRESENCIAL:
		frappe.throw(_("Meio de pagamento inválido: escolha Dinheiro ou Cartão."))

	try:
		quantidade_int = int(quantidade)
	except (TypeError, ValueError):
		quantidade_int = 0
	if quantidade_int <= 0:
		frappe.throw(_("Informe uma quantidade válida (maior que zero)."))

	pagador_data = _sanitizar_pagador_presencial(pagador)
	convidados_data = _sanitizar_convidados_presencial(convidados, quantidade_int)

	opcao = frappe.db.get_value(
		"Opcao Convite Festa",
		{"festa": festa, "portaria": 1, "ativo": 1},
		["name", "valor"],
		as_dict=True,
	)
	if not opcao:
		frappe.throw(_("Não há Opção de Convite ativa do tipo Portaria para esta festa."))

	convite = frappe.get_doc(
		{
			"doctype": "Convite Festa",
			"festa": festa,
			"nome_pagador": pagador_data["nome"],
			"email_pagador": pagador_data["email"],
			"telefone_pagador": pagador_data["telefone"],
			"presencial": 1,
			"meio_pagamento": meio_pagamento,
			# Em venda presencial não enviamos e-mail/QR — mas mantemos a flag
			# para que `_aplicar_pagador_aos_convidados` não exija e-mail por
			# convidado.
			"pagador_recebe_qr_codes": 1,
			"itens": [
				{
					"eh_convite": 1,
					"opcao_convite": opcao.name,
					"quantidade": quantidade_int,
				}
			],
			"convidados": [{"nome": c["nome"]} for c in convidados_data],
		}
	)
	convite.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"ok": True,
		"convite_name": convite.name,
		"valor_total": flt(convite.valor_total),
		"meio_pagamento": convite.meio_pagamento,
	}
