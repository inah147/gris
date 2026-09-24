# Copyright (c) 2026, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
# For license information, please see license.txt
"""Identidade compartilhada entre ``Responsavel`` e ``Associado``.

Um responsável legal que também é membro do grupo tem dois cadastros para a mesma pessoa.
Os dois já nascem com a **mesma chave** — ``Responsavel.autoname`` e ``Associado.autoname``
derivam o ``name`` do md5 dos dígitos do CPF —, mas até aqui nada no app usava esse fato: o
organograma chegou a criar prefixos (``responsavel:`` / ``associado:``) só para um clique
num card não marcar o homônimo do outro lado.

É por isso que ``Responsavel Vinculo.responsavel`` **não muda**. O valor gravado ali já é o
``name`` do associado sempre que a pessoa for associada, então as dezenas de consultas por
``{"responsavel": X}`` espalhadas pelo app seguem valendo sem uma linha de alteração. O que
faltava era tornar a relação explícita, e é isso que ``Responsavel.associado`` faz.

O campo é gravado, e não calculado na hora, por um motivo concreto: ``_anonimizar_responsaveis``
(ver ``gris.www.recepcao.visao_geral``) apaga o CPF do responsável quando o jovem sai do
funil. Depois disso o único jeito de reencontrar o associado seria pelo ``name`` — que não
basta para os cadastros legados, nomeados pelo md5 do CPF *pontuado* (ver
``gris.utils.documento``). Resolver uma vez, enquanto o CPF existe, e guardar.

Quem é responsável **e** associado passa a ter um perfil só: hobbies, interesses e
habilidades vivem no ``Associado``, e a pessoa acumula a função de Responsável Legal na área
do Conselho de Responsáveis.
"""

from __future__ import annotations

import frappe

from gris.utils.documento import localizar_associado_por_cpf

#: Campos de perfil que deixam de viver no ``Responsavel`` e passam para o ``Associado``.
CAMPOS_DE_PERFIL = ("o_que_gosta_de_fazer_no_dia_a_dia",)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def associado_do_responsavel(responsavel_name: str | None) -> str | None:
	"""``name`` do ``Associado`` da mesma pessoa, ou ``None`` quando ela só é responsável.

	A ponte gravada vem primeiro porque é a única que cobre os cadastros legados. O
	fallback pelo ``name`` é o caso canônico — os dois DocTypes derivam a chave do mesmo
	CPF — e serve para quem ainda não passou pela sincronização.
	"""
	if not responsavel_name:
		return None

	vinculado = frappe.db.get_value("Responsavel", responsavel_name, "associado")
	if vinculado:
		return str(vinculado)

	if frappe.db.exists("Associado", responsavel_name):
		return str(responsavel_name)

	return None


def responsavel_do_associado(associado_name: str | None) -> str | None:
	"""``name`` do ``Responsavel`` da mesma pessoa, ou ``None``."""
	if not associado_name:
		return None

	vinculado = frappe.db.get_value("Responsavel", {"associado": associado_name}, "name")
	if vinculado:
		return str(vinculado)

	if frappe.db.exists("Responsavel", associado_name):
		return str(associado_name)

	return None


def documento_de_perfil(responsavel_name: str | None):
	"""Documento onde hobbies, interesses e habilidades daquela pessoa vivem hoje.

	É o ``Associado`` quando a pessoa migrou, e o ``Responsavel`` caso contrário. Sem isto,
	a tela de auto-serviço do responsável continuaria gravando no cadastro que deixou de ser
	o canônico, e o perfil divergiria em silêncio.
	"""
	if not responsavel_name:
		return None

	migrado = frappe.db.get_value(
		"Responsavel", responsavel_name, ["associado", "migrado_para_associado"], as_dict=True
	)
	if migrado and migrado.migrado_para_associado and migrado.associado:
		return frappe.get_doc("Associado", migrado.associado)

	return frappe.get_doc("Responsavel", responsavel_name)


def tem_vinculo_de_responsavel(responsavel_name: str | None, ignorando: str | None = None) -> bool:
	"""Diz se o responsável ainda tem algum beneficiário.

	``ignorando`` existe para o ``on_trash`` do vínculo: a linha só sai do banco depois do
	hook, então contá-la manteria a pessoa no conselho para sempre.
	"""
	if not responsavel_name:
		return False

	filtros: dict = {"responsavel": responsavel_name}
	if ignorando:
		filtros["name"] = ["!=", ignorando]

	return bool(frappe.db.exists("Responsavel Vinculo", filtros))


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------


def vincular_responsavel_ao_associado(responsavel_name: str | None) -> str | None:
	"""Liga o responsável ao cadastro de associado da mesma pessoa e migra o perfil.

	Idempotente de propósito: roda num patch, em dois hooks e pode ser chamada de novo sem
	efeito. Devolve o ``name`` do ``Associado`` quando há um, ou ``None``.

	A cópia de perfil só preenche campo vazio. Uma segunda execução não pode sobrescrever o
	que a pessoa editou depois pelo lado do associado.
	"""
	if not responsavel_name:
		return None

	responsavel = frappe.db.get_value(
		"Responsavel", responsavel_name, ["name", "cpf", "associado"], as_dict=True
	)
	if not responsavel:
		return None

	associado_name = _resolver_associado(responsavel)
	if not associado_name:
		return None

	if responsavel.associado != associado_name:
		frappe.db.set_value(
			"Responsavel",
			responsavel_name,
			{"associado": associado_name, "migrado_para_associado": 1},
			update_modified=False,
		)
	else:
		frappe.db.set_value(
			"Responsavel", responsavel_name, "migrado_para_associado", 1, update_modified=False
		)

	_aplicar_no_associado(responsavel_name, associado_name)

	return associado_name


def sincronizar_flag_de_responsavel(
	responsavel_name: str | None, vinculo_ignorado: str | None = None
) -> None:
	"""Reconcilia ``Associado.e_responsavel_legal`` e a função no Conselho de Responsáveis.

	A flag é derivada do vínculo: é responsável quem tem beneficiário. Perder o último
	vínculo **encerra** a função (``data_fim``) em vez de apagar a linha, como o resto do
	organograma faz — o histórico continua de pé.
	"""
	associado_name = associado_do_responsavel(responsavel_name)
	if not associado_name:
		return

	_aplicar_no_associado(responsavel_name, associado_name, vinculo_ignorado=vinculo_ignorado)


def _aplicar_no_associado(
	responsavel_name: str, associado_name: str, vinculo_ignorado: str | None = None
) -> None:
	"""Cópia de perfil e função do conselho num carregamento e numa gravação só.

	As duas coisas mexem no mesmo documento; separá-las custaria dois `get_doc` e dois
	`save` do `Associado` a cada vínculo criado.
	"""
	from gris.api.gestao_adultos.responsaveis import (
		encerrar_funcao_do_conselho,
		garantir_funcao_do_conselho,
	)

	e_responsavel = tem_vinculo_de_responsavel(responsavel_name, ignorando=vinculo_ignorado)

	doc = frappe.get_doc("Associado", associado_name)
	mudou = _copiar_perfil(responsavel_name, doc)
	if e_responsavel:
		mudou = garantir_funcao_do_conselho(doc) or mudou
	else:
		mudou = encerrar_funcao_do_conselho(doc) or mudou

	if mudou:
		doc.save(ignore_permissions=True)

	atual = int(frappe.db.get_value("Associado", associado_name, "e_responsavel_legal") or 0)
	if atual != int(e_responsavel):
		frappe.db.set_value(
			"Associado",
			associado_name,
			"e_responsavel_legal",
			1 if e_responsavel else 0,
			update_modified=False,
		)


def _resolver_associado(responsavel: dict) -> str | None:
	"""``name`` do ``Associado`` daquela pessoa, do caminho mais confiável ao mais fraco."""
	if responsavel.get("associado"):
		return str(responsavel["associado"])

	# Enquanto o CPF existe, o resolver cobre as três convenções de hash de uma vez.
	if responsavel.get("cpf"):
		achado = localizar_associado_por_cpf(responsavel["cpf"])
		if achado:
			return achado

	# Cadastro já anonimizado pelo funil: só sobrou a chave, que é a convenção canônica.
	if frappe.db.exists("Associado", responsavel["name"]):
		return str(responsavel["name"])

	return None


def _copiar_perfil(responsavel_name: str, destino) -> bool:
	"""Copia hobbies, interesses e habilidades para o associado, sem sobrescrever nada.

	Só preenche campo vazio: uma segunda execução não pode desfazer o que a pessoa editou
	depois pelo lado do associado. E só carrega o `Responsavel` quando há de fato buraco a
	preencher — depois da primeira migração esta função vira duas leituras em memória.

	Altera o documento e devolve se mexeu; quem chama grava.
	"""
	faltando = [campo for campo in CAMPOS_DE_PERFIL if not (destino.get(campo) or "").strip()]
	falta_habilidades = not destino.habilidades
	if not faltando and not falta_habilidades:
		return False

	origem = frappe.get_doc("Responsavel", responsavel_name)
	mudou = False

	for campo in faltando:
		valor = (origem.get(campo) or "").strip()
		if valor:
			destino.set(campo, valor)
			mudou = True

	if falta_habilidades and origem.habilidades:
		for linha in origem.habilidades:
			destino.append("habilidades", {"habilidade": linha.habilidade})
		mudou = True

	return mudou


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def on_responsavel_atualizado(doc, method=None) -> None:
	"""Reconcilia a identidade a cada gravação do ``Responsavel``.

	Roda protegida por ``frappe.flags.gris_sync_pessoas`` porque a rotina grava no próprio
	responsável e no associado, e por um savepoint porque um cadastro torto não pode
	derrubar o save de quem o editou — o erro vira log, não tela de erro no meio de outra
	tarefa. Mesmo desenho de ``gris.api.gestao_adultos.secoes.on_associado_atualizado``.
	"""
	_reconciliar(doc.name, f"Identidade do responsável {doc.name}")


def on_vinculo_atualizado(doc, method=None) -> None:
	"""Vínculo novo ou alterado: a pessoa do outro lado pode ter virado responsável."""
	_reconciliar(doc.responsavel, f"Vínculo de responsável {doc.name}")


def on_vinculo_removido(doc, method=None) -> None:
	"""Vínculo apagado: pode ter sido o último, e aí a função no conselho se encerra."""
	_reconciliar(
		doc.responsavel,
		f"Vínculo de responsável {doc.name}",
		vinculo_ignorado=doc.name,
		so_flag=True,
	)


def _reconciliar(
	responsavel_name: str | None,
	titulo_do_erro: str,
	vinculo_ignorado: str | None = None,
	so_flag: bool = False,
) -> None:
	if frappe.flags.in_migrate or frappe.flags.in_patch or frappe.flags.in_install:
		return
	if frappe.flags.gris_sync_pessoas:
		return
	if not responsavel_name:
		return

	ponto = f"sync_pessoas_{frappe.generate_hash(length=8)}"
	frappe.db.savepoint(ponto)
	frappe.flags.gris_sync_pessoas = True
	try:
		if so_flag:
			sincronizar_flag_de_responsavel(responsavel_name, vinculo_ignorado=vinculo_ignorado)
		else:
			vincular_responsavel_ao_associado(responsavel_name)
	except Exception:
		frappe.db.rollback(save_point=ponto)
		frappe.log_error(
			title="Identidade responsável/associado",
			message=f"{titulo_do_erro}\n\n{frappe.get_traceback()}",
		)
	finally:
		frappe.flags.gris_sync_pessoas = False
