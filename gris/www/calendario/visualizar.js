frappe.ready(() => {
	const calendar = document.getElementById("activity-calendar");
	const yearFilter = document.getElementById("year-filter");
	const monthFilter = document.getElementById("month-filter");
	const sectionFilter = document.getElementById("section-filter");
	const activitySearch = document.getElementById("activity-search");
	const exportButton = document.getElementById("btn-export-calendar");
	const sourceEvents = calendar ? (calendar.events || []).map(cloneEvent) : [];
	const allSections = calendar ? (calendar.activeCategories || []) : [];

	const applyFilters = ({ resetAnchor = false } = {}) => {
		const year = Number(getSelectValue(yearFilter) || new Date().getFullYear());
		const selectedMonth = getSelectValue(monthFilter) || "";
		const requestedSections = getMultipleSelectValue(sectionFilter);
		const activeSections = requestedSections.length ? requestedSections : allSections;
		const searchTerm = normalizeText(activitySearch ? activitySearch.value : "");

		if (calendar) {
			const filteredEvents = sourceEvents.filter((event) => {
				const eventSection = event.category || "Diretoria";
				return (
					activeSections.includes(eventSection) &&
					eventMatchesMonth(event, year, selectedMonth) &&
					(!searchTerm || normalizeText(event.title || "").includes(searchTerm))
				);
			});

			calendar.events = filteredEvents;
			calendar.setActiveCategories(activeSections);

			if (selectedMonth) {
				const monthRange = getMonthRange(year, selectedMonth);
				calendar.setListRange(monthRange.start, monthRange.end);
				if (resetAnchor) {
					calendar.goToDate(monthRange.start);
				}
			} else {
				calendar.setListRange(`${year}-01-01`, `${year}-12-31`);
				if (resetAnchor) {
					calendar.goToDate(getDefaultAnchorDate(year));
				}
			}
		}

		updateHolidayList(selectedMonth);
	};

	if (yearFilter) {
		yearFilter.addEventListener("change", () => {
			const url = new URL(window.location.href);
			const year = getSelectValue(yearFilter);
			const selectedMonth = getSelectValue(monthFilter);
			if (year) {
				url.searchParams.set("year", year);
			}
			if (selectedMonth) {
				url.searchParams.set("month", selectedMonth);
			} else {
				url.searchParams.delete("month");
			}
			window.location.href = url.toString();
		});
	}

	if (monthFilter) {
		monthFilter.addEventListener("change", () => applyFilters({ resetAnchor: true }));
	}

	if (sectionFilter) {
		sectionFilter.addEventListener("change", () => applyFilters());
	}

	if (activitySearch) {
		activitySearch.addEventListener("input", () => applyFilters());
	}

	if (calendar) {
		calendar.addEventListener("gris:calendar:event-click", (event) => {
			const detail = event.detail || {};
			const data = detail.data || {};
			setText("view-modal-atividade", data.atividade || detail.title || "-");
			setText("view-modal-inicio", data.inicio || "-");
			setText("view-modal-termino", data.termino || "-");
			setText("view-modal-hora", formatTimeWindow(data.hora_inicio, data.hora_termino));
			setText("view-modal-secao", data.secao || detail.category || "-");
			setText("view-modal-local", data.local || "-");
			setText("view-modal-nivel", data.nivel || "-");

			const emptyDayFlag = document.getElementById("view-modal-sem-atividade-group");
			if (emptyDayFlag) {
				emptyDayFlag.classList.toggle("hidden", String(data.sem_atividade || 0) !== "1");
			}

			openDialog("activity-detail-dialog");
		});
	}

	if (exportButton) {
		exportButton.addEventListener("click", () => {
			const year = getSelectValue(yearFilter) || String(new Date().getFullYear());
			const month = getSelectValue(monthFilter) || "";
			const sections = getMultipleSelectValue(sectionFilter);
			const showEmptyDays = getCalendarShowAllDays(calendar) ? 1 : 0;
			const params = new URLSearchParams({
				year,
				month,
				show_empty_days: String(showEmptyDays),
				sections: JSON.stringify(sections),
			});

			window.open(`/api/method/gris.www.calendario.visualizar.export_calendar?${params.toString()}`, "_blank");
		});
	}

	document.addEventListener("click", (event) => {
		const holidayButton = event.target.closest("[data-holiday-button]");
		if (!holidayButton) {
			return;
		}

		setText("holiday-modal-name", holidayButton.dataset.holidayName || "Feriado");
		setText("holiday-modal-desc", holidayButton.dataset.holidayDesc || "Sem descrição disponível.");
		setHolidayBadge(holidayButton.dataset.holidayType || "Geral", holidayButton.dataset.holidayBadgeVariant || "outline");
		openDialog("holiday-dialog");
	});

	applyFilters();
});

function cloneEvent(event) {
	return {
		...event,
		data: { ...(event.data || {}) },
	};
}

function getSelectValue(element) {
	if (!element) {
		return "";
	}
	const value = element.value;
	return Array.isArray(value) ? value[0] || "" : (value || "");
}

function getMultipleSelectValue(element) {
	if (!element) {
		return [];
	}
	const value = element.value;
	return Array.isArray(value) ? value : [];
}

function parseISODate(value) {
	if (!value) {
		return null;
	}
	if (value instanceof Date) {
		return new Date(value.getTime());
	}
	const stringValue = String(value);
	const dateOnly = stringValue.match(/^(\d{4})-(\d{2})-(\d{2})$/);
	if (dateOnly) {
		return new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
	}
	const parsed = new Date(stringValue);
	return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function eventMatchesMonth(event, year, selectedMonth) {
	if (!selectedMonth) {
		return true;
	}
	const { start, end } = getMonthRange(year, selectedMonth, true);
	const eventStart = parseISODate(event.start);
	const eventEnd = parseISODate(event.end || event.start);
	if (!eventStart || !eventEnd) {
		return false;
	}
	return eventStart <= end && eventEnd >= start;
}

function getMonthRange(year, month, asDates = false) {
	const monthNumber = Number(month);
	const lastDay = new Date(year, monthNumber, 0).getDate();
	if (asDates) {
		return {
			start: new Date(year, monthNumber - 1, 1, 0, 0, 0, 0),
			end: new Date(year, monthNumber - 1, lastDay, 23, 59, 59, 999),
		};
	}
	return {
		start: `${year}-${String(monthNumber).padStart(2, "0")}-01`,
		end: `${year}-${String(monthNumber).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`,
	};
}

function getDefaultAnchorDate(year) {
	const today = new Date();
	if (today.getFullYear() === year) {
		return formatDateKey(today);
	}
	return `${year}-01-01`;
}

function formatDateKey(date) {
	return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatTimeWindow(start, end) {
	if (!start && !end) {
		return "-";
	}
	if (start && end) {
		return `${start} – ${end}`;
	}
	return start || end || "-";
}

function updateHolidayList(selectedMonth) {
	const holidayButtons = Array.from(document.querySelectorAll("[data-holiday-button]"));
	const holidayList = document.getElementById("holiday-list");
	const holidayEmptyState = document.getElementById("holiday-empty-state");
	let visibleCount = 0;

	for (const button of holidayButtons) {
		const shouldShow = !selectedMonth || button.dataset.holidayMonth === selectedMonth;
		button.hidden = !shouldShow;
		if (shouldShow) {
			visibleCount += 1;
		}
	}

	if (holidayList) {
		holidayList.hidden = visibleCount === 0;
	}
	if (holidayEmptyState) {
		holidayEmptyState.classList.toggle("hidden", visibleCount !== 0);
	}
}

function openDialog(id) {
	const dialog = document.getElementById(id);
	if (!dialog || typeof dialog.showModal !== "function") {
		return;
	}
	if (!dialog.open) {
		dialog.showModal();
	}
}

function setText(id, value) {
	const element = document.getElementById(id);
	if (element) {
		element.textContent = value || "-";
	}
}

function setHolidayBadge(label, variant) {
	const badge = document.getElementById("holiday-modal-type");
	if (!badge) {
		return;
	}

	badge.textContent = label;
	if (variant === "outline") {
		badge.className = "badge-outline";
		return;
	}
	if (["success", "warning", "info", "destructive"].includes(variant)) {
		badge.className = `badge badge-${variant}`;
		return;
	}
	badge.className = "badge";
}

function getCalendarShowAllDays(calendar) {
	const checkbox = calendar?.querySelector("[data-calendar-list-show-all-days]");
	return checkbox ? checkbox.checked : true;
}

function normalizeText(text) {
	return String(text)
		.toLowerCase()
		.normalize("NFD")
		.replace(/\p{M}/gu, "");
}
