(() => {
	const ISO = (d) => {
		const y = d.getFullYear();
		const m = String(d.getMonth() + 1).padStart(2, "0");
		const day = String(d.getDate()).padStart(2, "0");
		return `${y}-${m}-${day}`;
	};

	const parseISO = (str) => {
		if (!str) return null;
		const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2})?)?$/.exec(str);
		if (!m) return null;
		const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
		if (Number.isNaN(d.getTime())) return null;
		return d;
	};

	const parseTimeFromISO = (str) => {
		if (!str) return null;
		const m = /^\d{4}-\d{2}-\d{2}[T ](\d{2}):(\d{2})(?::\d{2})?$/.exec(str);
		if (!m) return null;
		return `${m[1]}:${m[2]}`;
	};

	const currentTime = () => {
		const d = new Date();
		return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(
			2,
			"0"
		)}`;
	};

	const isValidTime = (str) => /^\d{2}:\d{2}$/.test(String(str || ""));

	const stripTime = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

	const sameDay = (a, b) =>
		a &&
		b &&
		a.getFullYear() === b.getFullYear() &&
		a.getMonth() === b.getMonth() &&
		a.getDate() === b.getDate();

	const formatDisplay = (d, locale) =>
		new Intl.DateTimeFormat(locale, {
			day: "2-digit",
			month: "2-digit",
			year: "numeric",
		}).format(d);

	const formatTitle = (d, locale) => {
		const txt = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(d);
		return txt.charAt(0).toUpperCase() + txt.slice(1);
	};

	const weekdayLabels = (locale) => {
		const base = new Date(2024, 11, 1); // Sunday
		const fmt = new Intl.DateTimeFormat(locale, { weekday: "short" });
		const labels = [];
		for (let i = 0; i < 7; i++) {
			const d = new Date(base.getFullYear(), base.getMonth(), base.getDate() + i);
			let label = fmt.format(d);
			label = label.replace(".", "");
			label = label.charAt(0).toUpperCase() + label.slice(1);
			labels.push(label);
		}
		return labels;
	};

	const initDatepicker = (root) => {
		const trigger = root.querySelector("[aria-haspopup='dialog']");
		const popover = root.querySelector("[data-datepicker-popover]");
		const titleEl = root.querySelector("[data-datepicker-title]");
		const gridEl = root.querySelector("[data-datepicker-grid]");
		const weekdaysEl = root.querySelector("[data-datepicker-weekdays]");
		const labelEl = root.querySelector("[data-datepicker-label]");
		const prevBtn = root.querySelector("[data-datepicker-prev]");
		const nextBtn = root.querySelector("[data-datepicker-next]");
		const clearBtn = root.querySelector("[data-datepicker-clear]");
		const todayBtn = root.querySelector("[data-datepicker-today]");
		const timeInput = root.querySelector("[data-datepicker-time]");
		const confirmBtn = root.querySelector("[data-datepicker-confirm]");

		if (!trigger || !popover || !titleEl || !gridEl) {
			console.error("Datepicker initialisation failed", root);
			return;
		}

		const mode = root.dataset.mode === "range" ? "range" : "single";
		const withTime = mode === "single" && root.dataset.withTime === "true";
		const locale = root.dataset.locale || "pt-BR";
		const placeholder = root.dataset.placeholder || "Selecione uma data";
		const minDate = parseISO(root.dataset.min || "");
		const maxDate = parseISO(root.dataset.max || "");

		const valueInput = root.querySelector("[data-datepicker-value]");
		const startInput = root.querySelector("[data-datepicker-value-start]");
		const endInput = root.querySelector("[data-datepicker-value-end]");

		const initialSingleRaw = valueInput?.value || "";
		const initialTime = withTime ? parseTimeFromISO(initialSingleRaw) : null;

		const state = {
			cursor: new Date(),
			single: parseISO(initialSingleRaw),
			start: parseISO(startInput?.value || ""),
			end: parseISO(endInput?.value || ""),
			time: withTime ? initialTime || "" : "",
			hover: null,
			pendingRangeStart: null,
		};

		if (withTime && timeInput) {
			timeInput.value = state.time || "";
		}

		if (mode === "single" && state.single) {
			state.cursor = new Date(state.single);
		} else if (mode === "range" && state.start) {
			state.cursor = new Date(state.start);
		}
		state.cursor.setDate(1);

		weekdaysEl.innerHTML = weekdayLabels(locale)
			.map((w) => `<span>${w}</span>`)
			.join("");

		const isDisabled = (d) => {
			if (minDate && stripTime(d) < stripTime(minDate)) return true;
			if (maxDate && stripTime(d) > stripTime(maxDate)) return true;
			return false;
		};

		const updateLabel = () => {
			if (mode === "single") {
				if (state.single) {
					const dateText = formatDisplay(state.single, locale);
					labelEl.textContent =
						withTime && isValidTime(state.time)
							? `${dateText} ${state.time}`
							: dateText;
					labelEl.classList.remove("datepicker-trigger__label--placeholder");
				} else {
					labelEl.textContent = placeholder;
					labelEl.classList.add("datepicker-trigger__label--placeholder");
				}
			} else {
				if (state.start && state.end) {
					labelEl.textContent = `${formatDisplay(state.start, locale)} → ${formatDisplay(
						state.end,
						locale
					)}`;
					labelEl.classList.remove("datepicker-trigger__label--placeholder");
				} else if (state.start) {
					labelEl.textContent = `${formatDisplay(state.start, locale)} → …`;
					labelEl.classList.remove("datepicker-trigger__label--placeholder");
				} else {
					labelEl.textContent = placeholder;
					labelEl.classList.add("datepicker-trigger__label--placeholder");
				}
			}
		};

		const serializeSingle = () => {
			if (!state.single) return "";
			const datePart = ISO(state.single);
			if (!withTime) return datePart;
			const timePart = isValidTime(state.time) ? state.time : "00:00";
			return `${datePart}T${timePart}`;
		};

		const writeValues = () => {
			if (mode === "single") {
				if (valueInput) {
					valueInput.value = serializeSingle();
					valueInput.dispatchEvent(new Event("change", { bubbles: true }));
				}
			} else {
				if (startInput) {
					startInput.value = state.start ? ISO(state.start) : "";
					startInput.dispatchEvent(new Event("change", { bubbles: true }));
				}
				if (endInput) {
					endInput.value = state.end ? ISO(state.end) : "";
					endInput.dispatchEvent(new Event("change", { bubbles: true }));
				}
			}
			root.dispatchEvent(
				new CustomEvent("datepicker:change", {
					bubbles: true,
					detail:
						mode === "single"
							? { value: state.single ? serializeSingle() : null }
							: {
									value: {
										start: state.start ? ISO(state.start) : null,
										end: state.end ? ISO(state.end) : null,
									},
							  },
				})
			);
		};

		const renderGrid = () => {
			const year = state.cursor.getFullYear();
			const month = state.cursor.getMonth();
			titleEl.textContent = formatTitle(state.cursor, locale);

			const firstOfMonth = new Date(year, month, 1);
			const startOffset = firstOfMonth.getDay();
			const gridStart = new Date(year, month, 1 - startOffset);
			const today = stripTime(new Date());

			const cells = [];
			for (let i = 0; i < 42; i++) {
				const d = new Date(
					gridStart.getFullYear(),
					gridStart.getMonth(),
					gridStart.getDate() + i
				);
				const iso = ISO(d);
				const isOutside = d.getMonth() !== month;
				const disabled = isDisabled(d);
				const isToday = sameDay(d, today);

				let selected = false;
				let rangeStart = false;
				let rangeEnd = false;
				let inRange = false;
				let preview = false;

				if (mode === "single") {
					selected = sameDay(d, state.single);
				} else {
					rangeStart = sameDay(d, state.start);
					rangeEnd = sameDay(d, state.end);
					if (state.start && state.end) {
						const ds = stripTime(d);
						const a = stripTime(state.start);
						const b = stripTime(state.end);
						inRange = ds > a && ds < b;
					} else if (state.pendingRangeStart && state.hover) {
						const ds = stripTime(d);
						const a = stripTime(state.pendingRangeStart);
						const b = stripTime(state.hover);
						const lo = a < b ? a : b;
						const hi = a < b ? b : a;
						preview = ds >= lo && ds <= hi && !sameDay(d, state.pendingRangeStart);
					}
				}

				const classes = ["datepicker-cell"];
				if (isOutside) classes.push("is-outside");
				if (disabled) classes.push("is-disabled");
				if (isToday) classes.push("is-today");
				if (selected || rangeStart || rangeEnd) classes.push("is-selected");
				if (rangeStart) classes.push("is-range-start");
				if (rangeEnd) classes.push("is-range-end");
				if (inRange) classes.push("is-in-range");
				if (preview) classes.push("is-preview");

				cells.push(
					`<button type="button" role="gridcell" class="${classes.join(" ")}"` +
						` data-date="${iso}"` +
						` tabindex="${disabled ? -1 : -1}"` +
						(disabled ? ' disabled aria-disabled="true"' : "") +
						(isToday ? ' aria-current="date"' : "") +
						(selected || rangeStart || rangeEnd ? ' aria-selected="true"' : "") +
						`>${d.getDate()}</button>`
				);
			}
			gridEl.innerHTML = cells.join("");
		};

		const setSingle = (d) => {
			state.single = new Date(d);
			if (withTime && !isValidTime(state.time)) {
				state.time = currentTime();
				if (timeInput) timeInput.value = state.time;
			}
			writeValues();
			updateLabel();
			renderGrid();
			if (!withTime) close();
		};

		const setRangeBoundary = (d) => {
			if (!state.pendingRangeStart) {
				state.pendingRangeStart = new Date(d);
				state.start = new Date(d);
				state.end = null;
				state.hover = null;
				renderGrid();
				return;
			}
			const a = stripTime(state.pendingRangeStart);
			const b = stripTime(d);
			if (b < a) {
				state.start = new Date(d);
				state.end = new Date(state.pendingRangeStart);
			} else {
				state.start = new Date(state.pendingRangeStart);
				state.end = new Date(d);
			}
			state.pendingRangeStart = null;
			state.hover = null;
			writeValues();
			updateLabel();
			renderGrid();
			close();
		};

		const open = () => {
			if (trigger.getAttribute("aria-expanded") === "true") return;
			document.dispatchEvent(
				new CustomEvent("basecoat:popover", { detail: { source: root } })
			);
			trigger.setAttribute("aria-expanded", "true");
			popover.hidden = false;
			renderGrid();
		};

		const close = (focusTrigger = false) => {
			if (trigger.getAttribute("aria-expanded") !== "true") return;
			trigger.setAttribute("aria-expanded", "false");
			popover.hidden = true;
			state.pendingRangeStart = null;
			state.hover = null;
			if (focusTrigger) trigger.focus();
		};

		trigger.addEventListener("click", (e) => {
			e.stopPropagation();
			if (trigger.getAttribute("aria-expanded") === "true") {
				close(true);
			} else {
				open();
			}
		});

		prevBtn?.addEventListener("click", () => {
			state.cursor = new Date(state.cursor.getFullYear(), state.cursor.getMonth() - 1, 1);
			renderGrid();
		});
		nextBtn?.addEventListener("click", () => {
			state.cursor = new Date(state.cursor.getFullYear(), state.cursor.getMonth() + 1, 1);
			renderGrid();
		});

		clearBtn?.addEventListener("click", () => {
			state.single = null;
			state.start = null;
			state.end = null;
			state.time = "";
			state.pendingRangeStart = null;
			state.hover = null;
			if (timeInput) timeInput.value = "";
			writeValues();
			updateLabel();
			renderGrid();
		});

		todayBtn?.addEventListener("click", () => {
			const today = new Date();
			if (isDisabled(today)) return;
			state.cursor = new Date(today.getFullYear(), today.getMonth(), 1);
			if (mode === "single") {
				if (withTime) {
					state.time = currentTime();
					if (timeInput) timeInput.value = state.time;
				}
				setSingle(today);
			} else {
				setRangeBoundary(today);
			}
		});

		timeInput?.addEventListener("input", () => {
			const next = String(timeInput.value || "");
			state.time = isValidTime(next) ? next : "";
			if (state.single) {
				writeValues();
				updateLabel();
			}
		});

		confirmBtn?.addEventListener("click", () => {
			if (state.single && (!withTime || isValidTime(state.time))) {
				close(true);
			}
		});

		gridEl.addEventListener("click", (e) => {
			const cell = e.target.closest("[data-date]");
			if (!cell || cell.disabled) return;
			const d = parseISO(cell.dataset.date);
			if (!d) return;
			if (mode === "single") setSingle(d);
			else setRangeBoundary(d);
		});

		gridEl.addEventListener("mouseover", (e) => {
			if (mode !== "range" || !state.pendingRangeStart) return;
			const cell = e.target.closest("[data-date]");
			if (!cell || cell.disabled) return;
			const d = parseISO(cell.dataset.date);
			if (!d || sameDay(d, state.hover)) return;
			state.hover = d;
			renderGrid();
		});

		popover.addEventListener("keydown", (e) => {
			if (e.key === "Escape") {
				e.preventDefault();
				close(true);
				return;
			}
			const focused = document.activeElement;
			if (!focused || !gridEl.contains(focused)) return;
			const current = parseISO(focused.dataset.date);
			if (!current) return;
			let target = null;
			if (e.key === "ArrowLeft")
				target = new Date(
					current.getFullYear(),
					current.getMonth(),
					current.getDate() - 1
				);
			else if (e.key === "ArrowRight")
				target = new Date(
					current.getFullYear(),
					current.getMonth(),
					current.getDate() + 1
				);
			else if (e.key === "ArrowUp")
				target = new Date(
					current.getFullYear(),
					current.getMonth(),
					current.getDate() - 7
				);
			else if (e.key === "ArrowDown")
				target = new Date(
					current.getFullYear(),
					current.getMonth(),
					current.getDate() + 7
				);
			else if (e.key === "PageUp")
				target = new Date(
					current.getFullYear(),
					current.getMonth() - 1,
					current.getDate()
				);
			else if (e.key === "PageDown")
				target = new Date(
					current.getFullYear(),
					current.getMonth() + 1,
					current.getDate()
				);
			else if (e.key === "Home")
				target = new Date(
					current.getFullYear(),
					current.getMonth(),
					current.getDate() - current.getDay()
				);
			else if (e.key === "End")
				target = new Date(
					current.getFullYear(),
					current.getMonth(),
					current.getDate() + (6 - current.getDay())
				);
			else if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				if (mode === "single") setSingle(current);
				else setRangeBoundary(current);
				return;
			} else {
				return;
			}
			e.preventDefault();
			if (
				target.getMonth() !== state.cursor.getMonth() ||
				target.getFullYear() !== state.cursor.getFullYear()
			) {
				state.cursor = new Date(target.getFullYear(), target.getMonth(), 1);
			}
			renderGrid();
			const next = gridEl.querySelector(`[data-date="${ISO(target)}"]`);
			if (next && !next.disabled) {
				next.setAttribute("tabindex", "0");
				next.focus();
			}
		});

		document.addEventListener("click", (e) => {
			if (!root.contains(e.target)) close();
		});

		document.addEventListener("basecoat:popover", (e) => {
			if (e.detail?.source !== root) close();
		});

		Object.defineProperty(root, "value", {
			configurable: true,
			get() {
				if (mode === "single") return state.single ? serializeSingle() : null;
				return {
					start: state.start ? ISO(state.start) : null,
					end: state.end ? ISO(state.end) : null,
				};
			},
			set(next) {
				if (mode === "single") {
					if (typeof next === "string" && next) {
						state.single = parseISO(next);
						if (withTime) {
							const t = parseTimeFromISO(next);
							state.time = t || "";
							if (timeInput) timeInput.value = state.time;
						}
					} else {
						state.single = null;
						if (withTime) {
							state.time = "";
							if (timeInput) timeInput.value = "";
						}
					}
				} else if (next && typeof next === "object") {
					state.start = next.start ? parseISO(next.start) : null;
					state.end = next.end ? parseISO(next.end) : null;
					state.pendingRangeStart = null;
				} else {
					state.start = null;
					state.end = null;
				}
				writeValues();
				updateLabel();
				renderGrid();
			},
		});

		root.open = open;
		root.close = close;

		updateLabel();
		renderGrid();

		root.dataset.datepickerInitialized = "true";
		root.dispatchEvent(new CustomEvent("basecoat:initialized"));
	};

	if (window.basecoat) {
		window.basecoat.register(
			"datepicker",
			".datepicker:not([data-datepicker-initialized])",
			initDatepicker
		);
	}
})();
