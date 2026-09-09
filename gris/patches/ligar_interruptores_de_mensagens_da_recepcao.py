import frappe

from gris.api.recepcao_mensagens import (
	CAMPOS_DE_INTERRUPTOR,
	SETTINGS_DOCTYPE,
	_valor_bruto_do_single,
)


def execute():
	"""Marca como ligados os interruptores ``msg_*`` de Configurações de Recepção.

	Os Checks nascem com ``default: "1"``, mas o default só vale para uma linha nova em
	``tabSingles`` — e o Single da recepção já existe. Sem este patch a tela abre com os 15
	quadradinhos desmarcados enquanto o código, que trata ausência como ligado, continua
	enviando: a tela diria uma coisa e o robô faria outra. Pior, um Save sem tocar em nada
	gravaria 15 zeros e silenciaria todas as mensagens da recepção de uma vez.

	Só preenche o que está faltando: quem já desmarcou algo de propósito não é sobrescrito.
	"""
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return

	# ``Singles`` é tabela, não DocType: ``frappe.get_all`` não a enxerga. O helper do módulo
	# de mensagens é o mesmo caminho de leitura crua usado em produção.
	for campo in CAMPOS_DE_INTERRUPTOR:
		if _valor_bruto_do_single(campo) is None:
			frappe.db.set_single_value(SETTINGS_DOCTYPE, campo, 1)

	frappe.db.commit()
