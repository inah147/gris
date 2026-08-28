const DEFAULT_LEVEL = "Local";
let reopenEditDialogAfterDeleteClose = false;

frappe.ready(() => {
	initYearFilter();
	initCopyData();
	initStartEmpty();
	initNewEventDialog();
	initEditEventDialog();
	initDeleteEventDialog();
	initCalendarInteractions();
	initReconciliation();
	initSuccessDialog();
	initHolidayDialog();

	// Visualização padrão: lista. Mobile (< 640px) usa variante "default"; desktop usa "category".
	if (window.innerWidth < 640) {
		requestAnimationFrame(() => {
			document.getElementById("simulation-calendar")?.setListVariant?.("default");
		});
	}
});

function escapeHtml(value) {
	return String(value || "")
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/\"/g, "&quot;")
		.replace(/'/g, "&#39;");
}

function getFieldElementById(fieldId) {
	return document.getElementById(fieldId);
}

function getFieldValueById(fieldId) {
	const element = getFieldElementById(fieldId);
	if (!element) return "";
	return element.value || "";
}

function setFieldValueWhenReady(element, value) {
	if (!element) return;

	const apply = () => {
		element.value = value || "";
	};

	if (
		(element.classList?.contains("select") && element.dataset.selectInitialized === "true") ||
		(element.classList?.contains("datepicker") &&
			element.dataset.datepickerInitialized === "true") ||
		(!element.classList?.contains("select") &&
			!element.classList?.contains("datepicker") &&
			typeof element.value !== "undefined")
	) {
		apply();
		return;
	}

	element.addEventListener("basecoat:initialized", apply, { once: true });
}

function setComponentDisabled(fieldId, disabled) {
	const root = getFieldElementById(fieldId);
	if (!root) return;

	root.classList.toggle("is-disabled", !!disabled);

	const trigger = document.getElementById(`${fieldId}-trigger`);
	if (trigger) trigger.disabled = !!disabled;

	const searchInput = root.querySelector("header input");
	if (searchInput) searchInput.disabled = !!disabled;

	const hiddenInput = root.querySelector('input[type="hidden"]');
	if (hiddenInput) hiddenInput.disabled = !!disabled;
}

function openDialogById(dialogId) {
	const dialog = document.getElementById(dialogId);
	if (dialog && typeof dialog.showModal === "function" && !dialog.open) {
		dialog.showModal();
	}
}

function closeDialogById(dialogId) {
	const dialog = document.getElementById(dialogId);
	if (dialog && typeof dialog.close === "function" && dialog.open) {
		dialog.close();
	}
}

function setElementHidden(element, hidden) {
	if (element) {
		element.hidden = !!hidden;
	}
}

function bindDialogCloseButtons(dialogId, selector) {
	const dialog = document.getElementById(dialogId);
	if (!dialog) return;

	dialog.querySelectorAll(selector).forEach((button) => {
		button.addEventListener("click", () => closeDialogById(dialogId));
	});
}

function normalizeDateValue(value) {
	const normalized = String(value || "").trim();
	if (!normalized) return "";
	return normalized.split("T")[0].split(" ")[0];
}

function toApiDateTime(value, fallbackTime) {
	const dateValue = normalizeDateValue(value);
	return dateValue ? `${dateValue} ${fallbackTime}` : "";
}

function getSelectedYear() {
	const yearFromField = getFieldValueById("year-filter");
	if (yearFromField) return yearFromField;

	const url = new URL(window.location.href);
	return url.searchParams.get("year") || String(new Date().getFullYear());
}

function getDefaultEventDate() {
	const selectedYear = Number(getSelectedYear() || new Date().getFullYear());
	const today = new Date();
	const todayIso = today.toISOString().slice(0, 10);

	if (selectedYear === today.getFullYear()) {
		return todayIso;
	}

	return `${selectedYear}-01-01`;
}

function showApiError(result, fallbackMessage) {
	const message = result?.message?.message || result?.message || fallbackMessage;
	frappe.msgprint({
		title: __("Erro"),
		indicator: "red",
		message,
	});
}

function reloadPage() {
	window.location.reload();
}

// Atualiza o calendário in-place após uma mutação (criar/editar/excluir), sem
// recarregar a página: rebusca os eventos/categorias serializados do servidor e os
// aplica ao componente, preservando a posição de scroll (a lista rola dentro de
// `[data-calendar-body]`, não na janela). Se algo falhar, cai para o reload completo.
function refreshCalendarEvents() {
	const calendarRoot = document.getElementById("simulation-calendar");
	if (!calendarRoot || typeof calendarRoot.setCategories !== "function") {
		reloadPage();
		return;
	}

	frappe.call({
		method: "gris.www.calendario.simulacao_calendario.get_calendar_events",
		args: { year: getSelectedYear() },
		callback(result) {
			const payload = result.message || {};
			if (!Array.isArray(payload.events)) {
				reloadPage();
				return;
			}

			const calendarBody = calendarRoot.querySelector("[data-calendar-body]");
			const bodyTop = calendarBody ? calendarBody.scrollTop : 0;
			const windowY = window.scrollY || 0;

			if (Array.isArray(payload.categories)) {
				calendarRoot.setCategories(payload.categories);
			}
			calendarRoot.events = payload.events; // re-render síncrono

			if (calendarBody) calendarBody.scrollTop = bodyTop;
			window.scrollTo(0, windowY);
		},
		error() {
			reloadPage();
		},
	});
}

function applySemAtividadeState(checkboxEl, localEl, levelFieldId) {
	const isSemAtividade = checkboxEl ? checkboxEl.checked : false;
	if (localEl) {
		localEl.disabled = isSemAtividade;
		if (isSemAtividade) {
			localEl.value = "";
		}
	}

	const levelElement = getFieldElementById(levelFieldId);
	if (levelElement) {
		if (isSemAtividade) {
			setFieldValueWhenReady(levelElement, DEFAULT_LEVEL);
		}
		setComponentDisabled(levelFieldId, isSemAtividade);
	}
}

function applyAberturaGeralState(checkboxEl, atividadeEl) {
	const isAberturaGeral = checkboxEl ? checkboxEl.checked : false;
	if (!atividadeEl) return;

	if (isAberturaGeral) {
		atividadeEl.value = "Abertura Geral";
		atividadeEl.disabled = true;
		return;
	}

	atividadeEl.disabled = false;
}

function setupMutualExclusion(primaryCheckbox, secondaryCheckbox) {
	if (!primaryCheckbox || !secondaryCheckbox) return;

	primaryCheckbox.addEventListener("change", () => {
		if (primaryCheckbox.checked) {
			secondaryCheckbox.checked = false;
			secondaryCheckbox.dispatchEvent(new Event("change"));
		}
	});

	secondaryCheckbox.addEventListener("change", () => {
		if (secondaryCheckbox.checked) {
			primaryCheckbox.checked = false;
			primaryCheckbox.dispatchEvent(new Event("change"));
		}
	});
}

function setSectionCheckboxes(name, selectedValues) {
	const values = new Set(selectedValues || []);
	document.querySelectorAll(`input[name="${name}"]`).forEach((checkbox) => {
		checkbox.checked = values.has(checkbox.value);
	});
}

function formatDateForUser(value) {
	const normalized = normalizeDateValue(value);
	if (!normalized) return "-";

	try {
		if (frappe.datetime?.str_to_user) {
			return frappe.datetime.str_to_user(normalized);
		}
	} catch (error) {
		// Ignore formatter issues and fall back to raw ISO.
	}

	return normalized;
}

function formatMaybeBoolean(value) {
	if (value === 1 || value === "1" || value === true) return "Sim";
	if (value === 0 || value === "0" || value === false) return "Não";
	return null;
}

function formatDiffValue(value) {
	const boolValue = formatMaybeBoolean(value);
	if (boolValue) return escapeHtml(boolValue);
	if (value === undefined || value === null || value === "") {
		return '<span class="simulation-reconcile-muted">Vazio</span>';
	}
	if (/^\d{4}-\d{2}-\d{2}/.test(String(value))) {
		return escapeHtml(formatDateForUser(value));
	}
	return escapeHtml(String(value));
}

function unscrub(value) {
	if (frappe.model?.unscrub) {
		return frappe.model.unscrub(value);
	}
	return String(value || "")
		.replace(/_/g, " ")
		.replace(/\b\w/g, (char) => char.toUpperCase());
}

function initYearFilter() {
	const yearFilter = document.getElementById("year-filter");
	if (!yearFilter) return;

	yearFilter.addEventListener("change", () => {
		const url = new URL(window.location.href);
		url.searchParams.set("year", getFieldValueById("year-filter"));
		url.searchParams.delete("start_empty");
		window.location.href = url.toString();
	});
}

function initCopyData() {
	const copyButton = document.getElementById("btn-copy-data");
	if (!copyButton) return;

	copyButton.addEventListener("click", () => {
		const sourceYear = getFieldValueById("source-year");
		const targetYear = copyButton.getAttribute("data-target-year");

		if (!sourceYear) {
			frappe.msgprint(__("Selecione um ano de origem."));
			return;
		}

		frappe.confirm(
			`Tem certeza que deseja copiar os dados de ${sourceYear} para a simulação de ${targetYear}?`,
			() => {
				frappe.call({
					method: "gris.api.calendario.simulation.copy_calendar_data",
					args: {
						source_year: sourceYear,
						target_year: targetYear,
					},
					freeze: true,
					freeze_message: "Copiando dados...",
					callback(result) {
						if (result.message?.success) {
							frappe.show_alert({
								message: result.message.message,
								indicator: "green",
							});
							reloadPage();
							return;
						}
						showApiError(result, "Erro ao copiar os dados.");
					},
				});
			},
		);
	});
}

function initStartEmpty() {
	const startButton = document.getElementById("btn-start-empty");
	if (!startButton) return;

	startButton.addEventListener("click", () => {
		const targetYear = startButton.getAttribute("data-target-year");
		const url = new URL(window.location.href);
		url.searchParams.set("year", targetYear);
		url.searchParams.set("start_empty", "1");
		window.location.href = url.toString();
	});
}

function resetNewEventForm(defaultDate, selectedSection) {
	const atividadeInput = document.getElementById("modal-atividade");
	const localInput = document.getElementById("modal-local");
	const semAtividadeInput = document.getElementById("modal-sem-atividade");
	const aberturaGeralInput = document.getElementById("modal-abertura-geral");
	const inicioInput = document.getElementById("modal-inicio");
	const terminoInput = document.getElementById("modal-termino");
	const nivelInput = document.getElementById("modal-nivel");

	if (atividadeInput) {
		atividadeInput.value = "";
		atividadeInput.disabled = false;
	}
	if (localInput) {
		localInput.value = "";
		localInput.disabled = false;
	}
	if (semAtividadeInput) semAtividadeInput.checked = false;
	if (aberturaGeralInput) aberturaGeralInput.checked = false;

	setFieldValueWhenReady(inicioInput, defaultDate);
	setFieldValueWhenReady(terminoInput, defaultDate);
	setFieldValueWhenReady(nivelInput, DEFAULT_LEVEL);
	setSectionCheckboxes("modal-secao", selectedSection ? [selectedSection] : []);

	applySemAtividadeState(semAtividadeInput, localInput, "modal-nivel");
	applyAberturaGeralState(aberturaGeralInput, atividadeInput);
}

function openNewEventDialogForDate(date) {
	if (!document.getElementById("new-activity-modal")) return;
	resetNewEventForm(date || getDefaultEventDate(), null);
	openDialogById("new-activity-modal");
}

function initNewEventDialog() {
	const dialog = document.getElementById("new-activity-modal");
	if (!dialog) return;

	const newEventButton = document.getElementById("btn-new-event");
	const cancelButton = document.getElementById("cancel-modal");
	const saveButton = document.getElementById("save-modal");
	const semAtividadeInput = document.getElementById("modal-sem-atividade");
	const aberturaGeralInput = document.getElementById("modal-abertura-geral");
	const atividadeInput = document.getElementById("modal-atividade");
	const localInput = document.getElementById("modal-local");

	setupMutualExclusion(semAtividadeInput, aberturaGeralInput);

	semAtividadeInput?.addEventListener("change", () => {
		applySemAtividadeState(semAtividadeInput, localInput, "modal-nivel");
	});
	aberturaGeralInput?.addEventListener("change", () => {
		applyAberturaGeralState(aberturaGeralInput, atividadeInput);
	});

	newEventButton?.addEventListener("click", () => {
		openNewEventDialogForDate(getDefaultEventDate());
	});

	cancelButton?.addEventListener("click", () => closeDialogById("new-activity-modal"));

	saveButton?.addEventListener("click", () => {
		const atividade = document.getElementById("modal-atividade")?.value || "";
		const inicioDate = getFieldValueById("modal-inicio");
		const terminoDate = getFieldValueById("modal-termino");
		const secoes = Array.from(
			document.querySelectorAll('input[name="modal-secao"]:checked'),
		).map((item) => item.value);
		const local = document.getElementById("modal-local")?.value || "";
		const nivel = getFieldValueById("modal-nivel");
		const semAtividade = document.getElementById("modal-sem-atividade")?.checked ? 1 : 0;
		const aberturaGeral = document.getElementById("modal-abertura-geral")?.checked ? 1 : 0;

		if (!atividade || !inicioDate || !terminoDate || secoes.length === 0) {
			frappe.msgprint(__("Preencha todos os campos obrigatórios."));
			return;
		}

		if (normalizeDateValue(terminoDate) < normalizeDateValue(inicioDate)) {
			frappe.msgprint(__("A data de término não pode ser anterior à data de início."));
			return;
		}

		frappe.call({
			method: "gris.api.calendario.simulation.create_simulation_event",
			args: {
				atividade,
				inicio: toApiDateTime(inicioDate, "08:00:00"),
				termino: toApiDateTime(terminoDate, "12:00:00"),
				local,
				nivel,
				sem_atividade: semAtividade,
				abertura_geral: aberturaGeral,
				secoes: JSON.stringify(secoes),
			},
			freeze: true,
			freeze_message: "Salvando...",
			callback(result) {
				if (result.message?.success) {
					closeDialogById("new-activity-modal");
					frappe.show_alert({ message: result.message.message, indicator: "green" });
					refreshCalendarEvents();
					return;
				}
				showApiError(result, "Erro ao criar o evento simulado.");
			},
		});
	});
}

function openEditDialog(data) {
	if (!data) return;

	const semAtividadeInput = document.getElementById("edit-sem-atividade");
	const aberturaGeralInput = document.getElementById("edit-abertura-geral");
	const atividadeInput = document.getElementById("edit-atividade");
	const localInput = document.getElementById("edit-local");

	document.getElementById("edit-event-id").value = data.name || data.id || "";
	document.getElementById("edit-atividade").value = data.atividade || "";
	document.getElementById("edit-local").value = data.local || "";
	if (semAtividadeInput) semAtividadeInput.checked = !!Number(data.sem_atividade || 0);
	if (aberturaGeralInput) aberturaGeralInput.checked = !!Number(data.abertura_geral || 0);

	setFieldValueWhenReady(
		document.getElementById("edit-inicio"),
		normalizeDateValue(data.inicio),
	);
	setFieldValueWhenReady(
		document.getElementById("edit-termino"),
		normalizeDateValue(data.termino),
	);
	setFieldValueWhenReady(document.getElementById("edit-secao"), data.secao || "Diretoria");
	setFieldValueWhenReady(document.getElementById("edit-nivel"), data.nivel || DEFAULT_LEVEL);

	applySemAtividadeState(semAtividadeInput, localInput, "edit-nivel");
	applyAberturaGeralState(aberturaGeralInput, atividadeInput);
	openDialogById("edit-activity-modal");
}

function initEditEventDialog() {
	const dialog = document.getElementById("edit-activity-modal");
	if (!dialog) return;

	const cancelButton = document.getElementById("cancel-edit-modal");
	const saveButton = document.getElementById("save-edit-modal");
	const deleteButton = document.getElementById("delete-edit-modal");
	const semAtividadeInput = document.getElementById("edit-sem-atividade");
	const aberturaGeralInput = document.getElementById("edit-abertura-geral");
	const atividadeInput = document.getElementById("edit-atividade");
	const localInput = document.getElementById("edit-local");

	setupMutualExclusion(semAtividadeInput, aberturaGeralInput);

	semAtividadeInput?.addEventListener("change", () => {
		applySemAtividadeState(semAtividadeInput, localInput, "edit-nivel");
	});
	aberturaGeralInput?.addEventListener("change", () => {
		applyAberturaGeralState(aberturaGeralInput, atividadeInput);
	});

	cancelButton?.addEventListener("click", () => closeDialogById("edit-activity-modal"));

	saveButton?.addEventListener("click", () => {
		const eventId = document.getElementById("edit-event-id")?.value || "";
		const atividade = document.getElementById("edit-atividade")?.value || "";
		const inicioDate = getFieldValueById("edit-inicio");
		const terminoDate = getFieldValueById("edit-termino");
		const secao = getFieldValueById("edit-secao");
		const local = document.getElementById("edit-local")?.value || "";
		const nivel = getFieldValueById("edit-nivel");
		const semAtividade = document.getElementById("edit-sem-atividade")?.checked ? 1 : 0;
		const aberturaGeral = document.getElementById("edit-abertura-geral")?.checked ? 1 : 0;

		if (!eventId || !atividade || !inicioDate || !terminoDate || !secao) {
			frappe.msgprint(__("Preencha todos os campos obrigatórios."));
			return;
		}

		if (normalizeDateValue(terminoDate) < normalizeDateValue(inicioDate)) {
			frappe.msgprint(__("A data de término não pode ser anterior à data de início."));
			return;
		}

		frappe.call({
			method: "gris.api.calendario.simulation.update_simulation_event",
			args: {
				event_id: eventId,
				atividade,
				inicio: toApiDateTime(inicioDate, "08:00:00"),
				termino: toApiDateTime(terminoDate, "12:00:00"),
				secao,
				local,
				nivel,
				sem_atividade: semAtividade,
				abertura_geral: aberturaGeral,
			},
			freeze: true,
			freeze_message: "Atualizando...",
			callback(result) {
				if (result.message?.success) {
					closeDialogById("edit-activity-modal");
					frappe.show_alert({ message: result.message.message, indicator: "green" });
					refreshCalendarEvents();
					return;
				}
				showApiError(result, "Erro ao atualizar o evento.");
			},
		});
	});

	deleteButton?.addEventListener("click", () => {
		const eventId = document.getElementById("edit-event-id")?.value || "";
		if (!eventId) return;

		reopenEditDialogAfterDeleteClose = true;
		closeDialogById("edit-activity-modal");
		openDialogById("delete-event-modal");
	});
}

function initDeleteEventDialog() {
	const dialog = document.getElementById("delete-event-modal");
	if (!dialog) return;

	const cancelButton = document.getElementById("cancel-delete-modal");
	const confirmButton = document.getElementById("confirm-delete-modal");

	dialog.addEventListener("close", () => {
		if (!reopenEditDialogAfterDeleteClose) return;

		reopenEditDialogAfterDeleteClose = false;
		requestAnimationFrame(() => {
			if (document.getElementById("edit-event-id")?.value) {
				openDialogById("edit-activity-modal");
			}
		});
	});

	cancelButton?.addEventListener("click", () => {
		closeDialogById("delete-event-modal");
	});

	confirmButton?.addEventListener("click", () => {
		const eventId = document.getElementById("edit-event-id")?.value || "";
		if (!eventId) {
			closeDialogById("delete-event-modal");
			return;
		}

		reopenEditDialogAfterDeleteClose = false;
		closeDialogById("delete-event-modal");

		frappe.call({
			method: "gris.api.calendario.simulation.delete_simulation_event",
			args: { event_id: eventId },
			freeze: true,
			freeze_message: "Excluindo...",
			callback(result) {
				if (result.message?.success) {
					frappe.show_alert({ message: result.message.message, indicator: "green" });
					refreshCalendarEvents();
					return;
				}
				showApiError(result, "Erro ao excluir o evento.");
				openDialogById("edit-activity-modal");
			},
			error(result) {
				showApiError(result, "Erro ao excluir o evento.");
				openDialogById("edit-activity-modal");
			},
		});
	});
}

function initCalendarInteractions() {
	const calendarRoot = document.getElementById("simulation-calendar");
	if (!calendarRoot) return;

	calendarRoot.addEventListener("gris:calendar:event-click", (event) => {
		const detail = event.detail || {};
		const data = detail.data || {};

		if (data.event_type === "holiday") {
			openHolidayDialog(data);
			return;
		}

		if (data.event_type === "simulation" && document.getElementById("edit-activity-modal")) {
			openEditDialog(data);
		}
	});

	// Clique em espaço vazio de um dia (qualquer visualização) abre o diálogo de
	// novo evento já com a data clicada preenchida.
	calendarRoot.addEventListener("gris:calendar:day-click", (event) => {
		const date = event.detail?.date;
		if (!date) return;
		openNewEventDialogForDate(date);
	});
}

function initReconciliation() {
	const button = document.getElementById("btn-reconcile");
	const dialog = document.getElementById("reconcile-modal");
	if (!button || !dialog) return;

	const loading = document.getElementById("reconcile-loading");
	const empty = document.getElementById("reconcile-empty");
	const list = document.getElementById("reconcile-list");
	const tbody = document.getElementById("reconcile-tbody");
	const confirmButton = document.getElementById("btn-confirm-reconcile");
	const selectAllButton = document.getElementById("btn-select-all-apply");
	const switchTemplate = document.getElementById("reconcile-switch-template");

	bindDialogCloseButtons("reconcile-modal", ".close-modal");

	button.addEventListener("click", () => {
		openDialogById("reconcile-modal");
		fetchDifferences();
	});

	selectAllButton?.addEventListener("click", () => {
		tbody
			.querySelectorAll('[data-reconcile-switch-index] input[type="checkbox"]')
			.forEach((input) => {
				input.checked = true;
			});
	});

	function getReconcileTone(type) {
		if (type === "removed") return "destructive";
		if (type === "added") return "secondary";
		return "primary";
	}

	function getStatusConfig(diff) {
		if (diff.type === "added") {
			return {
				label: "Novo na simulação",
				tone: "secondary",
				ignoreLabel: "Não incluir",
				applyLabel: "Adicionar",
			};
		}

		if (diff.type === "removed") {
			return {
				label: "Removido na simulação",
				tone: "destructive",
				ignoreLabel: "Manter oficial",
				applyLabel: "Excluir",
			};
		}

		return {
			label: "Alterado",
			tone: "primary",
			ignoreLabel: "Ignorar",
			applyLabel: "Atualizar",
		};
	}

	function appendHtml(target, html) {
		if (!html) return;

		const fragment = document.createRange().createContextualFragment(html.trim());
		target.appendChild(fragment);
	}

	function buildReconcileSwitch(switchIndex) {
		const group = switchTemplate?.content?.firstElementChild?.cloneNode(true);
		if (!group) return null;

		group.dataset.reconcileSwitchIndex = String(switchIndex);
		const input = group.querySelector('input[type="checkbox"]');
		if (input) {
			input.id = `reconcile-switch-${switchIndex}`;
			input.name = `reconcile-switch-${switchIndex}`;
			input.checked = false;
		}
		return group;
	}

	function setReconcileState(state) {
		setElementHidden(loading, state !== "loading");
		setElementHidden(empty, state !== "empty");
		setElementHidden(list, state !== "list");
	}

	function fetchDifferences() {
		setReconcileState("loading");
		confirmButton.disabled = true;
		confirmButton.onclick = null;
		tbody.innerHTML = "";

		frappe.call({
			method: "gris.www.calendario.simulacao_calendario.get_reconciliation_data",
			args: { year: getSelectedYear() },
			callback(result) {
				const differences = Array.isArray(result.message) ? result.message : [];
				if (differences.length) {
					renderDifferences(differences);
					setReconcileState("list");
					confirmButton.disabled = false;
					return;
				}
				setReconcileState("empty");
			},
			error(result) {
				setReconcileState(null);
				showApiError(result, "Erro ao analisar as diferenças do calendário.");
			},
		});
	}

	function renderDifferences(differences) {
		const fragment = document.createDocumentFragment();
		const switchEls = [];

		differences.forEach((diff, index) => {
			const doc = diff.simulated || diff.official || {};
			const groupName = `recon-${index}`;
			const titleId = `${groupName}-title`;
			const title = `${doc.atividade || "Evento"} (${doc.secao || "Sem seção"})`;
			const startDate = formatDateForUser(doc.inicio);
			const endDate = formatDateForUser(doc.termino);
			const periodLabel = startDate === endDate ? startDate : `${startDate} - ${endDate}`;
			const status = getStatusConfig(diff);

			const row = document.createElement("tr");
			const entryCell = document.createElement("td");
			const actionsCell = document.createElement("td");
			const entry = document.createElement("div");
			entry.className = "simulation-reconcile-entry";

			const header = document.createElement("div");
			header.className = "simulation-reconcile-entry__header";

			const titleElement = document.createElement("div");
			titleElement.id = titleId;
			titleElement.className = "simulation-reconcile-entry__title";
			titleElement.textContent = title;
			header.appendChild(titleElement);

			const statusElement = document.createElement("span");
			statusElement.className = `simulation-reconcile-status simulation-reconcile-status--${status.tone}`;
			statusElement.textContent = status.label;
			header.appendChild(statusElement);

			const meta = document.createElement("div");
			meta.className = "simulation-reconcile-entry__meta";
			meta.textContent = periodLabel;

			entry.appendChild(header);
			entry.appendChild(meta);

			if (diff.type === "modified") {
				const changeItems = (diff.diffs || [])
					.map(
						(field) => `
                        <li>
                            <strong>${escapeHtml(unscrub(field))}</strong>
                            <span class="simulation-reconcile-change__values">
                                <span>${formatDiffValue(diff.official?.[field])}</span>
                                <span class="simulation-reconcile-arrow">-></span>
                                <span>${formatDiffValue(diff.simulated?.[field])}</span>
                            </span>
                        </li>
                    `,
					)
					.join("");

				appendHtml(
					entry,
					`
                    <div class="simulation-reconcile-change-list-wrap">
                        <ul class="simulation-reconcile-change-list">${changeItems}</ul>
                    </div>
                `,
				);
			}

			const switchEl = buildReconcileSwitch(index);
			switchEls.push(switchEl);

			entryCell.appendChild(entry);
			if (switchEl) {
				actionsCell.appendChild(switchEl);
			}

			row.appendChild(entryCell);
			row.appendChild(actionsCell);
			fragment.appendChild(row);
		});

		tbody.replaceChildren(fragment);

		confirmButton.onclick = () => {
			const actions = [];
			differences.forEach((diff, index) => {
				const switchEl = switchEls[index];
				const isChecked = switchEl?.querySelector('input[type="checkbox"]')?.checked;
				if (!isChecked) return;

				if (diff.type === "added") {
					actions.push({ action: "add", doc: diff.simulated, sim_name: diff.key });
					return;
				}
				if (diff.type === "removed") {
					actions.push({ action: "delete", name: diff.key });
					return;
				}
				if (diff.type === "modified") {
					actions.push({
						action: "update",
						name: diff.key,
						doc: diff.simulated,
						sim_name: diff.key,
					});
				}
			});

			if (!actions.length) {
				frappe.msgprint(__("Nenhuma alteração selecionada para aplicação."));
				return;
			}

			submitReconciliation(actions);
		};
	}
}

function submitReconciliation(actions) {
	frappe.call({
		method: "gris.www.calendario.simulacao_calendario.reconcile_calendar",
		args: { actions: JSON.stringify(actions) },
		freeze: true,
		freeze_message: "Aplicando alterações...",
		callback(result) {
			if (result.message?.count !== undefined) {
				closeDialogById("reconcile-modal");
				document.getElementById("success-message").textContent =
					`${result.message.count} alterações aplicadas com sucesso.`;
				openDialogById("success-modal");
				return;
			}
			showApiError(result, "Erro ao conciliar o calendário.");
		},
	});
}

function initSuccessDialog() {
	bindDialogCloseButtons("success-modal", ".close-modal");

	const okButton = document.getElementById("btn-success-ok");
	okButton?.addEventListener("click", () => {
		closeDialogById("success-modal");
		reloadPage();
	});
}

function openHolidayDialog(data) {
	document.getElementById("holiday-modal-name").textContent = data.holiday_name || "Feriado";
	document.getElementById("holiday-modal-type").textContent = data.holiday_type || "Geral";
	document.getElementById("holiday-modal-type").dataset.type = (
		data.holiday_type || "geral"
	).toLowerCase();
	document.getElementById("holiday-modal-desc").textContent =
		data.holiday_desc || "Sem descrição disponível.";
	openDialogById("holiday-modal");
}

function initHolidayDialog() {
	bindDialogCloseButtons("holiday-modal", ".close-modal");
}
