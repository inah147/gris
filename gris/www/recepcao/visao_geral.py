import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import format_date, format_datetime, getdate

from gris.api.portal_access import enrich_context
from gris.api.recepcao import formatar_idade, numeros_de_registro_pendentes
from gris.api.recepcao_funil import (
	CAMPOS_DE_EFETIVACAO,
	COLUNAS_DE_ACOMPANHAMENTO,
	FIELD_INTERVAL_MAP,
	STATUS_ACOMPANHAMENTO,
	STEPS_DEF,
	anexar_historico,
	calcular_etapas,
	carregar_configuracao,
	coluna_de_acompanhamento,
)

no_cache = 1

RAMOS = ["Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"]

# Valor sentinela do filtro de ramo para cards ainda sem ramo definido
RAMO_FILTRO_SEM_RAMO = "__sem_ramo__"

# Etapas que também movem a coluna do funil ao serem concluídas.
#
# A regra existia espalhada pelos pontos de entrada — ``confirmar_registro_paxtu`` aqui,
# ``gris.api.recepcao.registrar_recepcao_realizada`` e ``gris.www.responsavel.registro`` —
# e a bolinha da timeline não passava por nenhum deles: marcava a etapa e deixava o card
# parado na coluna antiga. Centralizar em ``update_step_status``, por onde todos os
# caminhos passam, é o que mantém etapa e status em sincronia.
#
# Desmarcar não reverte o status: voltar de coluna é decisão explícita da recepção.
STATUS_POR_ETAPA = {
	"primeira_visita_realizada": "Aguardar Dados",
	"dados_para_registro_enviados": "Fazer Registro",
	"registro_criado_no_paxtu": "Acompanhamento",
}


def _normalize_whatsapp_phone(phone):
	if not phone:
		return None

	cleaned = re.sub(r"\D", "", str(phone))
	if not cleaned:
		return None

	if cleaned.startswith("55"):
		normalized = cleaned
	elif len(cleaned) in {10, 11}:
		normalized = f"55{cleaned}"
	else:
		normalized = cleaned

	if len(normalized) < 12:
		return None

	return normalized


def _historico_de_etapas(nomes: list[str]) -> dict[str, dict[str, dict]]:
	"""Mapa ``Novo Associado`` -> etapa -> ``{"concluida_em", "concluido_por"}``.

	Uma consulta na tabela filha inteira em vez de abrir um documento por card do
	kanban.
	"""
	if not nomes:
		return {}

	historico: dict[str, dict[str, dict]] = {}
	linhas = frappe.get_all(
		"Etapa do Fluxo Concluida",
		filters={"parenttype": "Novo Associado", "parent": ["in", nomes]},
		fields=["parent", "etapa", "concluida_em", "concluido_por"],
	)
	for linha in linhas:
		historico.setdefault(linha.parent, {})[linha.etapa] = {
			"concluida_em": linha.concluida_em,
			"concluido_por": linha.concluido_por,
		}
	return historico


def get_context(context):
	# Disable cache to always show fresh data
	context.no_cache = 1

	context.active_link = "/recepcao"
	enrich_context(context, "/recepcao")

	# Colunas do kanban. As duas últimas são as duas faces do mesmo status
	# "Acompanhamento": a separação sai de ``coluna_de_acompanhamento`` e não do
	# campo ``status``, então o card migra sozinho da lista provisória para a
	# definitiva quando o registro provisório é efetivado.
	colunas = [
		"Novo Contato",
		"Conversa Inicial",
		"Visita Agendada",
		"Aguardar Dados",
		"Fazer Registro",
		*COLUNAS_DE_ACOMPANHAMENTO,
	]

	# Intervalos entre etapas (mesma regra usada pela integração MCP)
	config = carregar_configuracao()
	field_interval_map = FIELD_INTERVAL_MAP

	# Fields to fetch for Novo Associado
	fields_to_fetch = [
		"name",
		"nome_completo",
		"data_de_nascimento",
		"status",
		"ramo",
		"owner",
		"responsavel_recepcao",
		"tipo_de_registro",
		"numero_de_registro",
		"visita_agendada",
		"primeira_visita_realizada",
		*field_interval_map.keys(),
	]

	novos_associados = frappe.get_all(
		"Novo Associado",
		fields=fields_to_fetch,
		order_by="modified desc",
	)

	# Bulk Data Fetching
	names = [na.name for na in novos_associados]

	# Fetch Visits
	visits_map = {}
	if names:
		all_visits = frappe.get_all(
			"Agenda de Visitas",
			filters={"jovem": ["in", names]},
			fields=["jovem", "data_da_visita", "visita_confirmada"],
			order_by="data_da_visita desc",
		)
		# Process visits to map by jovem (taking the latest one because of order_by)
		for v in all_visits:
			if v.jovem not in visits_map:
				visits_map[v.jovem] = v

	# Fetch Responsavel Vinculo + contatos WhatsApp
	responsavel_map = {}
	whatsapp_contatos_map = {}
	if names:
		links = frappe.get_all(
			"Responsavel Vinculo",
			filters={"beneficiario_novo_associado": ["in", names]},
			fields=["beneficiario_novo_associado", "responsavel", "é_guardiao_legal", "primeiro_responsavel"],
		)

		resp_ids = {l.get("responsavel") for l in links if l.get("responsavel")}
		resp_info_map = {}
		if resp_ids:
			resps = frappe.get_all(
				"Responsavel",
				filters={"name": ["in", list(resp_ids)]},
				fields=["name", "nome_completo", "celular", "telefone_secundario"],
			)
			resp_info_map = {r.name: r for r in resps}

		links_by_associado = {}
		for link in links:
			associado_name = link.get("beneficiario_novo_associado")
			if not associado_name:
				continue
			links_by_associado.setdefault(associado_name, []).append(link)

		for associado_name, associado_links in links_by_associado.items():
			ordered_links = sorted(
				associado_links,
				key=lambda link: (
					1 if link.get("é_guardiao_legal") else 0,
					1 if link.get("primeiro_responsavel") else 0,
				),
				reverse=True,
			)

			contatos = []
			seen_responsaveis = set()

			for link in ordered_links:
				responsavel_id = link.get("responsavel")
				if not responsavel_id or responsavel_id in seen_responsaveis:
					continue

				resp_info = resp_info_map.get(responsavel_id)
				if not resp_info:
					continue

				if associado_name not in responsavel_map:
					responsavel_map[associado_name] = resp_info.get("nome_completo")

				phone = resp_info.get("celular") or resp_info.get("telefone_secundario")
				normalized_phone = _normalize_whatsapp_phone(phone)

				if normalized_phone:
					contatos.append(
						{
							"responsavel": responsavel_id,
							"nome": resp_info.get("nome_completo") or responsavel_id,
							"telefone": normalized_phone,
							"is_guardiao_legal": bool(link.get("é_guardiao_legal")),
						}
					)

				seen_responsaveis.add(responsavel_id)

			whatsapp_contatos_map[associado_name] = contatos

	# Observações (Comment) por associado, para o balão do card. Uma consulta agregada:
	# o conteúdo só é carregado quando alguém abre o dialog.
	observacoes_map = {}
	if names:
		observacoes_map = {
			linha.reference_name: linha.total
			for linha in frappe.get_all(
				"Comment",
				filters={
					"reference_doctype": "Novo Associado",
					"reference_name": ["in", names],
					"comment_type": "Comment",
				},
				fields=["reference_name", "count(name) as total"],
				group_by="reference_name",
			)
		}

	# Quem concluiu cada etapa e quando, para o ícone de informação da timeline.
	# Uma consulta na tabela filha inteira, em vez de abrir um documento por card.
	historico_map = _historico_de_etapas(names)

	# Fetch User Names
	user_names_map = {}
	user_ids = set(n.responsavel_recepcao for n in novos_associados if n.responsavel_recepcao)
	# Os autores das conclusões também precisam do nome legível para a dica.
	user_ids.update(
		linha["concluido_por"]
		for etapas in historico_map.values()
		for linha in etapas.values()
		if linha.get("concluido_por")
	)
	if user_ids:
		users = frappe.get_all("User", filters={"name": ["in", list(user_ids)]}, fields=["name", "full_name"])
		user_names_map = {u.name: (u.full_name or u.name) for u in users}

	# Map for Ramo CSS classes
	ramo_map = {
		"Filhotes": "filhotes",
		"Lobinho": "lobinho",
		"Escoteiro": "escoteiro",
		"Sênior": "senior",
		"Pioneiro": "pioneiro",
	}

	# Variantes do badge Basecoat (corresponde a .badge-ramo-* no CSS local)
	ramo_variant_map = {
		"Filhotes": "ramo-filhotes",
		"Lobinho": "ramo-lobinho",
		"Escoteiro": "ramo-escoteiro",
		"Sênior": "ramo-senior",
		"Pioneiro": "ramo-pioneiro",
	}

	# Group by status
	kanban_data = {coluna: [] for coluna in colunas}

	today = getdate()

	for associado in novos_associados:
		coluna = (
			coluna_de_acompanhamento(associado)
			if associado.status == STATUS_ACOMPANHAMENTO
			else associado.status
		)

		if coluna in kanban_data:
			# Get visit info from map
			visit_rec = visits_map.get(associado.name)

			# Use visit date if available as base, regardless of confirmation status
			# This ensures we have a base date for calculations
			base_date = visit_rec.data_da_visita if visit_rec else None

			# Process steps
			associado.steps = calcular_etapas(associado, config, base_date, today)
			anexar_historico(associado.steps, historico_map.get(associado.name, {}))
			for etapa in associado.steps:
				autor = etapa.get("concluido_por")
				if autor:
					etapa["concluido_por_nome"] = user_names_map.get(autor, autor)
				if etapa.get("concluida_em"):
					etapa["concluida_em_formatada"] = format_datetime(
						etapa["concluida_em"], "dd/MM/yyyy HH:mm"
					)

			associado.steps_json = json.dumps(associado.steps, default=str)

			# Get Responsavel Recepcao name
			if associado.responsavel_recepcao:
				associado.recepcao_name = user_names_map.get(associado.responsavel_recepcao, "Não atribuído")
			else:
				associado.recepcao_name = "Não atribuído"

			# Get Responsavel pelo Associado
			associado.responsavel_associado = responsavel_map.get(associado.name)

			# WhatsApp contacts
			associado.whatsapp_contatos = whatsapp_contatos_map.get(associado.name, [])
			associado.whatsapp_contatos_json = json.dumps(associado.whatsapp_contatos, default=str)
			associado.whatsapp_disponivel = bool(associado.whatsapp_contatos)
			associado.whatsapp_motivo_indisponivel = (
				None if associado.whatsapp_disponivel else "Sem telefone de responsável"
			)

			# Visit info
			associado.visita_confirmada = bool(visit_rec.visita_confirmada) if visit_rec else False
			associado.visita_data = (
				format_date(visit_rec.data_da_visita) if visit_rec and visit_rec.data_da_visita else None
			)

			# Idade recalculada a cada carregamento da página
			associado.idade = formatar_idade(associado.data_de_nascimento)

			associado.observacoes_count = observacoes_map.get(associado.name, 0)

			# Set ramo class
			associado.ramo_class = ramo_map.get(associado.ramo, "default")
			associado.ramo_variant = ramo_variant_map.get(associado.ramo, "secondary")

			kanban_data[coluna].append(associado)

	context.kanban_columns = colunas
	context.kanban_data = kanban_data
	# As duas listas de acompanhamento abrem o mesmo dialog; o template precisa
	# saber quais colunas são elas para marcar os cards.
	context.colunas_de_acompanhamento = list(COLUNAS_DE_ACOMPANHAMENTO)

	# Fetch users with role 'Recepcao'
	recepcao_role_users = frappe.get_all("Has Role", filters={"role": "Recepcao"}, fields=["parent"])
	user_names_list = [r.parent for r in recepcao_role_users]

	if user_names_list:
		context.recepcao_users = frappe.get_all(
			"User",
			filters={"name": ["in", user_names_list], "enabled": 1},
			fields=["name", "full_name"],
			order_by="full_name asc",
		)
	else:
		context.recepcao_users = []

	# Items para o componente `select` do design system Basecoat
	context.recepcao_user_items = [
		{"label": u.full_name or u.name, "value": u.name} for u in context.recepcao_users
	]
	# Items do filtro de ramo do cabeçalho (aplicado no cliente sobre os cards
	# já renderizados). A contagem ajuda a dimensionar o volume de cada ramo.
	contagem_por_ramo = dict.fromkeys(RAMOS, 0)
	sem_ramo = 0
	for cards in kanban_data.values():
		for card in cards:
			if card.ramo in contagem_por_ramo:
				contagem_por_ramo[card.ramo] += 1
			else:
				sem_ramo += 1

	total_cards = sum(contagem_por_ramo.values()) + sem_ramo
	ramo_filtro_items = [{"label": f"Todos os ramos ({total_cards})", "value": ""}]
	ramo_filtro_items += [{"label": f"{r} ({contagem_por_ramo[r]})", "value": r} for r in RAMOS]
	if sem_ramo:
		ramo_filtro_items.append({"label": f"Sem ramo ({sem_ramo})", "value": RAMO_FILTRO_SEM_RAMO})

	context.ramo_filtro_items = ramo_filtro_items

	return context


@frappe.whitelist()
def confirmar_registro_paxtu(novo_associado_name: str):
	"""Botão "Registro Criado no Paxtu": atalho para concluir a etapa homônima.

	O efeito (marcar a etapa e mover para "Acompanhamento") vem de ``STATUS_POR_ETAPA``,
	então o botão e a bolinha da timeline fazem exatamente a mesma coisa.
	"""
	update_step_status(novo_associado_name, "registro_criado_no_paxtu", 1)

	return "Registro confirmado com sucesso."


@frappe.whitelist()
def update_step_status(novo_associado_name: str, field: str, value: str | int):
	if not novo_associado_name:
		frappe.throw(_("Novo Associado não especificado."))

	# Validate field against allowed steps
	allowed_fields = [s["field"] for s in STEPS_DEF]

	if field not in allowed_fields:
		frappe.throw(_("Campo inválido."))

	concluida = bool(int(value))

	# Efetivar o registro exige o número de registro em mãos. A trava fica aqui, e não
	# no controller de Novo Associado, porque a criação do Associado também marca a
	# etapa — e nesse caminho o número vem do próprio Associado, sem diálogo a exibir.
	if concluida and field in CAMPOS_DE_EFETIVACAO:
		pendentes = numeros_de_registro_pendentes(novo_associado_name)
		if pendentes:
			frappe.throw(
				_("Informe o número de registro antes de efetivar: {0}.").format(", ".join(pendentes))
			)

	doc = frappe.get_doc("Novo Associado", novo_associado_name)
	doc.set(field, 1 if concluida else 0)
	if concluida and field in STATUS_POR_ETAPA:
		doc.status = STATUS_POR_ETAPA[field]

	doc.save()

	return "Status atualizado com sucesso."


@frappe.whitelist()
def finalizar_processo_recepcao(novo_associado_name: str):
	if not novo_associado_name:
		frappe.throw(_("Novo Associado não especificado."))

	na_doc = frappe.get_doc("Novo Associado", novo_associado_name)

	# Find Associado by hashed CPF (as name)
	if not na_doc.cpf:
		frappe.throw(_("Novo Associado sem CPF. Não é possível vincular ao Associado."))

	cpf_clean = re.sub(r"\D", "", na_doc.cpf)
	associado_name = hashlib.md5(cpf_clean.encode("utf-8")).hexdigest()

	if not frappe.db.exists("Associado", associado_name):
		frappe.throw(
			f"Associado com name/hash {associado_name} (CPF {na_doc.cpf}) não encontrado. Certifique-se de que o registro foi criado."
		)

	# Update Responsavel Vinculo
	links = frappe.get_all("Responsavel Vinculo", filters={"beneficiario_novo_associado": na_doc.name})
	responsavel_ids = []

	for link in links:
		link_doc = frappe.get_doc("Responsavel Vinculo", link.name)
		link_doc.beneficiario_novo_associado = None
		link_doc.beneficiario_associado = associado_name
		link_doc.save(ignore_permissions=True)
		if link_doc.responsavel:
			responsavel_ids.append(link_doc.responsavel)

	# Anonymize Responsavel
	fields_to_keep = [
		"o_que_gosta_de_fazer_no_dia_a_dia",
		"habilidades",
		"nome_completo",
		"informacoes_pessoais_section",  # Keep section breaks to avoid UI issues
		"hobbies_e_interesses_section",
		"informacoes_profissionais_e_academicas_section",
		"endereco_e_dados_de_contato_section",
	]

	# Get all fields of Responsavel
	meta = frappe.get_meta("Responsavel")
	fields_to_clear = []
	for field in meta.fields:
		if field.fieldname not in fields_to_keep and field.fieldtype not in [
			"Section Break",
			"Column Break",
			"Tab Break",
			"Table MultiSelect",
		]:
			fields_to_clear.append(field.fieldname)

	for resp_id in set(responsavel_ids):
		resp_doc = frappe.get_doc("Responsavel", resp_id)
		for field in fields_to_clear:
			# Clear value
			resp_doc.set(field, None)
		resp_doc.save(ignore_permissions=True)

	# Delete Agenda de Visitas records linked to this Novo Associado
	frappe.db.delete("Agenda de Visitas", {"jovem": na_doc.name})

	# Delete Novo Associado
	frappe.delete_doc("Novo Associado", na_doc.name, ignore_permissions=True)

	return "Recepção finalizada com sucesso."
