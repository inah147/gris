"""Avisos por WhatsApp do portal de acessos.

* Cada etapa nova de uma solicitação avisa quem tem o papel daquela etapa.
* Quem pediu é avisado quando o pedido é aprovado, concedido ou recusado.
* O grupo de tecnologia recebe as concessões manuais pendentes (Canva, Microsoft 365) e
  a lista de licenças a revogar à mão quando um associado fica inativo.

Todo envio é registrado para depois do commit (`frappe.db.after_commit`): uma aprovação
que falha e volta atrás não pode ter avisado ninguém. E nenhum envio derruba a gravação
— tudo passa por `try/except` com `frappe.log_error`, e a entrega em si é enfileirada
por `gris.utils.whatsapp`.
"""

from __future__ import annotations

import frappe
from frappe.utils import get_fullname, get_url

from gris.api.acessos.constantes import (
	ROLE_GESTOR,
	ROLE_SYSTEM_MANAGER,
	SETTINGS_DOCTYPE,
	TIPO_DRIVE,
	TIPO_FERRAMENTA,
	TIPO_PAPEL,
)
from gris.utils.contato import telefone_do_usuario
from gris.utils.whatsapp import enviar_para_grupo, enviar_texto

ASSUNTO = "Portal de acessos"
TIPO_APROVADOR = "Aprovador de acesso"
TIPO_SOLICITANTE = "Solicitante de acesso"
TIPO_GRUPO_TECNOLOGIA = "Grupo de tecnologia"

EVENTO_APROVADA = "aprovada"
EVENTO_CONCEDIDA = "concedida"
EVENTO_RECUSADA = "recusada"


def _logger():
	return frappe.logger("acessos_notificacoes", allow_site=True)


# ───────────────────────────── configuração ─────────────────────────────


def _avisos_habilitados() -> bool:
	return bool(frappe.db.get_single_value(SETTINGS_DOCTYPE, "habilitar_avisos_whatsapp"))


def _grupo_tecnologia() -> str:
	return (frappe.db.get_single_value(SETTINGS_DOCTYPE, "grupo_tecnologia_whatsapp") or "").strip()


def _fora_de_operacao_normal() -> bool:
	"""Migração, patch e instalação mexem em documentos sem ninguém pedindo."""
	return bool(frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate)


def _depois_do_commit(funcao, *args) -> None:
	"""Agenda o aviso para quando a transação for confirmada."""
	if _fora_de_operacao_normal() or not _avisos_habilitados():
		return

	def executar():
		try:
			funcao(*args)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"{ASSUNTO}: aviso por WhatsApp")

	frappe.db.after_commit.add(executar)


# ───────────────────────────── texto ─────────────────────────────


def _primeiro_nome(user: str) -> str:
	nome = (get_fullname(user) or "").strip()
	return nome.split()[0] if nome else user


def _link(caminho: str) -> str:
	return get_url(caminho)


def _rotulo_do_pedido(solicitacao) -> str:
	"""O acesso pedido, com a seção quando o acesso é concedido por seção."""
	if solicitacao.get("secao"):
		return f"{solicitacao.acesso} — {solicitacao.secao}"
	return solicitacao.acesso


def _mensagem_aprovador(user: str, solicitacao) -> str:
	etapa = solicitacao.etapa_corrente()
	total = solicitacao.total_de_etapas()
	justificativa = (solicitacao.justificativa or "").strip()
	linhas = [
		f"Olá, {_primeiro_nome(user)}!",
		"",
		f"*{solicitacao.solicitante_nome}* pediu acesso a *{_rotulo_do_pedido(solicitacao)}*.",
	]
	if total > 1 and etapa:
		linhas.append(f"Etapa {etapa.ordem} de {total}: {etapa.descricao}")
	if justificativa:
		linhas += ["", f"Justificativa: {justificativa}"]
	linhas += [
		"",
		f"Para aprovar ou recusar: {_link('/acessos')}",
		"",
		"_Esta é uma mensagem automática_",
	]
	return "\n".join(linhas)


def _mensagem_solicitante(solicitacao, evento: str) -> str:
	ola = f"Olá, {_primeiro_nome(solicitacao.solicitante)}!"
	acesso = f"*{_rotulo_do_pedido(solicitacao)}*"
	email = solicitacao.email_concessao or ""

	if evento == EVENTO_RECUSADA:
		corpo = f"Sua solicitação de acesso a {acesso} não foi aprovada."
		if (solicitacao.motivo or "").strip():
			corpo += f"\n\nMotivo: {solicitacao.motivo.strip()}"
	elif evento == EVENTO_CONCEDIDA:
		if solicitacao.tipo == TIPO_PAPEL:
			corpo = f"Sua solicitação foi aprovada e o acesso a {acesso} já está liberado no Gris."
		else:
			corpo = f"Seu acesso a {acesso} foi liberado para a conta {email}."
	elif solicitacao.tipo == TIPO_DRIVE:
		corpo = (
			f"Sua solicitação de acesso a {acesso} foi aprovada. "
			f"O drive vai aparecer na conta {email} em instantes."
		)
	else:
		corpo = (
			f"Sua solicitação de acesso a {acesso} foi aprovada. "
			f"A equipe de tecnologia vai criar o acesso com a conta {email} e você recebe um aviso quando estiver pronto."
		)

	return "\n".join(
		[ola, "", corpo, "", f"Seus acessos: {_link('/acessos')}", "", "_Esta é uma mensagem automática_"]
	)


def _mensagem_concessao_manual(solicitacao, instrucoes: str | None) -> str:
	linhas = [
		f"🔑 {ASSUNTO}: acesso aprovado aguardando criação",
		"",
		f"*{solicitacao.solicitante_nome}*",
		f"- *Ferramenta*: {solicitacao.acesso}",
		f"- *Conta*: {solicitacao.email_concessao}",
	]
	if (instrucoes or "").strip():
		linhas += ["", instrucoes.strip()]
	linhas += ["", f"Depois de criar a conta, confirme em: {_link('/acessos/gestao')}"]
	return "\n".join(linhas)


def _mensagem_inativos(itens: list[dict]) -> str:
	linhas = [
		f"⚠️ {ASSUNTO}: associado inativo com licenças a revogar",
		"",
		"As licenças abaixo não têm gestão automática e precisam ser removidas à mão:",
	]
	for item in itens:
		linhas += ["", f"*{item['nome']}* ({item['email']})"]
		linhas += [f"- {licenca}" for licenca in item["licencas"]]
	linhas += ["", f"Depois de remover, confirme a revogação em: {_link('/acessos/gestao')}"]
	return "\n".join(linhas)


# ───────────────────────────── destinatários ─────────────────────────────


def usuarios_com_papel(papel: str) -> list[str]:
	"""Usuários habilitados com o papel, sem Administrator."""
	if not papel:
		return []
	has_role = frappe.qb.DocType("Has Role")
	user = frappe.qb.DocType("User")
	linhas = (
		frappe.qb.from_(has_role)
		.join(user)
		.on(user.name == has_role.parent)
		.select(has_role.parent)
		.distinct()
		.where(has_role.parenttype == "User")
		.where(has_role.role == papel)
		.where(user.enabled == 1)
		.where(user.name.notin(["Administrator", "Guest"]))
	).run()
	return sorted(linha[0] for linha in linhas)


def _enviar_para_usuario(user: str, mensagem: str, tipo: str, referencia: str) -> bool:
	telefone = telefone_do_usuario(user)
	if not telefone:
		_logger().warning(f"{ASSUNTO} ({referencia}): nenhum telefone encontrado para {user}.")
		return False
	enviar_texto(
		telefone,
		mensagem,
		contexto={
			"assunto": f"{ASSUNTO}: {referencia}",
			"destinatario_tipo": tipo,
			"destinatario_nome": get_fullname(user) or user,
		},
	)
	return True


def _enviar_para_grupo_de_tecnologia(mensagem: str, referencia: str) -> bool:
	grupo = _grupo_tecnologia()
	if not grupo:
		_logger().warning(f"{ASSUNTO} ({referencia}): grupo de tecnologia não configurado.")
		return False
	enviar_para_grupo(
		grupo,
		mensagem,
		contexto={"assunto": f"{ASSUNTO}: {referencia}", "destinatario_tipo": TIPO_GRUPO_TECNOLOGIA},
	)
	return True


# ───────────────────────────── envios ─────────────────────────────


def _avisar_aprovadores(nome_da_solicitacao: str) -> None:
	solicitacao = frappe.get_doc("Solicitacao de Acesso", nome_da_solicitacao)
	etapa = solicitacao.etapa_corrente()
	if not etapa:
		return

	papel = etapa.papel_aprovador
	destinatarios = [user for user in usuarios_com_papel(papel) if user != solicitacao.solicitante]
	if not destinatarios and papel != ROLE_SYSTEM_MANAGER:
		# Ninguém tem o papel da etapa: só o System Manager consegue destravar o pedido.
		destinatarios = [
			user for user in usuarios_com_papel(ROLE_SYSTEM_MANAGER) if user != solicitacao.solicitante
		]

	enviados = sum(
		_enviar_para_usuario(user, _mensagem_aprovador(user, solicitacao), TIPO_APROVADOR, solicitacao.name)
		for user in destinatarios
	)
	if not enviados:
		_enviar_para_grupo_de_tecnologia(
			f"{ASSUNTO}: a solicitação {solicitacao.name} ({solicitacao.solicitante_nome} → "
			f"{solicitacao.acesso}) espera aprovação e ninguém com o papel {papel} pôde ser avisado.\n\n"
			f"{_link('/acessos/gestao')}",
			solicitacao.name,
		)


def _avisar_solicitante(nome_da_solicitacao: str, evento: str) -> None:
	solicitacao = frappe.get_doc("Solicitacao de Acesso", nome_da_solicitacao)
	_enviar_para_usuario(
		solicitacao.solicitante,
		_mensagem_solicitante(solicitacao, evento),
		TIPO_SOLICITANTE,
		solicitacao.name,
	)


def _avisar_concessao_manual(nome_da_solicitacao: str) -> None:
	solicitacao = frappe.get_doc("Solicitacao de Acesso", nome_da_solicitacao)
	instrucoes = frappe.db.get_value("Acesso", solicitacao.acesso, "instrucoes_concessao")
	mensagem = _mensagem_concessao_manual(solicitacao, instrucoes)
	if _enviar_para_grupo_de_tecnologia(mensagem, solicitacao.name):
		return
	for user in usuarios_com_papel(ROLE_GESTOR):
		_enviar_para_usuario(user, mensagem, TIPO_APROVADOR, solicitacao.name)


def avisar_aprovadores(solicitacao) -> None:
	_depois_do_commit(_avisar_aprovadores, solicitacao.name)


def avisar_solicitante(solicitacao, evento: str) -> None:
	_depois_do_commit(_avisar_solicitante, solicitacao.name, evento)


def avisar_concessao_manual(solicitacao) -> None:
	if solicitacao.tipo == TIPO_FERRAMENTA:
		_depois_do_commit(_avisar_concessao_manual, solicitacao.name)


def avisar_tecnologia_inativos(itens: list[dict]) -> bool:
	"""Agenda a mensagem consolidada ao grupo; ``False`` quando não há como enviar.

	O retorno decide se as licenças são carimbadas como avisadas: sem grupo configurado
	(ou com os avisos desligados), elas ficam sem carimbo e a rodada diária tenta de novo.
	"""
	if not itens or _fora_de_operacao_normal() or not _avisos_habilitados() or not _grupo_tecnologia():
		return False
	_depois_do_commit(_enviar_para_grupo_de_tecnologia, _mensagem_inativos(itens), "associado inativo")
	return True
