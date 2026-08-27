(() => {
	// ─── Helpers de formatação (sem float, para não perder centavos) ─────────────

	// Converte uma string de dígitos (interpretada como centavos) no par
	// { display: "R$ 1.234,56", value: "1234.56" }. Vazio quando não há dígitos.
	const fromDigits = (digits) => {
		const clean = String(digits || "")
			.replace(/\D/g, "")
			.replace(/^0+(?=\d)/, "");
		if (!clean) return { display: "", value: "" };
		const padded = clean.padStart(3, "0");
		const cents = padded.slice(-2);
		const intPart = padded.slice(0, -2);
		const intGrouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
		return { display: `R$ ${intGrouped},${cents}`, value: `${intPart}.${cents}` };
	};

	// Converte um número/valor cru (ex.: 1234.56 ou "1234.5") na string de dígitos
	// de centavos ("123456"). Usado na inicialização e no setter público.
	const toDigits = (raw) => {
		if (raw == null || raw === "") return "";
		const num = typeof raw === "number" ? raw : parseFloat(String(raw).replace(",", "."));
		if (isNaN(num)) return "";
		return String(Math.round(num * 100));
	};

	const format = (raw) => fromDigits(toDigits(raw)).display;
	const parse = (raw) => fromDigits(toDigits(raw)).value;

	// Gera a marcação do componente (usada nas tabelas dinâmicas via JS).
	const render = (opts) => {
		opts = opts || {};
		const digits = toDigits(opts.value);
		const numeric = fromDigits(digits).value;
		const display = fromDigits(digits).display;
		const cls = opts.class ? ` ${opts.class}` : "";
		const field = opts.field ? ` data-field="${opts.field}"` : "";
		const name = opts.name ? ` name="${opts.name}"` : "";
		const id = opts.id ? ` id="${opts.id}"` : "";
		let extra = "";
		if (opts.attrs) {
			for (const key in opts.attrs) {
				if (Object.prototype.hasOwnProperty.call(opts.attrs, key)) {
					extra += ` ${key}="${opts.attrs[key]}"`;
				}
			}
		}
		const placeholder = opts.placeholder || "R$ 0,00";
		return (
			`<div class="currency-input" data-currency-input${id}>` +
			`<input type="text" class="input currency-input__display${cls}" data-currency-input-display ` +
			`inputmode="numeric" placeholder="${placeholder}" value="${display}"${extra}>` +
			`<input type="hidden" data-currency-input-value${field}${name} value="${numeric}">` +
			`</div>`
		);
	};

	// ─── Inicialização do componente ─────────────────────────────────────────────

	const initCurrencyInput = (root) => {
		const display = root.querySelector("[data-currency-input-display]");
		const hidden = root.querySelector("[data-currency-input-value]");

		if (!display || !hidden) {
			console.error("Currency-input initialisation failed", root);
			return;
		}

		// Atualiza display visível + valor cru no hidden. Não dispara eventos
		// sintéticos: o input visível é filho do root, então seus eventos nativos
		// `input`/`change` já borbulham até o root, onde o festa.js escuta. Isso
		// preserva a semântica original (ex.: salvar o preço só no `change`/blur).
		const sync = (digits) => {
			const out = fromDigits(digits);
			display.value = out.display;
			hidden.value = out.value;
		};

		// Estado inicial a partir do valor cru já presente no hidden.
		sync(toDigits(hidden.value));

		display.addEventListener("input", () => {
			sync(display.value.replace(/\D/g, "").replace(/^0+(?=\d)/, ""));
			// Mantém o cursor sempre no fim (preenchimento da direita para a esquerda).
			const end = display.value.length;
			try {
				display.setSelectionRange(end, end);
			} catch (e) {
				/* alguns navegadores bloqueiam setSelectionRange em inputs não-texto */
			}
		});

		// ─── API pública no root, drop-in com o JS que usava o <input> direto ──────
		Object.defineProperty(root, "value", {
			configurable: true,
			get() {
				return hidden.value;
			},
			set(next) {
				sync(toDigits(next));
			},
		});

		Object.defineProperty(root, "disabled", {
			configurable: true,
			get() {
				return display.disabled;
			},
			set(next) {
				display.disabled = !!next;
			},
		});

		Object.defineProperty(root, "readOnly", {
			configurable: true,
			get() {
				return display.readOnly;
			},
			set(next) {
				display.readOnly = !!next;
			},
		});

		root.dataset.currencyInputInitialized = "true";
		root.dispatchEvent(new CustomEvent("basecoat:initialized"));
	};

	window.GrisCurrencyInput = { render, format, parse };

	if (window.basecoat) {
		window.basecoat.register(
			"currency-input",
			".currency-input:not([data-currency-input-initialized])",
			initCurrencyInput
		);
	}
})();
