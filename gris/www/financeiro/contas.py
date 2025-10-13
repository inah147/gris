import os
from urllib.parse import urlparse

import frappe
from frappe.utils import fmt_money, formatdate

from gris.api.financeiro.infinitepay import (
	bank_reconcilliation,
	get_infinitepay_bank_statement_df,
	get_infinitepay_receipts_df,
	get_infinitepay_sales_df,
)
from gris.api.portal_access import enrich_context, user_has_access
from gris.api.portal_cache_utils import get_uel_cached


def _get_method_infinitepay(method):
	if method is None:
		return "Outro"
	try:
		m = str(method)
	except Exception:
		return "Outro"
	mu = m.upper()
	if mu == "PIX":
		return "Pix"
	if mu == "DEPÓSITO DE VENDAS":
		return "Depósito de vendas"
	if mu == "BOLETO":
		return "Boleto"
	if mu in ("CRÉDITO", "DÉBITO"):
		return "Cartão"
	if mu in ("DINHEIRO"):
		return "Dinheiro"
	return "Outro"


def _get_monthly_payment_data_infinitepay(tipo_origem, valor):
	if tipo_origem == "Gestão de Cobrança" or tipo_origem == "Conta Inteligente":
		if valor >= 59.99 and valor <= 60.01:
			return {
				"categoria": "Contribuição Mensal",
				"fixo_variavel": "Fixo",
				"centro_de_custo": "Presidência",
				"ordinaria_extraordinaria": "Ordinária",
			}
	return {
		"categoria": None,
		"fixo_variavel": None,
		"centro_de_custo": None,
		"ordinaria_extraordinaria": None,
	}


def _get_inner_account_transfer_infinitepay(description):
	if "GRUPO ESCOTEIRO PROFESSORA INAH DE MELO N 147" in description:
		return {"categoria": "Transferência entre Contas", "repasse_entre_contas": 1}
	return {"categoria": None, "repasse_entre_contas": 0}


@frappe.whitelist()
def process_uploaded_files(extrato_file_url, vendas_file_url, recebimentos_file_url):
	# Permissão: apenas usuários com permissão de criação/edição nos doctypes afetados
	required_doctypes = [
		"Transacao Infinitepay extrato",
		"Transacao Infinitepay vendas",
		"Transacao Infinitepay recebimento",
		"Transacao Extrato Geral",
	]
	for dt in required_doctypes:
		if not frappe.has_permission(dt, ptype="create") or not frappe.has_permission(dt, ptype="write"):
			frappe.throw(
				f"Sem permissão para conciliação: requer criar/editar em '{dt}'.",
				frappe.PermissionError,
			)

	# Helpers para normalizar valores provenientes de pandas (NaN/NaT) e compor strings
	def nv(v):
		# Retorna None se v é NaN/NaT
		try:
			if v is None:
				return None
			# NaN/NaT comparações não são iguais a si próprios
			if v != v:
				return None
		except Exception:
			pass
		return v

	def s(v):
		v = nv(v)
		return str(v) if v is not None else ""

	def abs_or_none(v):
		v = nv(v)
		try:
			return abs(v)
		except Exception:
			return None

	def _resolve_path(file_url: str) -> str:
		"""Converte a file_url (public ou private) em caminho absoluto correto.

		Casos:
		- /files/xxx -> sites/<site>/public/files/xxx
		- /private/files/xxx -> sites/<site>/private/files/xxx
		- qualquer outro -> assume public/<file_url>
		"""
		if not file_url:
			return ""
		file_url = file_url.strip()
		if file_url.startswith("/private/files/"):
			return frappe.get_site_path(file_url.lstrip("/"))  # já aponta para private/files
		if file_url.startswith("/files/"):
			# remover prefixo /files/ e apontar para public/files
			inner = file_url.split("/files/", 1)[1]
			return frappe.get_site_path("public", "files", inner)
		# fallback: tratar como relativo a public
		return frappe.get_site_path("public", file_url.lstrip("/"))

	extrato_path = _resolve_path(extrato_file_url)
	vendas_path = _resolve_path(vendas_file_url)
	recebimentos_path = _resolve_path(recebimentos_file_url)
	try:
		# Validação de existência
		missing = [
			p
			for p in [
				("extrato", extrato_path),
				("vendas", vendas_path),
				("recebimentos", recebimentos_path),
			]
			if not (p[1] and os.path.exists(p[1]))
		]
		if missing:
			msgs = ", ".join(f"{k}: {v}" for k, v in missing)
			raise FileNotFoundError(f"Arquivos não encontrados -> {msgs}")

		# Extrai dataframes dos arquivos
		df_extrato = get_infinitepay_bank_statement_df(extrato_path)
		df_vendas = get_infinitepay_sales_df(vendas_path)
		df_recebimentos = get_infinitepay_receipts_df(recebimentos_path)
		# Ordem correta: extrato (bank_statement), recebimentos (receipts), vendas (sales)
		df_geral = bank_reconcilliation(df_extrato, df_recebimentos, df_vendas)

		# Estatísticas de inserção
		stats = {
			"extrato": {"total": len(df_extrato), "inserted": 0, "skipped_exist": 0, "failed": 0},
			"vendas": {"total": len(df_vendas), "inserted": 0, "skipped_exist": 0, "failed": 0},
			"recebimentos": {"total": len(df_recebimentos), "inserted": 0, "skipped_exist": 0, "failed": 0},
			# total de geral será incrementado conforme tentativas (debitos do extrato + df_geral)
			"geral": {"total": 0, "inserted": 0, "skipped_exist": 0, "failed": 0},
		}

		# Coleta de erros por doctype para diagnóstico
		errors = {"extrato": [], "vendas": [], "recebimentos": [], "geral": []}

		def _capture_error(section: str, identity: str, exc: Exception):
			try:
				msg = f"{identity} -> {exc!s}"
			except Exception:
				msg = str(exc)
			errors[section].append(msg)
			try:
				frappe.log_error(msg, f"Importação Infinitepay - {section}")
			except Exception:
				pass

		# Insere linhas do extrato (todos os campos)
		for _, row in df_extrato.iterrows():
			# Extrato Infinitepay
			try:
				filters = {}
				if row.get("fitid"):
					filters = {"id": row.get("fitid")}
				if filters and frappe.db.exists("Transacao Infinitepay extrato", filters):
					stats["extrato"]["skipped_exist"] += 1
				else:
					doc = frappe.get_doc(
						{
							"doctype": "Transacao Infinitepay extrato",
							"data_transacao": nv(row.get("date")),
							"tipo_transacao": s(row.get("transaction_type")),
							"nome_transacao": s(row.get("memo")),
							"detalhe": s(row.get("name")),
							"valor": nv(row.get("value")),
							"id": s(row.get("fitid")),
							"tipo": s(row.get("type")),
						}
					)
					doc.insert(ignore_permissions=False)
					stats["extrato"]["inserted"] += 1
			except Exception as e:
				stats["extrato"]["failed"] += 1
				_capture_error("extrato", row.get("fitid") or row.get("name") or "sem-id", e)

		# Insere linhas das vendas (todos os campos)
		for _, row in df_vendas.iterrows():
			try:
				filters = {}
				if row.get("infinite_id"):
					filters = {"infinite_id": row.get("infinite_id")}
				if filters and frappe.db.exists("Transacao Infinitepay vendas", filters):
					stats["vendas"]["skipped_exist"] += 1
				else:
					doc = frappe.get_doc(
						{
							"doctype": "Transacao Infinitepay vendas",
							"data_hora": nv(row.get("data_hora")),
							"meio_meio": s(row.get("meio_meio")),
							"meio_bandeira": s(row.get("meio_bandeira")),
							"meio_parcelas": s(row.get("meio_parcelas")),
							"tipo_origem": s(row.get("tipo_origem")),
							"tipo_dados_adicionais": s(row.get("tipo_dados_adicionais")),
							"identificador": s(row.get("identificador")),
							"status": s(row.get("status")),
							"valor": nv(row.get("valor")),
							"valor_liquido": nv(row.get("valor_liquido")),
							"taxa_aplicada": nv(row.get("taxa_aplicada")),
							"taxa_aplicada_perc": nv(row.get("taxa_aplicada_perc")),
							"plano": s(row.get("plano")),
							"infinite_id": s(row.get("infinite_id")),
							"origem_nome": s(row.get("origem_nome")),
						}
					)
					doc.insert(ignore_permissions=False)
					stats["vendas"]["inserted"] += 1
			except Exception as e:
				stats["vendas"]["failed"] += 1
				_capture_error("vendas", row.get("infinite_id") or row.get("identificador") or "sem-id", e)

		# Insere linhas dos recebimentos (todos os campos)
		for _, row in df_recebimentos.iterrows():
			try:
				filters = {}
				if row.get("infinite_id") is not None and row.get("numero_parcela") is not None:
					filters = {
						"infinite_id": row.get("infinite_id"),
						"numero_parcela": row.get("numero_parcela"),
					}
				elif row.get("infinite_id") is not None:
					filters = {"infinite_id": row.get("infinite_id")}
				if filters and frappe.db.exists("Transacao Infinitepay recebimento", filters):
					stats["recebimentos"]["skipped_exist"] += 1
				else:
					doc = frappe.get_doc(
						{
							"doctype": "Transacao Infinitepay recebimento",
							"infinite_id": s(row.get("infinite_id")),
							"origem": s(row.get("origem")),
							"data_venda": nv(row.get("data_venda")),
							"autorizacao": s(row.get("autorizacao")),
							"bandeira": s(row.get("bandeira")),
							"tipo": s(row.get("tipo")),
							"valor": nv(row.get("valor")),
							"total_parcelas": nv(row.get("total_parcelas")),
							"numero_parcela": nv(row.get("numero_parcela")),
							"valor_parcela": nv(row.get("valor_parcela")),
							"valor_parcela_liquido": nv(row.get("valor_parcela_liquido")),
							"valor_parcela_recebido": nv(row.get("valor_parcela_recebido")),
							"status": s(row.get("status")),
							"data_deposito": nv(row.get("data_deposito")),
							"numero_liquidacao": s(row.get("numero_liquidacao")),
							"antecipada": nv(row.get("antecipada")),
						}
					)
					doc.insert(ignore_permissions=False)
					stats["recebimentos"]["inserted"] += 1
			except Exception as e:
				stats["recebimentos"]["failed"] += 1
				_capture_error(
					"recebimentos",
					f"{row.get('infinite_id')}-{row.get('numero_parcela')}"
					if row.get("numero_parcela") is not None
					else str(row.get("infinite_id")),
					e,
				)

		for _, row in df_geral.iterrows():
			stats["geral"]["total"] += 1
			try:
				mpd = _get_monthly_payment_data_infinitepay(
					s(row.get("tipo_origem")), nv(row.get("valor_liquido"))
				)
				filters = {}
				if row.get("infinite_id"):
					filters = {"id": row.get("infinite_id")}
				if filters and frappe.db.exists("Transacao Extrato Geral", filters):
					stats["geral"]["skipped_exist"] += 1
				else:
					doc = frappe.get_doc(
						{
							"doctype": "Transacao Extrato Geral",
							"timestamp_transacao": nv(row.get("data_hora")),
							"data_transacao": (
								nv(row.get("data_hora")).date()
								if hasattr(nv(row.get("data_hora")), "date")
								else None
							),
							"descricao": f"Pagamento em {s(row.get('meio_meio'))} de {s(row.get('origem_nome'))}",
							"valor": nv(row.get("valor_liquido")),
							"valor_absoluto": abs_or_none(row.get("valor_liquido")),
							"debito_credito": (
								"Crédito" if s(row.get("type")).lower() == "credit" else "Débito"
							),
							"origem": s(row.get("origem_nome")),
							"instituicao": "Infinitepay",
							"observações": None,
							"descricao_reduzida": mpd["categoria"]
							if mpd["categoria"]
							else f"Pagamento em {s(row.get('meio_meio'))}",
							"metodo": _get_method_infinitepay(s(row.get("meio_meio"))),
							"destino": "GRUPO ESCOTEIRO PROFESSORA INAH DE MELO N 147. - INFINITEPAY",
							"carteira": "Infinitepay",
							"id": s(row.get("infinite_id")),
							"categoria": mpd["categoria"],
							"fixo_variavel": mpd["fixo_variavel"],
							"conta_fixa": None,
							"beneficiario": None,
							"centro_de_custo": mpd["centro_de_custo"],
							"ordinaria_extraordinaria": mpd["ordinaria_extraordinaria"],
							"data_deposito": nv(row.get("data_deposito")),
							"numero_liquidacao": s(row.get("numero_liquidacao")),
							"repasse_entre_contas": 0,
							"transacao_revisada": 0,
						}
					)
					doc.insert(ignore_permissions=False)
					stats["geral"]["inserted"] += 1
			except Exception as e:
				stats["geral"]["failed"] += 1
				_capture_error("geral", str(row.get("infinite_id")) or "sem-id", e)

		# Monta resumo
		def line(title, s):
			return f"- {title}: total {s['total']}, inseridas {s['inserted']}, já existiam {s['skipped_exist']}, erro {s['failed']}"

		def _error_section_lines(section_title: str, items: list[str]):
			if not items:
				return []
			max_show = 5
			shown = items[:max_show]
			lines = [f"  • {it}" for it in shown]
			if len(items) > max_show:
				lines.append(f"  • (+{len(items) - max_show} outras… ver Error Log)")
			return lines

		resumo = [
			"Resumo da importação:",
			line("Transacao Infinitepay extrato", stats["extrato"]),
			*_error_section_lines("Extrato", errors["extrato"]),
			line("Transacao Infinitepay vendas", stats["vendas"]),
			*_error_section_lines("Vendas", errors["vendas"]),
			line("Transacao Infinitepay recebimento", stats["recebimentos"]),
			*_error_section_lines("Recebimentos", errors["recebimentos"]),
			line("Transacao Extrato Geral", stats["geral"]),
			*_error_section_lines("Extrato Geral", errors["geral"]),
			"(Detalhes adicionais em: Error Log)",
		]
		return {
			"summary_text": "\n".join(resumo),
			"stats": stats,
			"errors": errors,
		}
	except Exception as e:
		frappe.log_error(str(e), "Erro ao processar arquivos importados")
		return {
			"summary_text": f"Erro ao processar arquivos: {e!s}",
			"stats": None,
			"errors": {"extrato": [], "vendas": [], "recebimentos": [], "geral": []},
		}


no_cache = 1


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/financeiro/contas"
		raise frappe.Redirect
	# Recupera logo e define para sidebar
	uel_data = get_uel_cached()
	if uel_data:
		context.portal_logo = uel_data.get("logo")
		if uel_data.get("nome_da_uel"):
			context.sidebar_title = f"{uel_data.get('tipo_uel')} {uel_data.get('nome_da_uel')}"
		else:
			context.sidebar_title = "Portal"
	else:
		context.sidebar_title = "Portal"
	context.active_link = "/financeiro/contas"
	enrich_context(context, "/financeiro/contas")

	# Dados de Contas (Instituições Financeiras)
	try:
		context.can_create_instituicao = frappe.has_permission("Instituicao Financeira", "create")
	except Exception:
		context.can_create_instituicao = False
	try:
		context.can_create_carteira = frappe.has_permission("Carteira", "create")
	except Exception:
		context.can_create_carteira = False
	contas_raw = frappe.get_all(
		"Instituicao Financeira",
		fields=["name", "nome"],
		order_by="nome asc",
	)
	context.contas = [
		{
			"name": c.get("name"),
			"display_name": c.get("nome") or c.get("name"),
		}
		for c in contas_raw
	]

	# Dados de Carteiras
	carteiras_raw = frappe.get_all(
		"Carteira",
		fields=[
			"name",
			"nome",
			"saldo",
			"data_atualizacao",
			# Tentamos ambos possíveis nomes (sem e com acento) se existirem
			"instituicao_financeira",
			"descricao",
			"responsavel",
			"chave_pix",
			"centro_de_custo",
		],
		order_by="nome asc",
	)
	carteiras = []
	# Mapeamento simples instituição -> variante de badge
	# variant_map agora mapeia substring -> (variant, outline_bool)
	variant_map = {
		"btg empresas": ("primary", False),
		"btg investimentos": ("primary", True),
		"portão 3": ("purple", False),
		"portao 3": ("purple", False),
		"inifinitepay": ("success", False),  # grafia presente no fixture
		"infinitepay": ("success", False),  # grafia alternativa
		"pagbank": ("warning", False),
	}
	for cart in carteiras_raw:
		saldo = cart.get("saldo") or 0
		# Campo pode ter sido criado com ou sem acento; fazemos fallback
		inst = cart.get("instituicao_financeira") or ""
		inst_slug = inst.lower()
		variant = None
		outline = False
		for key, v in variant_map.items():
			if key in inst_slug:
				variant, outline = v
				break
		if not variant:
			variant = "neutral"
		badge_classes = f"g-badge g-badge--{variant} g-badge--small"
		if outline:
			badge_classes = f"{badge_classes} g-badge--outline"
		carteiras.append(
			{
				"name": cart.get("name"),
				"display_name": cart.get("nome") or cart.get("name"),
				"instituicao_financeira": cart.get("instituicao_financeira"),
				"instituicao_variant": variant,
				"instituicao_badge_classes": badge_classes,
				"instituicao_badge_outline": outline,
				"descricao": cart.get("descricao") or "",
				"responsavel": cart.get("responsavel") or "",
				"chave_pix": cart.get("chave_pix") or "",
				"centro_de_custo": cart.get("centro_de_custo") or "",
				"saldo": saldo,
				"saldo_formatado": fmt_money(saldo) if saldo is not None else fmt_money(0),
				"data_atualizacao": cart.get("data_atualizacao"),
				"data_atualizacao_formatada": formatdate(cart.get("data_atualizacao"))
				if cart.get("data_atualizacao")
				else None,
			}
		)
	context.carteiras = carteiras
	return context
