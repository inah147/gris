import re
import unicodedata

import frappe
from frappe import _

from gris.api.financeiro.contribuicoes import CATEGORIAS_CONTRIBUINTES
from gris.api.portal_access import enrich_context
from gris.api.portal_cache_utils import get_uel_cached

no_cache = 1


def _levenshtein(s, t):
	"""Distância de Levenshtein entre duas strings."""
	n, m = len(s), len(t)
	if n == 0:
		return m
	if m == 0:
		return n
	prev = list(range(m + 1))
	for i in range(1, n + 1):
		curr = [i] + [0] * m
		for j in range(1, m + 1):
			cost = 0 if s[i - 1] == t[j - 1] else 1
			curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
		prev = curr
	return prev[m]


def _normalizar(texto):
	"""Lowercase e remove acentos."""
	if not texto:
		return ""
	texto = texto.lower()
	texto = unicodedata.normalize("NFD", texto)
	texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
	return texto


def _limpar_descricao(descricao):
	"""Remove trechos de Pix e normaliza a descrição."""
	if not descricao:
		return ""
	texto = descricao
	# Remover trechos (case insensitive) — ordem importa: mais longo primeiro
	texto = re.sub(r"(?i)pix recebido de\s*", "", texto)
	texto = re.sub(r"(?i)pix\s+", "", texto)
	return _normalizar(texto.strip())


def _nome_distancia(nome_completo, descricao_limpa):
	"""Retorna a menor distância de similaridade ou None se não houver semelhança.

	Valores menores indicam maior proximidade.
	"""
	if not nome_completo or not descricao_limpa:
		return None

	nome_norm = _normalizar(nome_completo)
	partes_nome = nome_norm.split()
	palavras_desc = descricao_limpa.split()

	if not partes_nome or not palavras_desc:
		return None

	melhor = None

	# Etapa 1: primeiro nome vs cada palavra da descrição
	primeiro_nome = partes_nome[0]
	threshold_primeiro = max(1, len(primeiro_nome) // 3)
	for palavra in palavras_desc:
		d = _levenshtein(primeiro_nome, palavra)
		if d <= threshold_primeiro and (melhor is None or d < melhor):
			melhor = d

	# Etapa 2: nome completo vs descrição inteira
	threshold_completo = int(len(nome_norm) * 0.4)
	d = _levenshtein(nome_norm, descricao_limpa)
	if d <= threshold_completo and (melhor is None or d < melhor):
		melhor = d

	return melhor


def _buscar_sugestoes_contribuicao(doc):
	"""Retorna até 5 Associados cuja contribuição mensal pode corresponder à transação."""
	if not doc.descricao or not doc.valor:
		return []

	try:
		valor_transacao = float(doc.valor)
	except (ValueError, TypeError):
		return []

	descricao_limpa = _limpar_descricao(doc.descricao)
	if not descricao_limpa:
		return []

	# Buscar contribuintes com valor de contribuição preenchido
	beneficiarios = frappe.get_all(
		"Associado",
		filters={
			"categoria": ["in", list(CATEGORIAS_CONTRIBUINTES)],
			"valor_contribuicao": [">", 0],
		},
		fields=["name", "nome_completo", "valor_contribuicao"],
	)

	# Filtrar por valor próximo (±R$1)
	candidatos_valor = [
		b for b in beneficiarios if abs(valor_transacao - float(b.valor_contribuicao or 0)) <= 1.0
	]

	if not candidatos_valor:
		return []

	# Buscar todos os vínculos de responsáveis em batch
	nomes_associados = [b.name for b in candidatos_valor]
	vinculos = frappe.get_all(
		"Responsavel Vinculo",
		filters={"beneficiario_associado": ["in", nomes_associados]},
		fields=["beneficiario_associado", "responsavel"],
	)

	# Buscar nomes dos responsáveis em batch
	resp_ids = list({v.responsavel for v in vinculos if v.responsavel})
	resp_nomes = {}
	if resp_ids:
		for r in frappe.get_all(
			"Responsavel",
			filters={"name": ["in", resp_ids]},
			fields=["name", "nome_completo"],
		):
			resp_nomes[r.name] = r.nome_completo

	# Mapear responsáveis por associado
	resp_por_associado = {}
	for v in vinculos:
		resp_por_associado.setdefault(v.beneficiario_associado, []).append(resp_nomes.get(v.responsavel, ""))

	candidatos_com_score = []
	for b in candidatos_valor:
		melhor_dist = None

		# Verificar nome do próprio beneficiário
		d = _nome_distancia(b.nome_completo, descricao_limpa)
		if d is not None:
			melhor_dist = d

		# Verificar nomes dos responsáveis
		nomes_resp = resp_por_associado.get(b.name, [])
		for nome_resp in nomes_resp:
			d = _nome_distancia(nome_resp, descricao_limpa)
			if d is not None and (melhor_dist is None or d < melhor_dist):
				melhor_dist = d

		if melhor_dist is not None:
			candidatos_com_score.append(
				{"name": b.name, "nome_completo": b.nome_completo, "dist": melhor_dist}
			)

	# Ordenar por proximidade (menor distância primeiro) e limitar a 5
	candidatos_com_score.sort(key=lambda c: c["dist"])
	return [{"name": c["name"], "nome_completo": c["nome_completo"]} for c in candidatos_com_score[:5]]


def get_context(context):
	# Bloqueio para usuários não autenticados
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/financeiro/extrato"
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

	context.active_link = "/financeiro/extrato"
	enrich_context(context, "/financeiro/extrato")
	context.show_sidebar = True
	context.no_cache = 1
	context.title = _("Detalhe de transação")

	# Adiciona opções de dropdown
	def get_distinct(doctype, field):
		return [
			r[field]
			for r in frappe.get_all(doctype, fields=[field], distinct=True, order_by=field)
			if r[field]
		]

	context.opcoes_categoria = get_distinct("Categoria de Transacao", "name")
	context.opcoes_centro_de_custo = get_distinct("Centro de Custo", "name")
	context.opcoes_conta_fixa = get_distinct("Conta Fixa", "name")

	# Beneficiários: associados das categorias que contribuem (Dirigente e Escotista não pagam).
	context.opcoes_beneficiario = [
		{"name": r["name"], "nome_completo": r.get("nome_completo", r["name"])}
		for r in frappe.get_all(
			"Associado",
			fields=["name", "nome_completo", "categoria"],
			filters={"categoria": ["in", list(CATEGORIAS_CONTRIBUINTES)]},
			order_by="nome_completo",
		)
	]

	context.opcoes_fixo_variavel = ["Fixo", "Variável"]
	context.opcoes_ordinaria_extraordinaria = ["Ordinária", "Extraordinária"]

	name = frappe.form_dict.get("name")
	if not name:
		context.not_found = True
		context.missing_reason = "Parâmetro 'name' não informado."
		return context

	try:
		doc = frappe.get_doc("Transacao Extrato Geral", name)
	except frappe.DoesNotExistError:
		context.not_found = True
		context.missing_reason = "Transação não encontrada."
		return context
	except Exception as e:
		context.not_found = True
		context.missing_reason = f"Erro ao carregar transação: {e}"
		return context

	context.doc = doc

	# Sugestões de contribuição mensal (somente se não revisada)
	context.sugestoes_contribuicao = []
	if not doc.transacao_revisada:
		context.sugestoes_contribuicao = _buscar_sugestoes_contribuicao(doc)

	# Filtrar contas fixas já pagas no mês
	if doc.data_transacao:
		from frappe.utils import getdate

		data_t = getdate(doc.data_transacao)
		mes_ref = data_t.replace(day=1)

		# 1. Encontrar pagamentos que já foram realizados (Pago) neste mês
		# ou estão vinculados a outras transações (independente se o pagamento estivesse 'Em Aberto',
		# se já tem transação vinculada, não deve aparecer de novo)

		# Vamos pela abordagem de transações já existentes no mês:
		# Encontrar todas as transações deste mês que têm conta_fixa preenchido
		primeiro_dia = mes_ref
		import calendar

		ultimo_dia = mes_ref.replace(day=calendar.monthrange(mes_ref.year, mes_ref.month)[1])

		used_accounts = frappe.get_all(
			"Transacao Extrato Geral",
			filters={
				"data_transacao": ["between", [primeiro_dia, ultimo_dia]],
				"conta_fixa": ["is", "set"],
				"name": ["!=", doc.name],  # Excluir a própria transação
			},
			pluck="conta_fixa",
		)

		# Remover das opções
		if used_accounts:
			# context.opcoes_conta_fixa é uma lista de strings (names)
			context.opcoes_conta_fixa = [op for op in context.opcoes_conta_fixa if op not in used_accounts]

	return context
