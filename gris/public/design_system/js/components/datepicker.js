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

	const formatMonth = (d, locale) => {
		const txt = new Intl.DateTimeFormat(locale, { month: "long" }).format(d);
		return txt.charAt(0).toUpperCase() + txt.slice(1);
	};

	// Página de anos mostrada quando o usuário abre a seleção de ano.
	const YEARS_PER_PAGE = 12;

	const yearPageStart = (year) =>
		year - (((year % YEARS_PER_PAGE) + YEARS_PER_PAGE) % YEARS_PER_PAGE);

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
		const monthRow = root.querySelector("[data-datepicker-month-row]");
		const yearToggle = root.querySelector("[data-datepicker-year-toggle]");
		const yearLabel = root.querySelector("[data-datepicker-year-label]");
		const yearPrevBtn = root.querySelector("[data-datepicker-year-prev]");
		const yearNextBtn = root.querySelector("[data-datepicker-year-next]");
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
			// "days" | "years": o ano no topo abre a lista de anos, para não obrigar o
			// usuário a navegar mês a mês até o ano desejado.
			view: "days",
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

		// Mês/ano só ficam indisponíveis quando o período inteiro está fora de min/max.
		const spanDisabled = (first, last) => {
			if (minDate && stripTime(last) < stripTime(minDate)) return true;
			if (maxDate && stripTime(first) > stripTime(maxDate)) return true;
			return false;
		};

		const yearDisabled = (year) => spanDisabled(new Date(year, 0, 1), new Date(year, 11, 31));

		const selectedDate = () => (mode === "single" ? state.single : state.start);

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

		const renderDays = () => {
			const year = state.cursor.getFullYear();
			const month = state.cursor.getMonth();
			// O ano fica na linha de cima; aqui sobra só o mês, navegado pelas setas.
			titleEl.textContent = formatMonth(state.cursor, locale);

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

		const renderYears = () => {
			const first = yearPageStart(state.cursor.getFullYear());
			const last = first + YEARS_PER_PAGE - 1;
			const thisYear = new Date().getFullYear();
			const selected = selectedDate();

			if (yearLabel) yearLabel.textContent = `${first} – ${last}`;

			const cells = [];
			for (let year = first; year <= last; year++) {
				const disabled = yearDisabled(year);
				const classes = ["datepicker-cell", "datepicker-cell--wide"];
				if (disabled) classes.push("is-disabled");
				if (year === thisYear) classes.push("is-today");
				if (selected && selected.getFullYear() === year) classes.push("is-selected");
				cells.push(
					`<button type="button" class="${classes.join(" ")}" data-year="${year}"` +
						(disabled ? ' disabled aria-disabled="true"' : "") +
						`>${year}</button>`
				);
			}
			gridEl.innerHTML = cells.join("");
		};

		const renderGrid = () => {
			const isDaysView = state.view === "days";

			if (weekdaysEl) weekdaysEl.hidden = !isDaysView;
			if (monthRow) monthRow.hidden = !isDaysView;
			// As setas do ano andam de ano em ano no calendário e de página em página
			// quando a lista de anos está aberta.
			yearPrevBtn?.setAttribute(
				"aria-label",
				isDaysView ? "Ano anterior" : "Anos anteriores"
			);
			yearNextBtn?.setAttribute("aria-label", isDaysView ? "Próximo ano" : "Próximos anos");
			yearToggle?.setAttribute("aria-expanded", isDaysView ? "false" : "true");
			gridEl.classList.toggle("datepicker-popover__grid--compact", !isDaysView);

			if (isDaysView && yearLabel) {
				yearLabel.textContent = String(state.cursor.getFullYear());
			}

			return isDaysView ? renderDays() : renderYears();
		};

		const setView = (view) => {
			state.view = view;
			renderGrid();
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
			state.view = "days";
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

		const stepMonth = (direction) => {
			state.cursor = new Date(
				state.cursor.getFullYear(),
				state.cursor.getMonth() + direction,
				1
			);
			renderGrid();
		};

		const stepYear = (direction) => {
			const salto = state.view === "years" ? YEARS_PER_PAGE : 1;
			state.cursor = new Date(
				state.cursor.getFullYear() + direction * salto,
				state.cursor.getMonth(),
				1
			);
			renderGrid();
		};

		prevBtn?.addEventListener("click", () => stepMonth(-1));
		nextBtn?.addEventListener("click", () => stepMonth(1));

		yearPrevBtn?.addEventListener("click", () => stepYear(-1));
		yearNextBtn?.addEventListener("click", () => stepYear(1));

		yearToggle?.addEventListener("click", () => {
			setView(state.view === "days" ? "years" : "days");
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
			state.view = "days";
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
			// Escolher o ano só troca o ano do calendário: o popover continua aberto,
			// no mesmo mês, para o usuário seguir escolhendo o dia.
			const yearCell = e.target.closest("[data-year]");
			if (yearCell) {
				if (yearCell.disabled) return;
				state.cursor = new Date(Number(yearCell.dataset.year), state.cursor.getMonth(), 1);
				setView("days");
				return;
			}

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
			if (state.view !== "days") return;
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
			// `root.contains(e.target)` não serve sozinho: quando o clique é numa célula do
			// calendário, o re-render troca o innerHTML e o alvo já saiu do DOM antes de o
			// evento chegar aqui — o popover fechava no meio da navegação. O caminho do
			// evento é capturado no dispatch e continua apontando para o componente.
			const path = typeof e.composedPath === "function" ? e.composedPath() : [];
			if (path.includes(root) || root.contains(e.target)) return;
			close();
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
