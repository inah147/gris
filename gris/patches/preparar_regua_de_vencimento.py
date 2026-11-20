import frappe

from gris.api.associados_vencimento_modelos import (
	CAMPOS_DE_INTERRUPTOR,
	INSTRUCOES_RENOVACAO_PADRAO,
	MODELOS_PADRAO,
	SETTINGS_DOCTYPE,
	TEXTO_JA_RENOVADO_PADRAO,
	valor_bruto,
)


def execute():
	"""Prepara a régua de vencimento do registro em Configurações de Associados.

	O Single já existe, então os ``default`` do JSON não valem para ele. Sem este patch a tela
	abriria com os modelos em branco e os interruptores desmarcados, enquanto o código trata
	ausência como "ligado" e "texto padrão": a tela diria uma coisa e o robô faria outra.

	Só preenche o que falta. O interruptor geral e a data de corte não são tocados: a régua
	nasce desligada e quem liga escolhe o corte.
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
	if not (valor_bruto("instrucoes_renovacao") or "").strip():
		valores["instrucoes_renovacao"] = INSTRUCOES_RENOVACAO_PADRAO
	if valor_bruto("intervalo_recorrente_dias") is None:
		valores["intervalo_recorrente_dias"] = 3

	if valores:
		frappe.db.set_single_value(SETTINGS_DOCTYPE, valores)
	frappe.db.commit()
