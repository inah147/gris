(function () {
	const form = document.getElementById("nova-festa-form");
	if (!form) return;

	const submitBtn = document.getElementById("nova-festa-submit");
	const tipoCoordSelect = document.getElementById("nova-festa-tipo-coord");
	const pickers = form.querySelectorAll("[data-coord-picker]");

	function showToast(category, message) {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: { config: { category, title: message, duration: 3500 } },
			})
		);
	}

	function getTipoCoord() {
		return new FormData(form).get("tipo_coord_geral") || "Responsavel";
	}

	function updatePickerVisibility() {
		const tipo = getTipoCoord();
		pickers.forEach((node) => {
			node.hidden = node.dataset.coordPicker !== tipo;
		});
	}

	tipoCoordSelect?.addEventListener("change", updatePickerVisibility);
	updatePickerVisibility();

	function parseTimeToMinutes(value) {
		if (!value || !value.includes(":")) return null;
		const [h, m] = value.split(":").map(Number);
		if (!Number.isInteger(h) || !Number.isInteger(m)) return null;
		if (h < 0 || h > 23 || m < 0 || m > 59) return null;
		return h * 60 + m;
	}

	function isEndTimeAfterStart(start, end) {
		const s = parseTimeToMinutes(start);
		const e = parseTimeToMinutes(end);
		if (s === null || e === null) return true;
		return e > s;
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		if (submitBtn.disabled) return;

		const data = new FormData(form);
		const tipoCoord = getTipoCoord();
		const coordenador =
			tipoCoord === "Responsavel"
				? (data.get("coordenador_responsavel") || "").trim()
				: (data.get("coordenador_associado") || "").trim();

		const payload = {
			nome_festa: (data.get("nome_festa") || "").trim(),
			data: (data.get("data") || "").trim(),
			horario_inicio: (data.get("horario_inicio") || "").trim(),
			horario_termino: (data.get("horario_termino") || "").trim(),
			tipo_coord_geral: tipoCoord,
			coordenador,
		};

		if (payload.nome_festa.length < 3) {
			showToast("warning", "Informe um nome com pelo menos 3 caracteres.");
			return;
		}
		if (!payload.data) {
			showToast("warning", "Informe a data da festa.");
			return;
		}
		if (!payload.coordenador) {
			showToast("warning", "Selecione o coordenador.");
			return;
		}
		if (!isEndTimeAfterStart(payload.horario_inicio, payload.horario_termino)) {
			showToast("error", "O horário de término deve ser posterior ao de início.");
			return;
		}

		submitBtn.disabled = true;

		frappe.call({
			method: "gris.www.festas.nova_festa.criar_festa",
			args: { payload: JSON.stringify(payload) },
			freeze: true,
			freeze_message: "Criando festa...",
			callback: function (r) {
				if (r.exc || !r.message) return;
				showToast("success", `Festa "${r.message.name}" criada com sucesso.`);
				window.location.href = r.message.redirect || "/festas/todas_festas";
			},
			always: function () {
				submitBtn.disabled = false;
			},
		});
	});
})();
