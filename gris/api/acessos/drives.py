"""Leitura e escrita dos drives compartilhados sem tocar no mecanismo existente.

A concessão, a revogação e a expiração continuam com os jobs de
``gris.api.google_workspace.access_manager``. Este módulo só:

* calcula, a partir do banco, o que aqueles jobs concedem a cada associado — sem chamar
  o Google, para a tela abrir rápido e não depender da API;
* acrescenta e encerra concessões manuais no Single, pelo mesmo caminho do Desk;
* adianta a concessão ou a revogação no Google num job, para a pessoa não esperar a
  rodada diária. Se esse job falhar, a rodada diária faz o mesmo trabalho.

Os helpers privados de ``access_manager`` são importados de propósito (os módulos de
drive de festas, projetos, captação e recepção fazem o mesmo): replicar as regras aqui
deixaria a tela divergir do que os jobs realmente fazem.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime, today

from gris.api.google_workspace import access_manager as workspace

WORKSPACE_DOCTYPE = workspace.SETTINGS_DOCTYPE
CONCESSAO_DOCTYPE = "Concessoes Manuais Workspace"

# Rótulos dos papéis do Google Drive, na tradução que o próprio Drive usa.
ROTULO_PERMISSAO = {
	"reader": "Leitor",
	"commenter": "Comentarista",
	"writer": "Editor",
	"fileorganizer": "Administrador de conteúdo",
	"organizer": "Administrador",
}


def rotulo_permissao(papel: str | None) -> str:
	return ROTULO_PERMISSAO.get((papel or "").strip().lower(), papel or "")


def _settings():
	# `get_doc` e não `get_cached_doc`: o projeto não usa cache, e a gravação abaixo
	# precisa do `modified` atual para o controle de concorrência funcionar.
	return frappe.get_doc(WORKSPACE_DOCTYPE)


def drives_configurados() -> list[frappe._dict]:
	"""Drives ativos do Single, com o que a tela precisa saber de cada um."""
	settings = _settings()
	return [
		frappe._dict(
			drive_id=row.drive_id,
			nome_drive=row.nome_drive,
			conceder_a_todos=bool(row.conceder_a_todos),
			permissao_padrao_beneficiario=row.permissao_padrao_beneficiario,
			permissao_padrao_adulto_voluntario=row.permissao_padrao_adulto_voluntario,
		)
		for row in workspace._get_configured_drives(settings)
	]


def nome_do_drive(drive_id: str) -> str | None:
	for row in _settings().drives_compartilhados or []:
		if row.drive_id == drive_id:
			return row.nome_drive
	return None


def _expira_em(row, dias: int):
	if row.expira_em:
		return getdate(row.expira_em)
	if row.concedido_em:
		return getdate(add_days(get_datetime(row.concedido_em), dias))
	return None


def estado_dos_drives(associado) -> dict[str, dict]:
	"""O que cada drive configurado dá ao associado hoje, segundo as regras dos jobs.

	- Drive para todos: o associado Ativo, com e-mail do domínio e categoria com papel
	  padrão (Beneficiário ou voluntário) recebe a permissão da categoria.
	- Drive restrito: vale a concessão manual ativa e não expirada do associado.
	  Administradores do sistema não expiram, como no job.
	"""
	settings = _settings()
	integracao = bool(settings.habilitar_integracao)
	dias = settings.dias_expiracao_acesso_restrito or 365
	hoje = getdate()

	email = workspace._normalize_email(associado.id_escoteiros) if associado else ""
	institucional = workspace._is_institutional_email(email, settings) if email else False
	ativo = bool(associado) and workspace._is_active_associate(associado)
	admin = None

	estados: dict[str, dict] = {}
	for row in workspace._get_configured_drives(settings):
		estado = {
			"drive_id": row.drive_id,
			"nome_drive": row.nome_drive,
			"global": bool(row.conceder_a_todos),
			"integracao": integracao,
			"tem_acesso": False,
			"permissao": None,
			"permissao_rotulo": None,
			"expira_em": None,
			"em_provisionamento": False,
		}

		if row.conceder_a_todos:
			papel = workspace._resolve_drive_default_role(row, associado) if associado else None
			if ativo and institucional and papel:
				estado.update(tem_acesso=True, permissao=papel, permissao_rotulo=rotulo_permissao(papel))
			estados[row.drive_id] = estado
			continue

		for concessao in settings.concessoes_manuais or []:
			if not concessao.ativo or concessao.drive_id != row.drive_id:
				continue
			if not associado or concessao.associado != associado.name:
				continue
			if admin is None:
				admin = bool(email) and workspace._is_workspace_admin(email)
			if workspace._is_manual_grant_expired(concessao, dias, hoje) and not admin:
				continue

			estado.update(
				tem_acesso=ativo and institucional,
				permissao=concessao.tipo_acesso,
				permissao_rotulo=rotulo_permissao(concessao.tipo_acesso),
				expira_em=None if admin else _expira_em(concessao, dias),
				em_provisionamento=not concessao.concedido_em,
			)
			break

		estados[row.drive_id] = estado

	return estados


def titulares_do_drive(drive_id: str) -> dict:
	"""Quem o mecanismo atual mantém no drive: todos os elegíveis ou as concessões."""
	settings = _settings()
	row = next((r for r in workspace._get_configured_drives(settings) if r.drive_id == drive_id), None)
	if not row:
		return {"global": False, "titulares": []}

	if row.conceder_a_todos:
		associados = frappe.get_all(
			"Associado",
			filters={"status_no_grupo": "Ativo", "id_escoteiros": ["is", "set"]},
			fields=["name", "nome_completo", "id_escoteiros", "categoria", "status_no_grupo"],
			order_by="nome_completo asc",
		)
		titulares = []
		for associado in associados:
			email = workspace._normalize_email(associado.id_escoteiros)
			papel = workspace._resolve_drive_default_role(row, associado)
			if not papel or not workspace._is_institutional_email(email, settings):
				continue
			titulares.append(
				{
					"associado": associado.name,
					"nome": associado.nome_completo,
					"email": email,
					"permissao": rotulo_permissao(papel),
					"origem": "Todos os associados",
				}
			)
		return {"global": True, "titulares": titulares}

	dias = settings.dias_expiracao_acesso_restrito or 365
	hoje = getdate()
	nomes = {
		c.associado: None
		for c in settings.concessoes_manuais or []
		if c.ativo and c.drive_id == drive_id and c.associado
	}
	if nomes:
		for associado in frappe.get_all(
			"Associado", filters={"name": ["in", list(nomes)]}, fields=["name", "nome_completo"]
		):
			nomes[associado.name] = associado.nome_completo

	titulares = []
	for concessao in settings.concessoes_manuais or []:
		if not concessao.ativo or concessao.drive_id != drive_id:
			continue
		expirada = workspace._is_manual_grant_expired(
			concessao, dias, hoje
		) and not workspace._is_workspace_admin(concessao.email_institucional)
		if expirada:
			continue
		expira = _expira_em(concessao, dias)
		titulares.append(
			{
				"associado": concessao.associado,
				"nome": nomes.get(concessao.associado) or concessao.email_institucional,
				"email": concessao.email_institucional,
				"permissao": rotulo_permissao(concessao.tipo_acesso),
				"origem": "Concessão manual",
				"concessao": concessao.name,
				"expira_em": str(expira) if expira else None,
				"em_provisionamento": not concessao.concedido_em,
			}
		)
	titulares.sort(key=lambda t: (t["nome"] or "").casefold())
	return {"global": False, "titulares": titulares}


def _gravar_com_retentativa(alterar) -> object:
	"""Recarrega o Single, aplica ``alterar`` e grava, tentando uma segunda vez se colidir.

	Por que gravar o Single inteiro e não inserir a linha filha direto: o job diário de
	acessos restritos carrega o Single, demora nas chamadas ao Google e grava tudo no fim.
	``Document.save`` apaga as linhas filhas que não estavam na cópia em memória — uma
	linha inserida por fora nesse intervalo sumiria sem aviso. Gravando pelo pai, o
	``modified`` muda e a gravação atrasada do job falha com ``TimestampMismatchError``
	em vez de apagar a concessão; o job é idempotente e refaz o trabalho na rodada
	seguinte.
	"""
	for tentativa in range(2):
		settings = _settings()
		resultado = alterar(settings)
		try:
			settings.save(ignore_permissions=True)
			return resultado
		except frappe.TimestampMismatchError:
			if tentativa:
				raise
			# O `check_if_latest` avisa por msgprint antes de lançar; sem limpar, o aviso
			# chegaria a quem pediu mesmo com a segunda tentativa dando certo.
			frappe.clear_last_message()
	return None


def registrar_concessao_manual(
	*, associado: str, email: str, drive_id: str, tipo_acesso: str, observacao: str
) -> str:
	"""Acrescenta uma concessão manual ativa ao Single e devolve o nome da linha."""

	def alterar(settings):
		drive = next((r for r in settings.drives_compartilhados or [] if r.drive_id == drive_id), None)
		if not drive:
			frappe.throw(f"O drive {drive_id} não está configurado em {WORKSPACE_DOCTYPE}.")
		linha = settings.append(
			"concessoes_manuais",
			{
				"associado": associado,
				"email_institucional": email,
				"drive": drive.nome_drive,
				"drive_id": drive_id,
				"tipo_acesso": tipo_acesso or "reader",
				"ativo": 1,
				"observacao": observacao,
			},
		)
		return linha

	linha = _gravar_com_retentativa(alterar)
	return linha.name


def encerrar_concessao_manual(nome_da_linha: str, observacao: str) -> dict | None:
	"""Marca a concessão como expirada ontem e devolve e-mail e drive para revogar.

	A linha continua ``ativo=1`` para o job diário revogar no Google e desativá-la — ele
	é a garantia caso o job imediato falhe. Administradores do sistema são a exceção:
	o job nunca expira o acesso deles e voltaria a conceder, então a linha é desativada.
	"""

	def alterar(settings):
		linha = next((c for c in settings.concessoes_manuais or [] if c.name == nome_da_linha), None)
		if not linha:
			return None
		linha.expira_em = add_days(today(), -1)
		if workspace._is_workspace_admin(linha.email_institucional):
			linha.ativo = 0
		linha.observacao = "\n".join(
			texto for texto in [(linha.observacao or "").strip(), observacao] if texto
		)
		return {"email": linha.email_institucional, "drive_id": linha.drive_id}

	return _gravar_com_retentativa(alterar)


def concessao_foi_aplicada(nome_da_linha: str) -> bool:
	return bool(frappe.db.get_value(CONCESSAO_DOCTYPE, nome_da_linha, "concedido_em"))


def enfileirar_concessao(solicitacao: str, nome_da_linha: str) -> None:
	frappe.enqueue(
		"gris.api.acessos.drives.executar_concessao",
		queue="short",
		timeout=300,
		enqueue_after_commit=True,
		solicitacao=solicitacao,
		nome_da_linha=nome_da_linha,
	)


def enfileirar_revogacao(email: str, drive_id: str) -> None:
	frappe.enqueue(
		"gris.api.acessos.drives.executar_revogacao",
		queue="short",
		timeout=300,
		enqueue_after_commit=True,
		email=email,
		drive_id=drive_id,
	)


def executar_concessao(solicitacao: str, nome_da_linha: str) -> None:
	"""Job: concede no Google agora, em vez de esperar a rodada diária."""
	settings = _settings()
	if not workspace._is_integration_enabled(settings):
		return

	linha = next((c for c in settings.concessoes_manuais or [] if c.name == nome_da_linha), None)
	if not linha or not linha.ativo:
		return

	try:
		drive = workspace._get_google_drive_service(settings)
		workspace.grant_drive_access_if_missing(
			drive, linha.email_institucional, linha.drive_id, linha.tipo_acesso or "reader"
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Concessão imediata de drive: {solicitacao}")
		return

	if not linha.concedido_em:
		frappe.db.set_value(
			CONCESSAO_DOCTYPE, nome_da_linha, "concedido_em", now_datetime(), update_modified=False
		)

	from gris.api.acessos.provisionamento import marcar_concedida

	marcar_concedida(solicitacao)


def executar_revogacao(email: str, drive_id: str) -> None:
	"""Job: revoga no Google agora. A rodada diária repete se este falhar."""
	settings = _settings()
	if not workspace._is_integration_enabled(settings):
		return
	try:
		drive = workspace._get_google_drive_service(settings)
		workspace.revoke_drive_access_if_exists(drive, email, drive_id)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Revogação imediata de drive: {email}")
