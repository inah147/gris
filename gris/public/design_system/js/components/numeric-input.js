(() => {
	// Campo numérico simples: aceita apenas dígitos e um único ponto decimal.
	// Vírgula digitada é convertida automaticamente para ponto. Use em inputs
	// `type="text"` com `inputmode="decimal"` e o atributo `data-numeric-input`.
	// Não é um campo de moeda — para valores em R$ use o componente currency-input.

	// Normaliza o texto: vírgula → ponto, remove tudo que não for dígito/ponto e
	// mantém apenas o primeiro ponto.
	const clean = (raw) => {
		let v = String(raw == null ? "" : raw)
			.replace(/,/g, ".")
			.replace(/[^0-9.]/g, "");
		const firstDot = v.indexOf(".");
		if (firstDot !== -1) {
			v = v.slice(0, firstDot + 1) + v.slice(firstDot + 1).replace(/\./g, "");
		}
		return v;
	};

	const sanitize = (input) => {
		const before = input.value;
		const next = clean(before);
		if (next === before) return;
		const caret = input.selectionStart;
		input.value = next;
		// Reposiciona o cursor compensando os caracteres removidos antes dele.
		if (typeof caret === "number") {
			const removed = before.length - next.length;
			const pos = Math.max(0, caret - removed);
			try {
				input.setSelectionRange(pos, pos);
			} catch (e) {
				/* navegadores podem bloquear setSelectionRange em alguns estados */
			}
		}
	};

	const initNumericInput = (input) => {
		input.addEventListener("input", () => sanitize(input));
		input.addEventListener("blur", () => sanitize(input));
		// Estado inicial (valores pré-preenchidos ou colados via markup).
		sanitize(input);
		input.dataset.numericInputInitialized = "true";
	};

	if (window.basecoat) {
		window.basecoat.register(
			"numeric-input",
			"input[data-numeric-input]:not([data-numeric-input-initialized])",
			initNumericInput
		);
	}
})();
