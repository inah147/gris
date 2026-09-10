import frappe

from gris.utils.opcoes_cadastro import CAMPOS_SELECT_POR_DOCTYPE, GRAFIAS_ANTIGAS

# Fieldname no DocType -> chave usada em ``GRAFIAS_ANTIGAS`` (que fala a língua do formulário,
# sem acento). Só ``Responsavel`` tem fieldname acentuado.
ALIASES = {"profissão": "profissao"}


def execute():
	"""Alinha os valores já gravados às listas de opções na grafia e na ordem do Paxtu.

	As listas de ``Novo Associado`` e ``Responsavel`` foram unificadas em
	``gris.utils.opcoes_cadastro``. Duas grafias antigas ficariam fora das novas opções —
	``Nâo desejo informar`` (etnia, com circunflexo) e ``Evangélico/Petencostal`` (religião).
	Um valor fora da lista some do select do portal e faz qualquer save seguinte do documento
	falhar na validação de Select, então ele é corrigido aqui.

	O que não casar com nenhuma opção é apenas registrado no log: são cadastros antigos com
	texto livre (``profissao`` era ``Data`` até esta mudança), e apagá-los perderia informação
	que a recepção ainda usa para transcrever o registro.
	"""
	for doctype, campos in CAMPOS_SELECT_POR_DOCTYPE.items():
		if not frappe.db.table_exists(doctype):
			continue

		for fieldname, valores in campos.items():
			if not frappe.db.has_column(doctype, fieldname):
				continue

			chave = ALIASES.get(fieldname, fieldname)
			tabela = frappe.qb.DocType(doctype)
			coluna = tabela[fieldname]

			for antigo, novo in GRAFIAS_ANTIGAS.get(chave, {}).items():
				frappe.qb.update(tabela).set(coluna, novo).where(coluna == antigo).run()

			fora_da_lista = (
				frappe.qb.from_(tabela)
				.select(tabela.name, coluna.as_("valor"))
				.where(coluna.notin([*valores, ""]))
				.where(coluna.isnotnull())
			).run(as_dict=True)

			for linha in fora_da_lista:
				frappe.logger("gris").info(
					f"normalizar_opcoes_cadastro: {doctype} {linha.name} tem "
					f"{fieldname}={linha.valor!r}, fora das opções do Paxtu"
				)

	frappe.db.commit()
