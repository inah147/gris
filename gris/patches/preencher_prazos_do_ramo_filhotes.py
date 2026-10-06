import frappe

from gris.api.recepcao_funil import (
	CAMPO_DIAS_ACOLHIDA_FILHOTES,
	CAMPO_DIAS_DADOS_FILHOTES,
	CAMPO_DIAS_REGISTRO_DEFINITIVO_FILHOTES,
	DIAS_PADRAO_ACOLHIDA_FILHOTES,
	DIAS_PADRAO_DADOS_FILHOTES,
	DIAS_PADRAO_REGISTRO_DEFINITIVO_FILHOTES,
)
from gris.api.recepcao_mensagens import SETTINGS_DOCTYPE, _valor_bruto_do_single

PRAZOS_DO_RAMO_FILHOTES = {
	CAMPO_DIAS_REGISTRO_DEFINITIVO_FILHOTES: DIAS_PADRAO_REGISTRO_DEFINITIVO_FILHOTES,
	CAMPO_DIAS_DADOS_FILHOTES: DIAS_PADRAO_DADOS_FILHOTES,
	CAMPO_DIAS_ACOLHIDA_FILHOTES: DIAS_PADRAO_ACOLHIDA_FILHOTES,
}


def execute():
	"""Grava os prazos padrão do ramo Filhotes em Configurações de Recepção.

	O ``default`` do campo só vale para uma linha nova em ``tabSingles``, e o Single da
	recepção já existe: sem este patch a tela abriria com 0 nos campos enquanto o código, que
	trata ausência como o padrão, conta 25, 30 e 30 dias. A tela diria uma coisa e o funil
	faria outra.

	Só preenche o que está faltando: um prazo já ajustado à mão não é sobrescrito. Por isso o
	patch pode rodar de novo (comentário em ``patches.txt``) a cada prazo novo do ramo.
	"""
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return

	for campo, padrao in PRAZOS_DO_RAMO_FILHOTES.items():
		if _valor_bruto_do_single(campo) is None:
			frappe.db.set_single_value(SETTINGS_DOCTYPE, campo, padrao)

	frappe.db.commit()
