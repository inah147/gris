// Agenda de Visitas — interações cliente.
// Toda a renderização do calendário fica no componente generic em
// public/design_system/components/generated/calendar.html.jinja.
// Esta página apenas escuta o CustomEvent "gris:calendar:event-click"
// para abrir o modal de detalhes da visita.

let currentVisitId = null;
let scheduleAssociates = [];

frappe.ready(function () {
	initCalendarListener();
	initVisitModalActions();
	initRescheduleListeners();
	initScheduleListeners();
});

// ---------- Helpers de dialog ---------------------------------------------

function openDialog(id) {
	const elt = document.getElementById(id);
	if (!elt || typeof elt.showModal !== "function" || elt.open) return;
	try {
		elt.showModal();
	} catch (err) {
		console.error(`Falha ao abrir dialog "${id}":`, err);
		frappe.show_alert({
			message: "Não foi possível abrir o modal. Recarregue a página.",
			indicator: "red",
		});
	}
}

function closeDialog(id) {
	const elt = document.getElementById(id);
	if (elt && elt.open) elt.close();
}

// ---------- Helpers de select Basecoat ------------------------------------

function getSelectValue(id) {
	const elt = document.getElementById(id);
	if (!elt) return "";
	if ("value" in elt) {
		const v = elt.value;
		return v == null ? "" : String(v);
	}
	const hidden = elt.querySelector('input[type="hidden"]');
	return hidden ? hidden.value : "";
}

function repopulateSelect(id, items, placeholder) {
	const oldEl = document.getElementById(id);
	if (!oldEl) return;

	const listbox = oldEl.querySelector('[role="listbox"]');
	const hidden = oldEl.querySelector('input[type="hidden"]');
	const triggerLabel = oldEl.querySelector(":scope > button > span");
	if (!listbox || !hidden || !triggerLabel) return;

	if (placeholder !== undefined && placeholder !== null) {
		oldEl.dataset.placeholder = placeholder;
	}

	listbox.innerHTML = "";
	(items || []).forEach((item, index) => {
		const opt = document.createElement("div");
		opt.id = `${id}-items-${index + 1}`;
		opt.setAttribute("role", "option");
		opt.dataset.value = item.value;
		opt.textContent = item.label;
		listbox.appendChild(opt);
	});

	hidden.value = "";
	triggerLabel.textContent = oldEl.dataset.placeholder || "Selecione…";

	const newEl = oldEl.cloneNode(true);
	newEl.removeAttribute("data-select-initialized");
	oldEl.parentNode.replaceChild(newEl, oldEl);
}

// ---------- Calendário: listener de click ---------------------------------

function getCalendarEl() {
	return document.getElementById("agenda-visitas-calendar");
}

function initCalendarListener() {
	const cal = getCalendarEl();
	if (!cal) return;
	cal.addEventListener("gris:calendar:event-click", (event) => {
		const detail = event.detail || {};
		const data = detail.data || {};
		if (data.type === "visit") openVisitModal(detail, data);
	});
}

function openVisitModal(eventDetail, data) {
	currentVisitId = eventDetail.id;
	document.getElementById("modal-child-name").textContent = data.name || eventDetail.title;
	document.getElementById("modal-child-age").textContent = data.age || "";
	document.getElementById("btn-open-file").href = `/recepcao/ficha_registro?name=${
		data.jovem || ""
	}`;

	const statusContainer = document.getElementById("modal-status-container");
	const btnConfirm = document.getElementById("btn-confirm");
	const btnUnconfirm = document.getElementById("btn-unconfirm");
	const confirmed = !!data.confirmed;

	statusContainer.classList.toggle("hidden", !confirmed);
	btnConfirm.classList.toggle("hidden", confirmed);
	btnUnconfirm.classList.toggle("hidden", !confirmed);

	openDialog("visit-modal");
}

// ---------- Manipulação da lista de eventos do calendário -----------------

function updateCalendarEvent(visitId, mutator) {
	const cal = getCalendarEl();
	if (!cal) return;
	const next = (cal.events || []).map((evt) => {
		if (String(evt.id) !== String(visitId)) return evt;
		return mutator({ ...evt, data: { ...(evt.data || {}) } });
	});
	cal.events = next;
}

function removeCalendarEvent(visitId) {
	const cal = getCalendarEl();
	if (!cal) return;
	cal.events = (cal.events || []).filter((evt) => String(evt.id) !== String(visitId));
}

function setVisitConfirmed(visitId, confirmed) {
	updateCalendarEvent(visitId, (evt) => {
		evt.icon = confirmed ? "circle-check-big" : null;
		evt.icon_color = confirmed ? "var(--success)" : null;
		evt.data.confirmed = confirmed ? 1 : 0;
		return evt;
	});
}

// ---------- Modal de detalhes da visita -----------------------------------

function initVisitModalActions() {
	document.getElementById("btn-confirm").addEventListener("click", () => {
		if (!currentVisitId) return;
		frappe.call({
			method: "gris.www.recepcao.agenda_visitas.confirm_visit",
			args: { visit_name: currentVisitId },
			callback: (r) => {
				if (r.exc) return;
				frappe.show_alert({
					message: "Visita confirmada com sucesso!",
					indicator: "green",
				});
				setVisitConfirmed(currentVisitId, true);
				closeDialog("visit-modal");
			},
		});
	});

	document.getElementById("btn-unconfirm").addEventListener("click", () => {
		if (!currentVisitId) return;
		frappe.call({
			method: "gris.www.recepcao.agenda_visitas.unconfirm_visit",
			args: { visit_name: currentVisitId },
			callback: (r) => {
				if (r.exc) return;
				frappe.show_alert({ message: "Confirmação removida.", indicator: "orange" });
				setVisitConfirmed(currentVisitId, false);
				closeDialog("visit-modal");
			},
		});
	});

	document.getElementById("btn-cancel").addEventListener("click", () => {
		if (!currentVisitId) return;
		frappe.call({
			method: "gris.www.recepcao.agenda_visitas.cancel_visit",
			args: { visit_name: currentVisitId },
			callback: (r) => {
				if (r.exc) return;
				frappe.show_alert({ message: "Visita cancelada.", indicator: "orange" });
				removeCalendarEvent(currentVisitId);
				closeDialog("visit-modal");
			},
		});
	});

	document.getElementById("btn-reschedule").addEventListener("click", () => {
		closeDialog("visit-modal");
		openDialog("reschedule-modal");
		loadRescheduleDates();
	});
}

// ---------- Modal de reagendamento ----------------------------------------

function initRescheduleListeners() {
	const btnSave = document.getElementById("btn-save-reschedule");

	document.addEventListener("change", (event) => {
		if (event.target.closest && event.target.closest("#reschedule-date-combobox")) {
			btnSave.disabled = !getSelectValue("reschedule-date-combobox");
		}
	});

	btnSave.addEventListener("click", () => {
		const selectedDate = getSelectValue("reschedule-date-combobox");
		if (!selectedDate) {
			frappe.msgprint(__("Por favor, selecione uma data."));
			return;
		}
		const visitId = currentVisitId;
		frappe.call({
			method: "gris.www.recepcao.agenda_visitas.reschedule_visit",
			args: { visit_name: visitId, new_date: selectedDate },
			callback: (r) => {
				if (r.exc) return;
				frappe.show_alert({
					message: "Visita reagendada com sucesso!",
					indicator: "green",
				});
				updateCalendarEvent(visitId, (evt) => {
					evt.start = selectedDate;
					evt.end = null;
					return evt;
				});
				window.closeRescheduleModal();
			},
		});
	});
}

function loadRescheduleDates() {
	const btnSave = document.getElementById("btn-save-reschedule");
	btnSave.disabled = true;

	repopulateSelect("reschedule-date-combobox", [], "Carregando datas…");

	frappe.call({
		method: "gris.www.recepcao.agenda_visitas.get_available_visit_dates_for_reschedule",
		args: { visit_name: currentVisitId },
		callback: (r) => {
			if (r.message && r.message.length > 0) {
				repopulateSelect("reschedule-date-combobox", r.message, "Selecione uma data…");
			} else {
				repopulateSelect(
					"reschedule-date-combobox",
					[],
					"Nenhuma data disponível nos próximos 60 dias.",
				);
			}
		},
	});
}

window.closeRescheduleModal = function () {
	closeDialog("reschedule-modal");
};

// ---------- Modal de agendamento ------------------------------------------

function initScheduleListeners() {
	document.addEventListener("change", (event) => {
		if (!event.target.closest) return;
		if (!event.target.closest("#schedule-associate-combobox")) return;

		const associateName = getSelectValue("schedule-associate-combobox");
		if (!associateName) {
			repopulateSelect("schedule-date-combobox", [], "Selecione um associado primeiro");
			return;
		}

		const associate = scheduleAssociates.find((a) => a.name === associateName);
		if (!associate || !associate.ramo) {
			repopulateSelect("schedule-date-combobox", [], "Associado sem Ramo definido");
			return;
		}

		repopulateSelect("schedule-date-combobox", [], "Carregando datas…");
		frappe.call({
			method: "gris.www.recepcao.agenda_visitas.get_available_dates_for_ramo",
			args: { ramo: associate.ramo },
			callback: (r) => {
				if (r.message && r.message.length > 0) {
					repopulateSelect("schedule-date-combobox", r.message, "Selecione uma data…");
				} else {
					repopulateSelect("schedule-date-combobox", [], "Nenhuma data disponível");
				}
			},
		});
	});
}

window.openScheduleModal = function () {
	repopulateSelect("schedule-associate-combobox", [], "Carregando…");
	repopulateSelect("schedule-date-combobox", [], "Selecione um associado primeiro");

	openDialog("schedule-modal");

	frappe.call({
		method: "gris.www.recepcao.agenda_visitas.get_associates_for_scheduling",
		callback: (r) => {
			if (r.message && r.message.length > 0) {
				scheduleAssociates = r.message;
				const items = r.message.map((assoc) => ({
					label: `${assoc.nome_completo} (${assoc.ramo || "Sem Ramo"})`,
					value: assoc.name,
				}));
				repopulateSelect("schedule-associate-combobox", items, "Selecione…");
			} else {
				scheduleAssociates = [];
				repopulateSelect("schedule-associate-combobox", [], "Nenhum associado disponível");
			}
		},
	});
};

window.closeScheduleModal = function () {
	closeDialog("schedule-modal");
};

window.confirmSchedule = function () {
	const associate = getSelectValue("schedule-associate-combobox");
	const date = getSelectValue("schedule-date-combobox");

	if (!associate || !date) {
		frappe.msgprint(__("Selecione um associado e uma data."));
		return;
	}

	frappe.call({
		method: "gris.www.recepcao.agenda_visitas.schedule_visit",
		args: { associate: associate, date: date },
		callback: (r) => {
			if (r.exc) return;
			frappe.show_alert({ message: "Visita agendada com sucesso!", indicator: "green" });
			window.closeScheduleModal();
			setTimeout(() => window.location.reload(), 800);
		},
	});
};
