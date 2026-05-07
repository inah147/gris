"""Presets de volume de dados a gerar por DocType."""

# Para cada chave, valor é a quantidade aproximada de registros a criar.
# Em "small", priorizamos cobertura de cenários (1+ por status); em médio/grande, escala.
PRESETS = {
	"small": {
		"responsavel": 8,
		"novo_associado_por_ramo": 2,  # x 5 ramos = 10
		"associado_por_combinacao": 1,  # cobre matriz status x categoria
		"associado_extras": 5,
		"calendario": 6,
		"calendario_simulado": 4,
		"feriados": 5,
		"funcao_voluntario": 4,
		"habilidade": 6,
		"agenda_visitas": 4,
		"pesquisa_novos_associados": 3,
		"resposta_manifestacao_interesse": 3,
		"transparencia": 2,
		"log_importacao": 2,
		"metrica_mensal": 3,
		"conta_fixa": 4,  # cobre os 4 cenários
		"meses_pagamento_contribuicao": 6,
		"transacao_extrato_geral": 10,
		"transacao_btg": 4,
		"transacao_infinitepay_extrato": 4,
		"transacao_infinitepay_recebimento": 4,
		"transacao_infinitepay_vendas": 4,
		"transacao_portao_3": 4,
		"cobranca_infinitepay": 3,
		"projeto_por_status": 1,  # x 6 status
		"entrevista": 3,
	},
	"medium": {
		"responsavel": 30,
		"novo_associado_por_ramo": 6,
		"associado_por_combinacao": 2,
		"associado_extras": 30,
		"calendario": 20,
		"calendario_simulado": 12,
		"feriados": 12,
		"funcao_voluntario": 8,
		"habilidade": 12,
		"agenda_visitas": 15,
		"pesquisa_novos_associados": 12,
		"resposta_manifestacao_interesse": 12,
		"transparencia": 6,
		"log_importacao": 6,
		"metrica_mensal": 12,
		"conta_fixa": 8,
		"meses_pagamento_contribuicao": 12,
		"transacao_extrato_geral": 60,
		"transacao_btg": 20,
		"transacao_infinitepay_extrato": 20,
		"transacao_infinitepay_recebimento": 20,
		"transacao_infinitepay_vendas": 20,
		"transacao_portao_3": 20,
		"cobranca_infinitepay": 10,
		"projeto_por_status": 2,
		"entrevista": 12,
	},
	"large": {
		"responsavel": 120,
		"novo_associado_por_ramo": 20,
		"associado_por_combinacao": 5,
		"associado_extras": 120,
		"calendario": 80,
		"calendario_simulado": 50,
		"feriados": 30,
		"funcao_voluntario": 12,
		"habilidade": 20,
		"agenda_visitas": 60,
		"pesquisa_novos_associados": 50,
		"resposta_manifestacao_interesse": 50,
		"transparencia": 20,
		"log_importacao": 20,
		"metrica_mensal": 24,
		"conta_fixa": 20,
		"meses_pagamento_contribuicao": 24,
		"transacao_extrato_geral": 300,
		"transacao_btg": 100,
		"transacao_infinitepay_extrato": 100,
		"transacao_infinitepay_recebimento": 100,
		"transacao_infinitepay_vendas": 100,
		"transacao_portao_3": 100,
		"cobranca_infinitepay": 40,
		"projeto_por_status": 4,
		"entrevista": 50,
	},
}


def get_preset(volume: str) -> dict:
	if volume not in PRESETS:
		raise ValueError(f"Volume '{volume}' inválido. Use: {list(PRESETS.keys())}")
	return PRESETS[volume]
