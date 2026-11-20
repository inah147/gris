import frappe

from gris.api.associados_vencimento_modelos import (
	CAMPOS_DE_INTERRUPTOR,
	INSTRUCOES_RENOVACAO_PADRAO,
	INSTRUCOES_RENOVACAO_VENCIDO_PADRAO,
	MODELOS_PADRAO,
	SETTINGS_DOCTYPE,
	TEXTO_JA_RENOVADO_PADRAO,
	valor_bruto,
)

# Data de corte decidida com o usuário (20/11/2026): quem venceu a partir de 01/11/2026 entra na
# cobrança recorrente e no aviso de vencido ao chefe. Só é gravada se o campo estiver vazio.
CORTE_INICIAL = "2026-11-01"

# Texto padrão da primeira versão do patch, trocado quando ninguém o editou.
INSTRUCOES_RENOVACAO_ANTIGA = "A renovação é feita pelo Paxtu (paxtu.escoteiros.org.br)."


def execute():
	"""Prepara a régua de vencimento do registro em Configurações de Associados.

	O Single já existe, então os ``default`` do JSON não valem para ele. Sem este patch a tela
	abriria com os modelos em branco e os interruptores desmarcados, enquanto o código trata
	ausência como "ligado" e "texto padrão": a tela diria uma coisa e o robô faria outra.

	Só preenche o que falta. A data de corte nasce em 01/11/2026 (decisão do usuário) e pode ser
	trocada na tela; o interruptor geral não é tocado: a régua nasce desligada.
	"""
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return

	valores: dict[str, object] = {}
	for campo in CAMPOS_DE_INTERRUPTOR:
		if valor_bruto(campo) is None:
			valores[campo] = 1
	for campo, texto in MODELOS_PADRAO.items():
		if not (valor_bruto(campo) or "").strip():
			valores[campo] = texto
	if not (valor_bruto("texto_ja_renovado") or "").strip():
		valores["texto_ja_renovado"] = TEXTO_JA_RENOVADO_PADRAO
	instrucoes = (valor_bruto("instrucoes_renovacao") or "").strip()
	if not instrucoes or instrucoes == INSTRUCOES_RENOVACAO_ANTIGA:
		valores["instrucoes_renovacao"] = INSTRUCOES_RENOVACAO_PADRAO
	if not (valor_bruto("instrucoes_renovacao_vencido") or "").strip():
		valores["instrucoes_renovacao_vencido"] = INSTRUCOES_RENOVACAO_VENCIDO_PADRAO
	if not valor_bruto("cobrar_vencidos_desde"):
		valores["cobrar_vencidos_desde"] = CORTE_INICIAL
	if valor_bruto("intervalo_recorrente_dias") is None:
		valores["intervalo_recorrente_dias"] = 3

	if valores:
		frappe.db.set_single_value(SETTINGS_DOCTYPE, valores)
	frappe.db.commit()
