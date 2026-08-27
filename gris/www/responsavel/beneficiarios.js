frappe.ready(function () {
	const scheduleDialog = document.getElementById("modalAgendamento");
	const addDialog = document.getElementById("modalAdicionar");
	const cancelDialog = document.getElementById("modalCancelarAgendamento");
	const visitDateSelect = document.getElementById("visit-date-select");
	const btnAgendar = document.getElementById("btn-agendar-visita");
	const btnReagendar = document.getElementById("btn-reagendar-visita");
	const btnCancelar = document.getElementById("btn-cancelar-visita");
	const btnConfirmarAgendamento = document.getElementById("btn-confirmar-agendamento");
	const btnConfirmarCancelamento = document.getElementById("btn-confirmar-cancelamento");
	const btnAdicionar = document.getElementById("btn-adicionar-beneficiario");
	const formAdicionar = document.getElementById("form-adicionar-beneficiario");
	const btnConfirmarAdicionar = document.getElementById("btn-confirmar-adicionar");
	const inputNome = document.getElementById("add_nome_jovem");
	const inputCpf = document.getElementById("add_cpf_jovem");
	const birthDatePicker = document.getElementById("add_data_nascimento_jovem");
	const responsavelCpf = (
		document.getElementById("responsavel-data")?.dataset.cpf || ""
	).replace(/\D/g, "");
	let isReschedule = false;

	const openDialog = (dialog) => {
		if (!dialog) return;
		if (typeof dialog.showModal === "function") {
			dialog.showModal();
		} else {
			dialog.setAttribute("open", "open");
		}
	};

	const closeDialog = (dialog) => {
		if (!dialog) return;
		if (typeof dialog.close === "function") {
			dialog.close();
		} else {
			dialog.removeAttribute("open");
		}
	};

	const escapeHtml = (value) => {
		const div = document.createElement("div");
		div.textContent = value == null ? "" : String(value);
		return div.innerHTML;
	};

	const showToast = (category, title, description) => {
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: {
					config: {
						category,
						title: escapeHtml(title),
						description: escapeHtml(description || ""),
					},
				},
			})
		);
	};

	const setLoading = (button, loading, label) => {
		if (!button) return;
		if (!button.dataset.originalHtml) {
			button.dataset.originalHtml = button.innerHTML;
		}
		button.disabled = loading;
		button.setAttribute("aria-busy", loading ? "true" : "false");
		button.innerHTML = loading ? label : button.dataset.originalHtml;
	};

	const reloadSoon = () => {
		window.setTimeout(() => {
			window.location.reload();
		}, 1100);
	};

	const getVisitDate = () => visitDateSelect?.value || "";

	const updateScheduleButton = () => {
		if (!btnConfirmarAgendamento) return;
		btnConfirmarAgendamento.disabled = !getVisitDate();
	};

	const resetVisitDate = () => {
		if (visitDateSelect && "value" in visitDateSelect) {
			visitDateSelect.value = "";
		}
		updateScheduleButton();
	};

	const openScheduleDialog = (reschedule) => {
		isReschedule = Boolean(reschedule);
		resetVisitDate();
		openDialog(scheduleDialog);
	};

	document.querySelectorAll("[data-close-dialog]").forEach((button) => {
		button.addEventListener("click", () => {
			closeDialog(document.getElementById(button.dataset.closeDialog));
		});
	});

	if (visitDateSelect) {
		visitDateSelect.addEventListener("change", updateScheduleButton);
	}

	if (btnAgendar) {
		btnAgendar.addEventListener("click", () => openScheduleDialog(false));
	}

	if (btnReagendar) {
		btnReagendar.addEventListener("click", () => openScheduleDialog(true));
	}

	if (btnCancelar) {
		btnCancelar.addEventListener("click", () => openDialog(cancelDialog));
	}

	if (btnAdicionar) {
		btnAdicionar.addEventListener("click", () => {
			resetAdicionarForm();
			openDialog(addDialog);
			inputNome?.focus();
		});
	}

	if (btnConfirmarAgendamento) {
		btnConfirmarAgendamento.addEventListener("click", () => {
			const selectedDate = getVisitDate();
			if (!selectedDate) return;
			if (isReschedule) {
				rescheduleVisit(selectedDate);
			} else {
				scheduleVisit(selectedDate);
			}
		});
	}

	if (btnConfirmarCancelamento) {
		btnConfirmarCancelamento.addEventListener("click", cancelVisit);
	}

	if (inputCpf) {
		inputCpf.addEventListener("input", function () {
			let value = this.value.replace(/\D/g, "").slice(0, 11);
			if (value.length > 9) {
				value = value.replace(/^(\d{3})(\d{3})(\d{3})(\d{1,2}).*/, "$1.$2.$3-$4");
			} else if (value.length > 6) {
				value = value.replace(/^(\d{3})(\d{3})(\d{1,3}).*/, "$1.$2.$3");
			} else if (value.length > 3) {
				value = value.replace(/^(\d{3})(\d{1,3}).*/, "$1.$2");
			}
			this.value = value;
		});
	}

	if (formAdicionar) {
		formAdicionar.addEventListener("submit", (event) => {
			event.preventDefault();
			submitAdicionarBeneficiario();
		});
	}

	function resetAdicionarForm() {
		formAdicionar?.reset();
		if (birthDatePicker && "value" in birthDatePicker) {
			birthDatePicker.value = null;
		}
		clearValidation();
	}

	function clearValidation() {
		formAdicionar?.querySelectorAll("[aria-invalid='true']").forEach((element) => {
			element.removeAttribute("aria-invalid");
		});
		formAdicionar
			?.querySelectorAll(".datepicker-trigger[aria-invalid='true']")
			.forEach((element) => {
				element.removeAttribute("aria-invalid");
			});
		formAdicionar?.querySelectorAll("[data-field-error]").forEach((element) => {
			element.textContent = "";
			element.hidden = true;
		});
	}

	function setFieldInvalid(fieldName, control, message) {
		const error = formAdicionar?.querySelector(`[data-field-error="${fieldName}"]`);
		const invalidControl = control?.classList?.contains("datepicker")
			? control.querySelector(".datepicker-trigger")
			: control;

		invalidControl?.setAttribute("aria-invalid", "true");
		if (error) {
			error.textContent = message;
			error.hidden = false;
		}
	}

	function validateCPF(cpf) {
		cpf = (cpf || "").replace(/\D/g, "");
		if (cpf.length !== 11) return false;
		if (/^(\d)\1{10}$/.test(cpf)) return false;

		let sum = 0;
		for (let i = 0; i < 9; i++) sum += parseInt(cpf.charAt(i), 10) * (10 - i);
		let remainder = 11 - (sum % 11);
		if (remainder === 10 || remainder === 11) remainder = 0;
		if (remainder !== parseInt(cpf.charAt(9), 10)) return false;

		sum = 0;
		for (let i = 0; i < 10; i++) sum += parseInt(cpf.charAt(i), 10) * (11 - i);
		remainder = 11 - (sum % 11);
		if (remainder === 10 || remainder === 11) remainder = 0;
		return remainder === parseInt(cpf.charAt(10), 10);
	}

	function validateAdicionarForm() {
		clearValidation();
		let valid = true;
		const nome = (inputNome?.value || "").trim();
		const cpfValue = (inputCpf?.value || "").trim();
		const cpfLimpo = cpfValue.replace(/\D/g, "");
		const dataNascimento =
			birthDatePicker?.value || formAdicionar?.elements.data_nascimento_jovem?.value || "";
		const today = new Date(new Date().toISOString().split("T")[0]);
		const birthDate = dataNascimento ? new Date(dataNascimento) : null;

		if (!nome || !/^[A-Za-zÀ-ÿ\s]+$/.test(nome)) {
			setFieldInvalid(
				"nome_jovem",
				inputNome,
				"Informe um nome válido usando apenas letras e espaços."
			);
			valid = false;
		}

		if (!validateCPF(cpfValue)) {
			setFieldInvalid("cpf_jovem", inputCpf, "Informe um CPF válido.");
			valid = false;
		} else if (responsavelCpf && cpfLimpo === responsavelCpf) {
			setFieldInvalid(
				"cpf_jovem",
				inputCpf,
				"O CPF do jovem não pode ser o mesmo do responsável."
			);
			valid = false;
		}

		if (!birthDate || birthDate >= today) {
			setFieldInvalid(
				"data_nascimento_jovem",
				birthDatePicker,
				"Informe uma data anterior a hoje."
			);
			valid = false;
		}

		return valid;
	}

	function submitAdicionarBeneficiario() {
		if (!formAdicionar || !validateAdicionarForm()) return;

		const formData = new FormData(formAdicionar);
		setLoading(btnConfirmarAdicionar, true, "Adicionando...");

		frappe.call({
			method: "gris.www.responsavel.beneficiarios.adicionar_beneficiario",
			args: {
				nome_jovem: (formData.get("nome_jovem") || "").trim(),
				cpf_jovem: (formData.get("cpf_jovem") || "").trim(),
				data_nascimento_jovem: formData.get("data_nascimento_jovem") || "",
			},
			callback: function (r) {
				if (r.message && r.message.ok) {
					closeDialog(addDialog);
					showToast(
						"success",
						"Beneficiário adicionado",
						r.message.message || "Cadastro iniciado com sucesso."
					);
					reloadSoon();
				}
			},
			error: function () {
				showToast(
					"error",
					"Não foi possível adicionar",
					"Revise os dados e tente novamente."
				);
			},
			always: function () {
				setLoading(btnConfirmarAdicionar, false);
			},
		});
	}

	function scheduleVisit(date) {
		setLoading(btnConfirmarAgendamento, true, "Agendando...");
		frappe.call({
			method: "gris.www.responsavel.beneficiarios.schedule_visit",
			args: { date: date },
			callback: function (r) {
				if (!r.exc) {
					closeDialog(scheduleDialog);
					showToast("success", "Visita agendada", "A visita foi agendada com sucesso.");
					reloadSoon();
				}
			},
			error: function () {
				showToast(
					"error",
					"Não foi possível agendar",
					"A data selecionada pode não estar mais disponível."
				);
			},
			always: function () {
				setLoading(btnConfirmarAgendamento, false);
				updateScheduleButton();
			},
		});
	}

	function rescheduleVisit(date) {
		setLoading(btnConfirmarAgendamento, true, "Reagendando...");
		frappe.call({
			method: "gris.www.responsavel.beneficiarios.reschedule_visit",
			args: { date: date },
			callback: function (r) {
				if (!r.exc) {
					closeDialog(scheduleDialog);
					showToast(
						"success",
						"Visita reagendada",
						"A nova data foi salva com sucesso."
					);
					reloadSoon();
				}
			},
			error: function () {
				showToast(
					"error",
					"Não foi possível reagendar",
					"A data selecionada pode não estar mais disponível."
				);
			},
			always: function () {
				setLoading(btnConfirmarAgendamento, false);
				updateScheduleButton();
			},
		});
	}

	function cancelVisit() {
		setLoading(btnConfirmarCancelamento, true, "Cancelando...");
		frappe.call({
			method: "gris.www.responsavel.beneficiarios.cancel_visit",
			callback: function (r) {
				if (!r.exc) {
					closeDialog(cancelDialog);
					showToast(
						"success",
						"Agendamento cancelado",
						"A visita foi removida da agenda."
					);
					reloadSoon();
				}
			},
			error: function () {
				showToast("error", "Não foi possível cancelar", "Tente novamente em instantes.");
			},
			always: function () {
				setLoading(btnConfirmarCancelamento, false);
			},
		});
	}

	updateScheduleButton();
});
