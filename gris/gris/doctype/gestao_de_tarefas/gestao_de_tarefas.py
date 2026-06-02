from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

TASK_FIELDS: tuple[str, ...] = (
	"board",
	"descricao",
	"responsavel",
	"status",
	"data_inicio",
	"prazo",
	"data_entrega",
	"observacoes",
)

TASK_STATUS_OPTIONS: frozenset[str] = frozenset(
	{"Nao iniciado", "Em andamento", "Atrasado", "Concluido", "Cancelado"}
)

TASK_STATUS_NOT_STARTED = "Nao iniciado"
TASK_STATUS_DONE = "Concluido"
TASK_STATUS_LATE = "Atrasado"
TASK_STATUS_CANCELLED = "Cancelado"


class GestaodeTarefas(Document):
	def validate(self) -> None:
		self._validate_dates()
		self._normalize_status_dates()

	def _validate_dates(self) -> None:
		if self.data_inicio and self.prazo and getdate(self.data_inicio) > getdate(self.prazo):
			frappe.throw(
				_("Tarefa '{0}' com data de inicio maior que prazo.").format(self.descricao or self.name)
			)

	def _normalize_status_dates(self) -> None:
		status = (self.status or "").strip()
		if status == TASK_STATUS_DONE and not self.data_entrega:
			self.data_entrega = nowdate()
		if status != TASK_STATUS_DONE and self.data_entrega and status != TASK_STATUS_CANCELLED:
			self.data_entrega = None


def validar_tarefas_atrasadas() -> None:
	"""Marca tarefas com prazo vencido como 'Atrasado'.

	Substitui o scheduler antigo que iterava projeto-a-projeto. Uma unica query
	agregada localiza candidatos e o update e feito por documento para preservar
	hooks (track_changes, version) e a permissao do scheduler.
	"""
	hoje = nowdate()
	candidates = frappe.db.sql(
		"""
		SELECT name
		FROM `tabGestao de Tarefas`
		WHERE status NOT IN ('Concluido', 'Cancelado', 'Atrasado')
			AND prazo IS NOT NULL
			AND prazo < %s
		""",
		(hoje,),
		as_dict=False,
	)

	for (task_name,) in candidates or []:
		try:
			frappe.db.set_value("Gestao de Tarefas", task_name, "status", TASK_STATUS_LATE)
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=_("Falha ao marcar tarefa atrasada"),
			)
