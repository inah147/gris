(() => {
	const collator = new Intl.Collator("pt-BR", { numeric: true, sensitivity: "base" });

	const parseNumberPtBr = (raw) => {
		if (raw == null) return null;
		const str = String(raw).trim();
		if (!str) return null;
		const cleaned = str.replace(/\s+/g, "").replace(/\./g, "").replace(",", ".");
		if (!/^-?\d+(\.\d+)?$/.test(cleaned)) return null;
		const n = Number(cleaned);
		return Number.isFinite(n) ? n : null;
	};

	const parseDate = (raw) => {
		if (raw == null) return null;
		const str = String(raw).trim();
		if (!str) return null;
		const iso = /^(\d{4})-(\d{2})-(\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2})?)?$/.exec(str);
		if (iso) {
			const t = Date.UTC(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
			return Number.isNaN(t) ? null : t;
		}
		const br = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(str);
		if (br) {
			const t = Date.UTC(Number(br[3]), Number(br[2]) - 1, Number(br[1]));
			return Number.isNaN(t) ? null : t;
		}
		return null;
	};

	const detectColumnType = (rows, columnIndex) => {
		let numericMatches = 0;
		let dateMatches = 0;
		let nonEmpty = 0;
		for (const row of rows) {
			const cell = row.children[columnIndex];
			if (!cell) continue;
			const value = (cell.dataset.sortValue ?? cell.textContent ?? "").trim();
			if (!value) continue;
			nonEmpty += 1;
			if (parseDate(value) != null) dateMatches += 1;
			else if (parseNumberPtBr(value) != null) numericMatches += 1;
		}
		if (nonEmpty === 0) return "text";
		if (dateMatches / nonEmpty >= 0.6) return "date";
		if (numericMatches / nonEmpty >= 0.6) return "number";
		return "text";
	};

	const cellValue = (row, columnIndex) => {
		const cell = row.children[columnIndex];
		if (!cell) return "";
		return (cell.dataset.sortValue ?? cell.textContent ?? "").trim();
	};

	const compareFor = (type) => {
		if (type === "number") {
			return (a, b) => {
				const na = parseNumberPtBr(a);
				const nb = parseNumberPtBr(b);
				if (na == null && nb == null) return 0;
				if (na == null) return 1;
				if (nb == null) return -1;
				return na - nb;
			};
		}
		if (type === "date") {
			return (a, b) => {
				const da = parseDate(a);
				const db = parseDate(b);
				if (da == null && db == null) return 0;
				if (da == null) return 1;
				if (db == null) return -1;
				return da - db;
			};
		}
		return (a, b) => collator.compare(a, b);
	};

	const setIcon = (th, direction) => {
		const useEl = th.querySelector(".table-sort-icon use");
		if (!useEl) return;
		const symbol =
			direction === "ascending"
				? "chevron-up"
				: direction === "descending"
				? "chevron-down"
				: "chevrons-up-down";
		useEl.setAttribute("href", `/assets/gris/design_system/icons/lucide/sprite.svg#${symbol}`);
	};

	const initTable = (table) => {
		const tbody = table.tBodies[0];
		const headerRow = table.tHead?.rows?.[0];
		if (!tbody || !headerRow) {
			table.dataset.tableSortableInitialized = "true";
			return;
		}

		const headers = Array.from(headerRow.children);
		let originalOrder = null;
		let activeIndex = -1;

		const captureOriginalOrder = () => {
			originalOrder = Array.from(tbody.rows);
		};

		const setHeaderState = (clickedIndex, direction) => {
			headers.forEach((th, idx) => {
				if (!th.hasAttribute("data-sortable")) return;
				if (idx === clickedIndex) {
					th.setAttribute("aria-sort", direction);
					th.classList.toggle("is-asc", direction === "ascending");
					th.classList.toggle("is-desc", direction === "descending");
					setIcon(th, direction);
				} else {
					th.setAttribute("aria-sort", "none");
					th.classList.remove("is-asc", "is-desc");
					setIcon(th, "none");
				}
			});
		};

		const sortBy = (columnIndex) => {
			if (!originalOrder) captureOriginalOrder();
			const th = headers[columnIndex];
			const current = th.getAttribute("aria-sort") || "none";
			const next =
				current === "none" ? "ascending" : current === "ascending" ? "descending" : "none";

			if (next === "none") {
				originalOrder.forEach((row) => tbody.appendChild(row));
				setHeaderState(-1, "none");
				activeIndex = -1;
			} else {
				const type = th.dataset.sortType || detectColumnType(originalOrder, columnIndex);
				const cmp = compareFor(type);
				const rows = Array.from(tbody.rows);
				rows.sort((a, b) => {
					const result = cmp(cellValue(a, columnIndex), cellValue(b, columnIndex));
					return next === "ascending" ? result : -result;
				});
				rows.forEach((row) => tbody.appendChild(row));
				setHeaderState(columnIndex, next);
				activeIndex = columnIndex;
			}

			table.dispatchEvent(
				new CustomEvent("table:sort", {
					bubbles: true,
					detail: { columnIndex: activeIndex, direction: next },
				})
			);
		};

		headers.forEach((th, idx) => {
			if (!th.hasAttribute("data-sortable")) return;
			const trigger = th.querySelector(".table-sort-trigger");
			if (!trigger) return;
			trigger.addEventListener("click", () => sortBy(idx));
		});

		table.dataset.tableSortableInitialized = "true";
		table.dispatchEvent(new CustomEvent("basecoat:initialized"));
	};

	if (window.basecoat) {
		window.basecoat.register(
			"table-sortable",
			"table[data-table-sortable]:not([data-table-sortable-initialized])",
			initTable
		);
	}
})();
