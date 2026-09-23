import datetime
import re

import frappe
from frappe.model.document import Document
from frappe.utils import cint, getdate

from gris.utils.documento import e_hash_de_cpf, id_por_cpf, localizar_novo_associado


def _assoc_logger():
	return frappe.logger("associate_user", allow_site=True, file_count=10)


class Associado(Document):
	def _fix_phones(self):
		if self.telefone:
			num = re.sub(r"\D", "", self.telefone)
			self.telefone = f"+55{num}" if not num.startswith("55") else f"+{num}"
		if self.telefone_cobranca:
			num = re.sub(r"\D", "", self.telefone_cobranca)
			self.telefone_cobranca = f"+55{num}" if not num.startswith("55") else f"+{num}"
		if self.telefone_responsavel_1:
			num = re.sub(r"\D", "", self.telefone_responsavel_1)
			self.telefone_responsavel_1 = f"+55{num}" if not num.startswith("55") else f"+{num}"
		if self.telefone_responsavel_2:
			num = re.sub(r"\D", "", self.telefone_responsavel_2)
			self.telefone_responsavel_2 = f"+55{num}" if not num.startswith("55") else f"+{num}"

	def _fix_names(self):
		if self.nome_completo:
			self.nome_completo = self.nome_completo.title()
		if self.nome_responsavel_1:
			self.nome_responsavel_1 = self.nome_responsavel_1.title()
		if self.nome_responsavel_2:
			self.nome_responsavel_2 = self.nome_responsavel_2.title()

	def _set_status(self):
		historico = None
		if getattr(self, "historico_no_grupo", None) and any(
			r.data_de_ingresso for r in self.historico_no_grupo
		):
			historico = sorted(
				[r for r in self.historico_no_grupo if r.data_de_ingresso], key=lambda r: r.data_de_ingresso
			)
		if historico:
			last_record = historico[-1]
			desligado = bool(last_record.data_de_desligamento)
		else:
			desligado = False

		if desligado:
			self.status_no_grupo = "Inativo"
			self.status = "Desconhecido"
		else:
			self.status_no_grupo = "Ativo"
			if self.validade_registro:
				expiration = datetime.datetime.strptime(str(self.validade_registro)[:10], "%Y-%m-%d").date()
				self.status = "Válido" if expiration > datetime.date.today() else "Vencido"
			else:
				self.status = "Desconhecido"

	def _anonymize_cpfs(self):
		"""Guarda o CPF só como identificador: o md5 dos dígitos (``id_por_cpf``).

		Os dígitos são a única forma estável do número — hashear o CPF com a pontuação que
		o operador digitou dava um identificador diferente do que ``Responsavel`` e
		``Novo Associado`` derivam do mesmo CPF, e era isso que fazia a recepção não
		encontrar o cadastro do jovem na hora de finalizar.

		Idempotente de propósito: o que já é hash fica como está. Este método roda no
		``before_insert`` e de novo em todo ``before_save``, então sem a checagem o campo
		era re-hasheado a cada gravação e deixava de bater com o ``name`` do documento.
		"""
		for campo in ("cpf", "cpf_responsavel_1", "cpf_responsavel_2"):
			valor = self.get(campo)
			if valor and not e_hash_de_cpf(valor):
				self.set(campo, id_por_cpf(valor))

	def _serialize_hist(self, rows):
		"""Serializa linhas do histórico em tuplas (ingresso, desligamento) para comparação.

		Ignora linhas totalmente vazias (sem ingresso e sem desligamento).
		"""
		return [
			(
				getattr(r, "data_de_ingresso", None),
				getattr(r, "data_de_desligamento", None),
			)
			for r in (rows or [])
			if (getattr(r, "data_de_ingresso", None) or getattr(r, "data_de_desligamento", None))
		]

	def autoname(self):
		"""Nome do cadastro = identificador do CPF, o mesmo de ``Responsavel`` e do funil.

		Explícito aqui, e não só no ``autoname: field:cpf`` do DocType, para o ``name`` sair
		sempre dos dígitos do CPF. Sem CPF o nome fica vazio e o ``field:cpf`` cobra o
		campo, como antes.

		O nome é calculado depois do ``before_insert``, que já hasheou o campo, então o
		valor aqui normalmente já é o identificador — ``id_por_cpf`` só entra quando o
		documento chega com o CPF em claro.
		"""
		if self.cpf:
			self.name = self.cpf if e_hash_de_cpf(self.cpf) else id_por_cpf(self.cpf)

	def validate(self):
		self._set_status()
		self._validar_funcoes_internas()
		self._validar_vinculo_funcao_area()

	def _validar_funcoes_internas(self):
		"""Só uma função pode ser a principal, e o período tem que fazer sentido.

		A principal é a que o organograma mostra no card; com duas marcadas a
		escolha viraria sorteio pela ordem das linhas.
		"""
		principais = [linha for linha in (self.funcoes_internas or []) if linha.principal]
		if len(principais) > 1:
			frappe.throw(
				frappe._("Marque apenas uma função interna como principal (há {0} marcadas).").format(
					len(principais)
				)
			)

		for linha in self.funcoes_internas or []:
			if linha.data_inicio and linha.data_fim and linha.data_fim < linha.data_inicio:
				frappe.throw(
					frappe._("Função interna na linha {0}: a data de fim é anterior à de início.").format(
						linha.idx
					)
				)

	def _validar_vinculo_funcao_area(self):
		"""Toda função interna nova precisa de área, e o par tem que estar vinculado.

		A área é o que posiciona a pessoa no organograma, e o vínculo válido mora em
		`Unidade Organizacional.funcoes`.

		Os recortes abaixo não são zelo, e é por eles que a área não é `reqd` no
		schema: existem linhas antigas de funções que nunca tiveram área, e existem
		linhas cujo vínculo pode ser desfeito depois. Validar tudo tornaria esses
		associados insalváveis para sempre — e o Associado é gravado em lote pela
		importação do Paxtu, pela cobrança e pela recepção, que quebrariam semanas
		depois por uma edição sem relação aparente. Então só entram as linhas que
		entraram ou mudaram agora, e que ainda estão em vigor.
		"""
		if frappe.flags.in_migrate or frappe.flags.in_patch or frappe.flags.in_install:
			return

		anterior = self.get_doc_before_save()
		antes = (
			{(linha.funcao, linha.area) for linha in (anterior.funcoes_internas or [])} if anterior else set()
		)

		hoje = getdate()
		suspeitas = [
			linha
			for linha in (self.funcoes_internas or [])
			if linha.funcao
			# Linha que já existia assim não é problema novo: só o que entrou ou mudou.
			and (linha.funcao, linha.area) not in antes
			# Histórico é imutável e não precisa obedecer ao catálogo de hoje.
			and (not linha.data_fim or getdate(linha.data_fim) >= hoje)
		]
		if not suspeitas:
			return

		for linha in suspeitas:
			if not linha.area:
				frappe.throw(
					frappe._("Função interna na linha {0}: escolha a área onde {1} é exercida.").format(
						linha.idx, frappe.bold(linha.funcao)
					)
				)

		permitidos = {
			(vinculo["funcao"], vinculo["parent"])
			for vinculo in frappe.get_all(
				"Funcao da Area",
				filters={
					"parenttype": "Unidade Organizacional",
					"parent": ["in", sorted({linha.area for linha in suspeitas})],
				},
				fields=["parent", "funcao"],
			)
		}
		for linha in suspeitas:
			if (linha.funcao, linha.area) not in permitidos:
				frappe.throw(
					frappe._(
						"Função interna na linha {0}: {1} não está vinculada à área {2}. "
						"Vincule a função na unidade organizacional ou escolha outra área."
					).format(linha.idx, frappe.bold(linha.funcao), frappe.bold(linha.area))
				)

	def _handle_novo_associado_pre(self):
		if not self.cpf:
			return

		na_name = id_por_cpf(self.cpf)

		if not frappe.db.exists("Novo Associado", na_name):
			return

		self.flags.linked_novo_associado = na_name

		na_cobranca = frappe.db.get_value(
			"Novo Associado", na_name, ["email_cobranca", "telefone_cobranca"], as_dict=True
		)
		if na_cobranca:
			if na_cobranca.get("email_cobranca"):
				self.email_cobranca = na_cobranca.get("email_cobranca")
			if na_cobranca.get("telefone_cobranca"):
				self.telefone_cobranca = na_cobranca.get("telefone_cobranca")

		# Busca data da visita
		data_visita = frappe.db.get_value(
			"Agenda de Visitas", {"jovem": na_name, "visita_confirmada": 1}, "data_da_visita"
		)

		if data_visita:
			self.append("historico_no_grupo", {"data_de_ingresso": data_visita})

	def _handle_novo_associado_post(self):
		na_name = self.flags.linked_novo_associado
		if not na_name:
			return

		try:
			na_doc = frappe.get_doc("Novo Associado", na_name)
		except frappe.DoesNotExistError:
			return

		dirty = False

		if na_doc.status != "Acompanhamento":
			na_doc.status = "Acompanhamento"
			dirty = True

		# O número de registro vem junto: é ele que a visão geral cobra antes de deixar
		# marcar a etapa de efetivação, e por este caminho ela é marcada sem passar
		# pelo diálogo.
		if self.registro and not na_doc.numero_de_registro:
			na_doc.numero_de_registro = self.registro
			dirty = True

		if self.tipo_registro == "Provisório":
			if not na_doc.registro_provisorio_efetivado:
				na_doc.registro_provisorio_efetivado = 1
				dirty = True
		elif self.tipo_registro == "Definitivo":
			if not na_doc.registro_definitivo_efetivado:
				na_doc.registro_definitivo_efetivado = 1
				dirty = True

		if dirty:
			na_doc.save(ignore_permissions=True)

	def _novo_associado_vinculado(self) -> str | None:
		"""Nome do ``Novo Associado`` correspondente, se o jovem ainda está no funil.

		``Associado`` e ``Novo Associado`` são nomeados pelo md5 do CPF, então normalmente
		compartilham o nome. Cadastros criados antes da correção da convenção têm o nome
		vindo do CPF pontuado, e para eles a busca passa pelo CPF que o funil guarda em
		claro (ver ``gris.utils.documento.localizar_novo_associado``). O registro do funil
		some quando a recepção é finalizada — depois disso não há mais etapa a atualizar
		nem mensagem a enviar.
		"""
		return localizar_novo_associado(self.name, self.cpf)

	def _sincronizar_id_escoteiros_novo_associado(self, na_name: str):
		"""Marca a etapa "id@escoteiros criado" assim que o e-mail institucional aparece.

		Passa pelo documento, e não por ``frappe.db.set_value``, para que o controller de
		Novo Associado registre a conclusão da etapa no histórico como em qualquer outro
		caminho.
		"""
		if not self.id_escoteiros:
			return

		if frappe.db.get_value("Novo Associado", na_name, "id_escoteiros_criado"):
			return

		na_doc = frappe.get_doc("Novo Associado", na_name)
		na_doc.id_escoteiros_criado = 1
		na_doc.save(ignore_permissions=True)

	def _notificar_registro_criado(self, na_name: str):
		"""Avisa o responsável, uma única vez, que o registro do jovem foi criado.

		Roda no insert e no update porque o número de registro nem sempre chega junto com o
		cadastro. O envio único é garantido pelo carimbo em ``Novo Associado``, conferido aqui
		e de novo dentro do job — a checagem antecipada evita enfileirar um job por linha numa
		importação em massa de associados.
		"""
		if not self.registro:
			return

		if frappe.db.get_value("Novo Associado", na_name, "data_mensagem_registro_criado"):
			return

		frappe.enqueue(
			"gris.api.recepcao_mensagens.notificar_registro_criado",
			queue="short",
			timeout=120,
			job_name=f"notificar_registro_criado:{na_name}",
			associado_name=na_name,
			enqueue_after_commit=True,
		)

	def _processar_vinculo_com_recepcao(self):
		"""Reflete no funil de recepção o que mudou no cadastro do associado."""
		na_name = self._novo_associado_vinculado()
		if not na_name:
			return

		self._sincronizar_id_escoteiros_novo_associado(na_name)
		self._notificar_registro_criado(na_name)

	def before_insert(self):
		self._handle_novo_associado_pre()
		self._anonymize_cpfs()
		if self.registro:
			self.registro = self.registro.replace(" ", "")
		self._set_status()
		self._fix_phones()
		self._fix_names()

	def before_save(self):
		if self.pais_divorciados == "Não":
			self.tipo_guarda = "-"
		if self.registro:
			self.registro = self.registro.replace(" ", "")
		self._anonymize_cpfs()
		self._set_status()
		self._fix_phones()
		self._fix_names()

		old_doc = self.get_doc_before_save()
		old_funcao_categoria = (
			f"{old_doc.funcao} - {old_doc.categoria}"
			if old_doc and old_doc.funcao and old_doc.categoria
			else None
		)
		new_funcao_categoria = f"{self.funcao} - {self.categoria}" if self.funcao and self.categoria else None
		self.flags.old_funcao_categoria = old_funcao_categoria
		self.flags.new_funcao_categoria = new_funcao_categoria
		# Guardados separadamente para que a sincronização de papéis saiba qual
		# perfil a automação teria atribuído antes da alteração.
		self.flags.old_categoria = getattr(old_doc, "categoria", None) if old_doc else None
		self.flags.old_funcao = getattr(old_doc, "funcao", None) if old_doc else None
		self.flags.old_status_no_grupo = getattr(old_doc, "status_no_grupo", None) if old_doc else None
		self.flags.status_no_grupo_changed = self.flags.old_status_no_grupo != self.status_no_grupo

		# --- Detecta alteração no child table historico_no_grupo ---
		old_hist = self._serialize_hist(getattr(old_doc, "historico_no_grupo", []) if old_doc else [])
		new_hist = self._serialize_hist(getattr(self, "historico_no_grupo", []))
		self.flags.historico_no_grupo_changed = old_hist != new_hist

	def after_insert(self):
		self._handle_novo_associado_post()
		self._processar_vinculo_com_recepcao()
		if cint(frappe.db.get_single_value("Configuracoes de Associados", "criar_usuarios")) != 1:
			pass
		else:
			log = _assoc_logger()
			log.info(f"[ENQUEUE CREATE] {self.name}")
			frappe.enqueue(
				"gris.api.users.user_manager.create_associate_user",
				job_name=f"create_associate_user:{self.name}",
				queue="default",
				associate_name=self.name,
				enqueue_after_commit=True,
			)

		if self.status_no_grupo == "Ativo" and self.id_escoteiros:
			frappe.enqueue(
				"gris.api.google_workspace.access_manager.sync_global_access_for_associate",
				job_name=f"sync_google_workspace_global_access:{self.name}",
				queue="default",
				associate_name=self.name,
				enqueue_after_commit=True,
			)

	def on_update(self):
		# Ignora primeira criação: after_insert já tratou
		if self.flags.get("in_insert"):
			return
		self._processar_vinculo_com_recepcao()
		log = _assoc_logger()
		log.info(
			f"[ENQUEUE UPDATE] {self.name} old='{getattr(self.flags, 'old_funcao_categoria', None)}' "
			f"new='{getattr(self.flags, 'new_funcao_categoria', None)}'"
		)
		frappe.enqueue(
			"gris.api.users.user_manager.update_associate_user",
			job_name=f"update_associate_user:{self.name}",
			queue="default",
			associate_name=self.name,
			old_funcao_categoria=getattr(self.flags, "old_funcao_categoria", None),
			new_funcao_categoria=getattr(self.flags, "new_funcao_categoria", None),
			old_categoria=getattr(self.flags, "old_categoria", None),
			old_funcao=getattr(self.flags, "old_funcao", None),
			enqueue_after_commit=True,
		)
		# Se houve alteração no histórico, atualiza série temporal de associados
		if self.flags.get("historico_no_grupo_changed"):
			log.info(f"[ENQUEUE METRICS] {self.name} historico_no_grupo modificado")
			frappe.enqueue(
				"gris.api.users.user_metrics.update_associates_time_series",
				job_name="update_associates_time_series",
				queue="default",
				enqueue_after_commit=True,
			)

		if self.status_no_grupo == "Ativo" and self.id_escoteiros:
			frappe.enqueue(
				"gris.api.google_workspace.access_manager.sync_global_access_for_associate",
				job_name=f"sync_google_workspace_global_access:{self.name}",
				queue="default",
				associate_name=self.name,
				enqueue_after_commit=True,
			)

		if self.flags.get("status_no_grupo_changed") and self.status_no_grupo == "Inativo":
			frappe.enqueue(
				"gris.api.google_workspace.access_manager.revoke_all_access_for_associate",
				job_name=f"revoke_google_workspace_access:{self.name}",
				queue="default",
				associate_name=self.name,
				enqueue_after_commit=True,
			)

			# Só jovem tem chefe de seção para avisar. A desistência vinda do funil já mandou
			# o aviso com o nome legível e marca ``ignore_notificacoes`` para não repetir aqui.
			if (self.categoria or "").strip() == "Beneficiário" and not self.flags.get("ignore_notificacoes"):
				frappe.enqueue(
					"gris.api.recepcao_mensagens.notificar_desistencia",
					job_name=f"aviso_desligamento_beneficiario:{self.name}",
					queue="short",
					enqueue_after_commit=True,
					nome_completo=self.nome_completo,
					sexo=self.sexo,
					ramo=self.ramo,
				)
