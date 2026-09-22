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
	ETAPAS_QUE_MOVEM_O_FUNIL,
	FIELD_INTERVAL_MAP,
	STATUS_ACOMPANHAMENTO,
	STATUS_FORA_DO_FUNIL,
	STEPS_DEF,
	anexar_historico,
	calcular_etapas,
	carregar_configuracao,
	coluna_de_acompanhamento,
	dias_para_registro_definitivo,
	sinal_registro_definitivo,
	status_por_etapas_concluidas,
)
from gris.api.recepcao_vagas import calcular_vagas_por_ramo, dados_do_dialog, ramo_sem_vagas
from gris.api.recepcao_visitas import remover_visita_do_jovem
from gris.utils.documento import localizar_associado_por_cpf, localizar_associados_em_lote

no_cache = 1

RAMOS = ["Filhotes", "Lobinho", "Escoteiro", "Sênior", "Pioneiro"]

# Valor sentinela do filtro de ramo para cards ainda sem ramo definido
RAMO_FILTRO_SEM_RAMO = "__sem_ramo__"

# Etapa -> coluna do funil, na forma de mapa. A ordem, que o desmarcar usa para recalcular
# o status, mora em ``ETAPAS_QUE_MOVEM_O_FUNIL`` (``gris.api.recepcao_funil``).
STATUS_POR_ETAPA = dict(ETAPAS_QUE_MOVEM_O_FUNIL)


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

	# Colunas do kanban. As três últimas são as faces do mesmo status
	# "Acompanhamento": a separação sai de ``coluna_de_acompanhamento`` e não do
	# campo ``status``, então o card migra sozinho da lista provisória para a
	# definitiva quando o registro provisório é efetivado, e dela para a final
	# quando o registro definitivo é efetivado.
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
		"cpf",
		"owner",
		"responsavel_recepcao",
		"tipo_de_registro",
		"numero_de_registro",
		"visita_agendada",
		"primeira_visita_realizada",
		"reagendamento_pendente",
		"data_pedido_reagendamento",
		"data_registro_provisorio_efetivado",
		*field_interval_map.keys(),
	]

	novos_associados = frappe.get_all(
		"Novo Associado",
		fields=fields_to_fetch,
		order_by="modified desc",
	)

	# Vagas de cada ramo, para o selo "Seção sem vagas". As linhas já carregadas vão
	# junto para a conta não reconsultar o funil.
	vagas_por_ramo = calcular_vagas_por_ramo(novos_associados)

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

	# Cadastro de ``Associado`` de quem está em acompanhamento. É ele que libera o botão
	# "Finalizar Recepção" no dialog do card: sem cadastro não há para onde migrar os
	# vínculos, então o botão nem aparece. Resolvido em lote (ver
	# ``gris.utils.documento.localizar_associados_em_lote``) para não consultar por card,
	# e só para quem está em acompanhamento — antes disso o registro ainda não existe.
	cadastro_associado_map = localizar_associados_em_lote(
		[
			{"chave": na.name, "cpf": na.cpf, "registro": na.numero_de_registro}
			for na in novos_associados
			if na.status == STATUS_ACOMPANHAMENTO
		]
	)

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
	# Espera do registro definitivo lida uma vez, não por card.
	dias_registro_definitivo = dias_para_registro_definitivo(config)

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

			# Sinal de reagendamento: o card volta para "Conversa Inicial" carregando
			# desde quando a visita está esperando ser remarcada.
			associado.reagendamento_pendente = bool(associado.reagendamento_pendente)
			associado.reagendamento_data = (
				format_date(associado.data_pedido_reagendamento)
				if associado.data_pedido_reagendamento
				else None
			)

			# Sinal "hora do registro definitivo": quem efetivou o provisório há mais
			# tempo que o configurado ganha o selo no card, para a recepção ver a
			# pendência na visão geral sem abrir perfil por perfil.
			sinal_definitivo = sinal_registro_definitivo(associado, dias_registro_definitivo, today)
			associado.registro_definitivo_pendente = sinal_definitivo["pendente"]
			associado.registro_definitivo_dias = sinal_definitivo["dias"]
			associado.registro_definitivo_desde = (
				format_date(sinal_definitivo["desde"]) if sinal_definitivo["desde"] else None
			)

			# Selo "Seção sem vagas": só marca o card, não trava nada no funil.
			associado.sem_vagas = ramo_sem_vagas(vagas_por_ramo, associado.ramo, associado.status)
			associado.vagas_disponiveis = (
				vagas_por_ramo[associado.ramo].disponiveis if associado.sem_vagas else None
			)

			# Idade recalculada a cada carregamento da página
			associado.idade = formatar_idade(associado.data_de_nascimento)

			associado.observacoes_count = observacoes_map.get(associado.name, 0)

			# Cadastro do Associado já criado (vazio = recepção ainda não pode ser finalizada).
			associado.cadastro_associado = cadastro_associado_map.get(associado.name)

			# Set ramo class
			associado.ramo_class = ramo_map.get(associado.ramo, "default")
			associado.ramo_variant = ramo_variant_map.get(associado.ramo, "secondary")

			kanban_data[coluna].append(associado)

	context.kanban_columns = colunas
	context.kanban_data = kanban_data
	# O ícone ao lado do ramo, nos modais dos cards, abre o mesmo dialog "Cálculo de Vagas"
	# da Fila de Espera (include compartilhado), com estes números.
	context.vagas_por_ramo = dados_do_dialog(vagas_por_ramo)
	# As listas de acompanhamento abrem o mesmo dialog; o template precisa
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

	# Marcar empurra o card para a coluna da etapa; desmarcar recalcula a coluna a partir das
	# etapas que sobraram marcadas, para o card não ficar numa lista que não é mais a dele.
	# Quem está fora da esteira (fila de espera, concluído) não é arrastado de volta.
	if doc.status not in STATUS_FORA_DO_FUNIL:
		if concluida and field in STATUS_POR_ETAPA:
			doc.status = STATUS_POR_ETAPA[field]
		elif not concluida:
			doc.status = status_por_etapas_concluidas(doc)

	doc.save()

	# A visita só é apagada depois do save: se a gravação falhar, o jovem não fica sem visita
	# e com a etapa ainda marcada.
	if not concluida and field == "visita_agendada":
		remover_visita_do_jovem(novo_associado_name)

	return "Status atualizado com sucesso."


@frappe.whitelist()
def finalizar_processo_recepcao(novo_associado_name: str):
	"""Tira o jovem do funil: migra os vínculos para o ``Associado`` e apaga o cadastro do funil.

	Exige o cadastro de ``Associado`` já criado — é para ele que os vínculos do responsável
	vão. O botão da visão geral só aparece quando o cadastro existe (ver
	``cadastro_associado`` no ``get_context``); a checagem daqui é a que vale.
	"""
	if not novo_associado_name:
		frappe.throw(_("Novo Associado não especificado."))

	na_doc = frappe.get_doc("Novo Associado", novo_associado_name)

	# Finalizar apaga o jovem do funil e reescreve o cadastro do responsável. A permissão
	# de apagar o Novo Associado é a porta: hoje só "Recepcao" e "System Manager" a têm, e
	# são os mesmos que escrevem em Responsavel e Responsavel Vinculo. O cadastro do
	# Associado é só lido aqui — cobrar permissão nele trancaria a própria recepção, que
	# não tem acesso a esse DocType.
	if not na_doc.has_permission("delete"):
		frappe.throw(_("Você não tem permissão para finalizar a recepção."), frappe.PermissionError)

	if not na_doc.cpf:
		frappe.throw(_("Novo Associado sem CPF. Não é possível vincular ao Associado."))

	# O cadastro pode ter sido nomeado pela convenção antiga (md5 do CPF pontuado), por isso
	# a busca passa pelo resolver em vez de recalcular o hash aqui.
	associado_name = localizar_associado_por_cpf(na_doc.cpf, na_doc.numero_de_registro)

	if not associado_name:
		frappe.throw(
			_(
				"O cadastro do Associado de {0} ainda não existe. Crie o cadastro (ou importe do Paxtu) antes de finalizar a recepção."
			).format(na_doc.nome_completo or novo_associado_name)
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

	_anonimizar_responsaveis(responsavel_ids)
	_desvincular_registros_do_funil(na_doc.name)

	# Delete Novo Associado
	frappe.delete_doc("Novo Associado", na_doc.name, ignore_permissions=True)

	return "Recepção finalizada com sucesso."


# Campos do ``Responsavel`` que sobrevivem à anonimização.
#
# Nome, hobbies e habilidades ficam porque é o que o grupo usa para lembrar quem é a
# família e no que ela pode ajudar. E-mail e celular ficam por necessidade operacional:
# o e-mail é a chave da sessão no portal (ver
# ``gris.api.responsavel_acesso.get_responsavel_do_usuario``), então apagá-lo tranca a
# família fora de ``/responsavel`` no mesmo instante em que o filho vira associado; o
# celular é o canal de WhatsApp com ela. Documento, endereço e dados profissionais, que
# só serviam para montar o registro, saem.
CAMPOS_PRESERVADOS_DO_RESPONSAVEL = (
	"o_que_gosta_de_fazer_no_dia_a_dia",
	"habilidades",
	"nome_completo",
	"email",
	"celular",
	"informacoes_pessoais_section",  # Keep section breaks to avoid UI issues
	"hobbies_e_interesses_section",
	"informacoes_profissionais_e_academicas_section",
	"endereco_e_dados_de_contato_section",
)


def _anonimizar_responsaveis(responsavel_ids: list[str]) -> None:
	"""Limpa do ``Responsavel`` o que só existia para o processo de registro."""
	meta = frappe.get_meta("Responsavel")
	fields_to_clear = [
		field.fieldname
		for field in meta.fields
		if field.fieldname not in CAMPOS_PRESERVADOS_DO_RESPONSAVEL
		and field.fieldtype
		not in [
			"Section Break",
			"Column Break",
			"Tab Break",
			"Table MultiSelect",
		]
	]

	for resp_id in set(responsavel_ids):
		resp_doc = frappe.get_doc("Responsavel", resp_id)
		for field in fields_to_clear:
			# Clear value
			resp_doc.set(field, None)
		resp_doc.save(ignore_permissions=True)


# Quem aponta para o jovem do funil por campo ``Link`` e é apagado junto com ele, como
# ``DocType -> fieldname``. Fora desta lista ficam só os dois tratados à parte:
# ``Responsavel Vinculo``, que é migrado para o Associado em vez de apagado, e
# ``Agenda de Visitas``, que sai pelo serviço de visitas. O teste de finalização confere
# que nenhuma ligação nova ficou de fora (é ela que trava a exclusão).
LIGACOES_APAGADAS_COM_O_FUNIL = (
	("Log de Mensagem", "novo_associado"),
	("Fila de Espera", "associado"),
)


def _desvincular_registros_do_funil(novo_associado_name: str) -> None:
	"""Apaga o que aponta para o jovem no funil, antes de apagar o próprio jovem.

	``frappe.delete_doc`` recusa apagar um documento que ainda é destino de um campo
	``Link`` (``LinkExistsError``), então a visita, o log de mensagens e a fila de espera
	saem primeiro — senão a finalização quebra justamente em quem recebeu mensagem, que é
	todo mundo que chegou até o fim do funil.

	As observações do card são referência dinâmica, não ``Link``: nunca travaram a
	exclusão, mas a limpeza delas pelo Frappe é um job enfileirado depois do commit. Aqui
	elas saem na mesma transação, para não ficar comentário órfão apontando para um jovem
	que não existe mais caso o job não rode.
	"""
	# A visita sai pelo serviço, e não por um delete direto, para passar pelos hooks dela.
	remover_visita_do_jovem(novo_associado_name)

	for doctype, fieldname in LIGACOES_APAGADAS_COM_O_FUNIL:
		frappe.db.delete(doctype, {fieldname: novo_associado_name})

	frappe.db.delete(
		"Comment", {"reference_doctype": "Novo Associado", "reference_name": novo_associado_name}
	)
