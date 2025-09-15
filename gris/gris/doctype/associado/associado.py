import datetime
import hashlib
import re

import frappe
from frappe.model.document import Document


def _assoc_logger():
	return frappe.logger("associate_user", allow_site=True, file_count=10)


class Associado(Document):
	def _fix_phones(self):
		if self.telefone:
			num = re.sub(r"\D", "", self.telefone)
			self.telefone = f"+55{num}" if not num.startswith("55") else f"+{num}"
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
		if self.cpf:
			self.cpf = hashlib.md5(self.cpf.encode("utf-8")).hexdigest()
		if self.cpf_responsavel_1:
			self.cpf_responsavel_1 = hashlib.md5(self.cpf_responsavel_1.encode("utf-8")).hexdigest()
		if self.cpf_responsavel_2:
			self.cpf_responsavel_2 = hashlib.md5(self.cpf_responsavel_2.encode("utf-8")).hexdigest()

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

	def validate(self):
		self._set_status()

	def before_insert(self):
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

		# --- Detecta alteração no child table historico_no_grupo ---
		old_hist = self._serialize_hist(getattr(old_doc, "historico_no_grupo", []) if old_doc else [])
		new_hist = self._serialize_hist(getattr(self, "historico_no_grupo", []))
		self.flags.historico_no_grupo_changed = old_hist != new_hist

	def after_insert(self):
		log = _assoc_logger()
		log.info(f"[ENQUEUE CREATE] {self.name}")
		frappe.enqueue(
			"gris.api.users.user_manager.create_associate_user",
			job_name=f"create_associate_user:{self.name}",
			queue="default",
			associate_name=self.name,
			enqueue_after_commit=True,
		)

	def on_update(self):
		# Ignora primeira criação: after_insert já tratou
		if self.flags.get("in_insert"):
			return
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
			# old_funcao_categoria=getattr(self.flags, "old_funcao_categoria", None),
			old_funcao_categoria=getattr(self.flags, "old_funcao_categoria", None),
			new_funcao_categoria=getattr(self.flags, "new_funcao_categoria", None),
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
