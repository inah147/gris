frappe.ready(function () {
	const form = document.getElementById("registro-form");
	if (!form) return;

	const submitButton = document.getElementById("btn-submit-registro");
	const tipoDialog = document.getElementById("modalTipoRegistro");
	const confirmationDialog = document.getElementById("confirmationDialog");
	const selectedTipoInput = document.getElementById("selected-tipo-registro");
	const confirmTipoButton = document.getElementById("btn-confirm-tipo-registro");
	const confirmSaveButton = document.getElementById("btn-confirm-save");
	const confirmationSummary = document.getElementById("confirmation-summary");
	const confirmDataCheck = document.getElementById("confirm-data-check");
	const confirmImageCheck = document.getElementById("confirm-image-check");
	const addResponsavelContainer = document.getElementById("add-responsavel-container");
	const unicoResponsavelDialog = document.getElementById("unicoResponsavelDialog");
	const errorDialog = document.getElementById("erroDialog");
	const errorDialogTitle = document.getElementById("erroDialog-title");
	const errorDialogMessage = document.getElementById("erro-dialog-message");
	const novoAssociadoName = document.getElementById("novo-associado-name")?.value || "";
	const readOnly = form.dataset.readOnly === "true";

	const mainMandatoryFields = [
		"nome_completo",
		"data_de_nascimento",
		"etnia",
		"sexo",
		"pais_nascimento",
		"uf_de_nascimento",
		"cidade_de_nascimento",
		"rg",
		"orgao_expedidor",
		"cpf",
		"estado_civil",
		"religiao",
		"escolaridade",
		"cep",
		"endereco",
		"numero",
		"bairro",
		"estado",
		"cidade",
		"email",
		"celular",
		"email_cobranca",
		"telefone_cobranca",
	];

	const mainDataFields = [
		"nome_completo",
		"data_de_nascimento",
		"etnia",
		"sexo",
		"pais_nascimento",
		"uf_de_nascimento",
		"cidade_de_nascimento",
		"rg",
		"orgao_expedidor",
		"cpf",
		"estado_civil",
		"religiao",
		"escolaridade",
		"profissao",
		"local_de_trabalho",
		"cep",
		"endereco",
		"numero",
		"complemento",
		"estado",
		"cidade",
		"bairro",
		"email",
		"celular",
		"telefone_secundario",
		"email_cobranca",
		"telefone_cobranca",
	];

	const responsavelMandatoryFields = [
		"nome_completo",
		"cpf",
		"rg",
		"orgao_expedidor",
		"data_de_nascimento",
		"sexo",
		"estado_civil",
		"escolaridade",
		"profissao",
		"local_de_trabalho",
		"cep",
		"endereco",
		"numero",
		"bairro",
		"cidade",
		"estado",
		"email",
		"celular",
	];

	const addressFields = [
		"cep",
		"endereco",
		"numero",
		"complemento",
		"bairro",
		"cidade",
		"estado",
	];
	let pendingSave = null;
	let movingToConfirmation = false;
	let saving = false;

	const labelMap = {
		tipo_de_registro: "Tipo de registro",
		nome_completo: "Nome completo",
		data_de_nascimento: "Data de nascimento",
		pais_nascimento: "País de nascimento",
		uf_de_nascimento: "UF de nascimento",
		cidade_de_nascimento: "Cidade de nascimento",
		orgao_expedidor: "Órgão expedidor",
		estado_civil: "Estado civil",
		telefone_secundario: "Telefone secundário",
		guarda_unilateral: "Guarda unilateral",
		local_de_trabalho: "Local de trabalho",
		é_guardiao_legal: "É guardião legal",
		cpf: "CPF",
		rg: "RG",
		cep: "CEP",
		uf: "UF",
		email: "Email",
		celular: "Celular",
		email_cobranca: "Email de cobrança",
		telefone_cobranca: "Telefone de cobrança",
		endereco: "Endereço",
		numero: "Número",
		complemento: "Complemento",
		bairro: "Bairro",
		cidade: "Cidade",
		estado: "Estado",
		etnia: "Etnia",
		sexo: "Sexo",
		religiao: "Religião",
		escolaridade: "Escolaridade",
		profissao: "Profissão",
		estrangeiro: "Estrangeiro",
	};

	function escapeHtml(value) {
		const div = document.createElement("div");
		div.textContent = value == null ? "" : String(value);
		return div.innerHTML;
	}

	function showToast(category, title, description) {
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
	}

	function openDialog(dialog) {
		if (!dialog) return;
		if (typeof dialog.showModal === "function") {
			dialog.showModal();
		} else {
			dialog.setAttribute("open", "open");
		}
	}

	function closeDialog(dialog) {
		if (!dialog) return;
		if (typeof dialog.close === "function") {
			dialog.close();
		} else {
			dialog.removeAttribute("open");
		}
	}

	function setLoading(button, loading, label) {
		if (!button) return;
		if (!button.dataset.originalHtml) {
			button.dataset.originalHtml = button.innerHTML;
		}
		button.disabled = loading;
		button.setAttribute("aria-busy", loading ? "true" : "false");
		button.innerHTML = loading
			? escapeHtml(label || "Carregando...")
			: button.dataset.originalHtml;
	}

	function reloadSoon() {
		window.setTimeout(() => window.location.reload(), 1200);
	}

	const ERRO_GENERICO =
		"Não foi possível concluir a ação. Verifique sua conexão e tente novamente.";

	// As mensagens do servidor chegam como JSON aninhado em _server_messages e podem trazer
	// marcação HTML; aqui viram texto puro para entrar no diálogo com segurança.
	function serverMessages(response) {
		const raw = response && response._server_messages;
		if (!raw) return [];
		try {
			return JSON.parse(raw)
				.map((item) => {
					try {
						return JSON.parse(item).message || "";
					} catch (e) {
						return item;
					}
				})
				.map((message) =>
					String(message || "")
						.replace(/<[^>]*>/g, " ")
						.replace(/\s+/g, " ")
						.trim()
				)
				.filter(Boolean);
		} catch (e) {
			return [];
		}
	}

	function showErrorDialog(message, title) {
		const text = message || ERRO_GENERICO;

		if (!errorDialog || !errorDialogMessage) {
			showToast("error", title || "Não foi possível continuar", text);
			return;
		}

		if (errorDialogTitle) {
			errorDialogTitle.textContent = title || "Não foi possível continuar";
		}
		errorDialogMessage.textContent = text;
		openDialog(errorDialog);
	}

	function showServerError(response, title) {
		showErrorDialog(serverMessages(response)[0], title);
	}

	function allFieldControls(scope) {
		return Array.from(scope.querySelectorAll("[data-fieldname]"));
	}

	function findFieldControl(scope, fieldName, fieldScope) {
		return (
			allFieldControls(scope).find((control) => {
				return (
					control.dataset.fieldname === fieldName &&
					(!fieldScope || control.dataset.fieldScope === fieldScope)
				);
			}) || null
		);
	}

	function getMainControl(fieldName) {
		return findFieldControl(form, fieldName, "main");
	}

	function getResponsavelControl(card, fieldName) {
		return findFieldControl(card, fieldName, "responsavel");
	}

	function getHiddenValue(control, selector) {
		return control.querySelector(selector)?.value || "";
	}

	function getControlValue(control) {
		if (!control) return "";
		if (control.type === "checkbox") return control.checked ? 1 : 0;
		if (control.classList.contains("select")) {
			return "value" in control
				? control.value || ""
				: getHiddenValue(control, ":scope > input[type='hidden']");
		}
		if (control.classList.contains("datepicker")) {
			return "value" in control
				? control.value || ""
				: getHiddenValue(control, "[data-datepicker-value]");
		}
		if (control.classList.contains("phone-input")) {
			return "value" in control
				? control.value || ""
				: getHiddenValue(control, "[data-phone-input-value]");
		}
		return control.value || "";
	}

	function setControlValue(control, value) {
		if (!control) return;
		const nextValue = value || "";
		if (control.type === "checkbox") {
			control.checked = Boolean(value);
			control.dispatchEvent(new Event("change", { bubbles: true }));
			return;
		}
		if (
			control.classList.contains("select") ||
			control.classList.contains("datepicker") ||
			control.classList.contains("phone-input")
		) {
			if ("value" in control) {
				control.value = nextValue;
			} else if (control.classList.contains("select")) {
				const hidden = control.querySelector(":scope > input[type='hidden']");
				if (hidden) hidden.value = nextValue;
			} else if (control.classList.contains("datepicker")) {
				const hidden = control.querySelector("[data-datepicker-value]");
				if (hidden) hidden.value = nextValue;
			} else {
				const hidden = control.querySelector("[data-phone-input-value]");
				if (hidden) hidden.value = nextValue;
			}
			control.dispatchEvent(new Event("change", { bubbles: true }));
			return;
		}
		control.value = nextValue;
		control.dispatchEvent(new Event("input", { bubbles: true }));
	}

	function getFocusable(control) {
		if (!control) return null;
		if (control.classList.contains("select")) return control.querySelector(":scope > button");
		if (control.classList.contains("datepicker"))
			return control.querySelector(".datepicker-trigger");
		if (control.classList.contains("phone-input"))
			return control.querySelector("[data-phone-input-number]");
		return typeof control.focus === "function" ? control : null;
	}

	function setInvalid(control, message) {
		if (!control) return;
		control.setAttribute("aria-invalid", "true");
		if (control.classList.contains("select")) {
			control.querySelector(":scope > button")?.setAttribute("aria-invalid", "true");
		}
		if (control.classList.contains("datepicker")) {
			control.querySelector(".datepicker-trigger")?.setAttribute("aria-invalid", "true");
		}
		if (control.classList.contains("phone-input")) {
			control
				.querySelector("[data-phone-input-number]")
				?.setAttribute("aria-invalid", "true");
		}
		const error = control.closest(".registro-field")?.querySelector("[data-field-error]");
		if (error && message) {
			error.textContent = message;
			error.hidden = false;
		}
	}

	function clearInvalidControl(control) {
		if (!control) return;
		control.removeAttribute("aria-invalid");
		control
			.querySelectorAll("[aria-invalid='true']")
			.forEach((item) => item.removeAttribute("aria-invalid"));
		const error = control.closest(".registro-field")?.querySelector("[data-field-error]");
		if (error) {
			error.textContent = "";
			error.hidden = true;
		}
	}

	function clearValidation() {
		form.querySelectorAll("[aria-invalid='true']").forEach((control) =>
			control.removeAttribute("aria-invalid")
		);
		form.querySelectorAll("[data-field-error]").forEach((error) => {
			error.textContent = "";
			error.hidden = true;
		});
	}

	function focusControl(control) {
		if (!control) return;
		const focusable = getFocusable(control);
		control.scrollIntoView({ behavior: "smooth", block: "center" });
		window.setTimeout(() => focusable?.focus(), 250);
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

	function validateEmail(email) {
		return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email || "");
	}

	function applyCPFMask(input) {
		let value = input.value.replace(/\D/g, "").slice(0, 11);
		if (value.length > 9) {
			value = value.replace(/^(\d{3})(\d{3})(\d{3})(\d{1,2}).*/, "$1.$2.$3-$4");
		} else if (value.length > 6) {
			value = value.replace(/^(\d{3})(\d{3})(\d{1,3}).*/, "$1.$2.$3");
		} else if (value.length > 3) {
			value = value.replace(/^(\d{3})(\d{1,3}).*/, "$1.$2");
		}
		input.value = value;
	}

	function isWrapperHidden(card) {
		return Boolean(card.closest(".responsavel-wrapper")?.hidden);
	}

	function visibleGuardianChecks() {
		return Array.from(
			document.querySelectorAll(".guardiao-legal-check[data-fieldname='é_guardiao_legal']")
		).filter((check) => !check.closest(".responsavel-wrapper")?.hidden);
	}

	function toggleGuardiaoLegal() {
		const isUnilateral = getControlValue(getMainControl("guarda_unilateral")) === 1;
		const checks = Array.from(
			document.querySelectorAll(".guardiao-legal-check[data-fieldname='é_guardiao_legal']")
		);
		const visibleChecks = visibleGuardianChecks();

		document.querySelectorAll(".registro-responsavel-vinculo").forEach((section) => {
			section.hidden = !isUnilateral;
		});

		if (isUnilateral) {
			checks.forEach((check) => {
				check.disabled = false;
			});
			const selectedVisible = visibleChecks.filter((check) => check.checked);
			if (selectedVisible.length !== 1) {
				checks.forEach((check) => {
					check.checked = false;
				});
				if (visibleChecks[0]) visibleChecks[0].checked = true;
			}
			return;
		}

		checks.forEach((check) => {
			check.checked = true;
			check.disabled = true;
		});
	}

	function visibleResponsavelCards() {
		return Array.from(document.querySelectorAll(".responsavel-card")).filter(
			(card) => !isWrapperHidden(card)
		);
	}

	function hiddenResponsavelWrapper() {
		return Array.from(document.querySelectorAll(".responsavel-wrapper")).find(
			(wrapper) => wrapper.hidden
		);
	}

	// O botão de adicionar só aparece enquanto houver um card de responsável escondido.
	function syncAddResponsavelButton() {
		if (!addResponsavelContainer) return;
		addResponsavelContainer.hidden = !hiddenResponsavelWrapper();
	}

	function addResponsavel() {
		const wrapper = hiddenResponsavelWrapper();
		if (!wrapper) return;

		wrapper.hidden = false;
		syncAddResponsavelButton();
		toggleGuardiaoLegal();

		const card = wrapper.querySelector(".responsavel-card");
		focusControl(getResponsavelControl(card, "nome_completo"));
	}

	function removeResponsavel(card) {
		const wrapper = card.closest(".responsavel-wrapper");
		if (!wrapper) return;

		wrapper.hidden = true;
		card.dataset.responsavelId = "";

		allFieldControls(card)
			.filter((control) => control.dataset.fieldScope === "responsavel")
			.forEach((control) => {
				setControlValue(control, control.type === "checkbox" ? 0 : "");
				clearInvalidControl(control);
			});

		const sameAddress = card.querySelector(".same-address-check");
		if (sameAddress) {
			sameAddress.checked = false;
			setAddressLocked(card, false);
		}

		const title = card.querySelector(".responsavel-card__title");
		if (title) title.textContent = "Novo Responsável";
		setCpfSearchStatus(card, "");

		syncAddResponsavelButton();
		toggleGuardiaoLegal();
	}

	function syncAddressToCard(card) {
		addressFields.forEach((fieldName) => {
			const source = getMainControl(fieldName);
			const target = getResponsavelControl(card, fieldName);
			setControlValue(target, getControlValue(source));
			clearInvalidControl(target);
		});
	}

	function setControlLocked(control, locked) {
		if (!control) return;
		control.dataset.addressLocked = locked ? "true" : "false";
		if (control.classList.contains("select")) {
			control.querySelector(":scope > button").disabled = locked;
			control.setAttribute("aria-disabled", locked ? "true" : "false");
			return;
		}
		if (control.classList.contains("datepicker")) {
			control.querySelector(".datepicker-trigger").disabled = locked;
			control.setAttribute("aria-disabled", locked ? "true" : "false");
			return;
		}
		if (control.classList.contains("phone-input")) {
			control.querySelector("[data-phone-input-number]").readOnly = locked;
			control.querySelector(".phone-input__country > button").disabled = locked;
			control.setAttribute("aria-disabled", locked ? "true" : "false");
			return;
		}
		if (control.type === "checkbox") {
			control.disabled = locked;
			return;
		}
		control.readOnly = locked;
	}

	function setAddressLocked(card, locked) {
		addressFields.forEach((fieldName) =>
			setControlLocked(getResponsavelControl(card, fieldName), locked)
		);
	}

	function setReadOnlyMode() {
		allFieldControls(form).forEach((control) => {
			if (control.classList.contains("select")) {
				control.querySelector(":scope > button").disabled = true;
				control.querySelector(":scope > input[type='hidden']").disabled = true;
				control.setAttribute("aria-disabled", "true");
				return;
			}
			if (control.classList.contains("datepicker")) {
				control.querySelector(".datepicker-trigger").disabled = true;
				control.querySelectorAll("input[type='hidden']").forEach((input) => {
					input.disabled = true;
				});
				control.setAttribute("aria-disabled", "true");
				return;
			}
			if (control.classList.contains("phone-input")) {
				control.querySelector("[data-phone-input-number]").disabled = true;
				control.querySelector(".phone-input__country > button").disabled = true;
				control.querySelector("[data-phone-input-value]").disabled = true;
				control.setAttribute("aria-disabled", "true");
				return;
			}
			control.disabled = true;
		});
		form.querySelectorAll("button, textarea").forEach((control) => {
			control.disabled = true;
		});
	}

	function collectMainData() {
		const data = {};
		mainDataFields.forEach((fieldName) => {
			data[fieldName] = getControlValue(getMainControl(fieldName));
		});
		data.estrangeiro = getControlValue(getMainControl("estrangeiro"));
		data.guarda_unilateral = getControlValue(getMainControl("guarda_unilateral"));
		return data;
	}

	function collectResponsaveisData() {
		// Card escondido é responsável que não foi adicionado (ou foi removido): enviá-lo
		// vincularia ao jovem alguém que o usuário deixou de fora.
		return visibleResponsavelCards().map((card) => {
			const data = { name: card.dataset.responsavelId || "" };
			allFieldControls(card)
				.filter((control) => control.dataset.fieldScope === "responsavel")
				.forEach((control) => {
					data[control.dataset.fieldname] = getControlValue(control);
				});
			return data;
		});
	}

	function setCpfSearchStatus(card, message, variant) {
		const status = card.querySelector("[data-cpf-search-status]");
		if (!status) return;
		status.textContent = message || "";
		status.hidden = !message;
		status.classList.toggle("registro-field-hint--error", variant === "error");
	}

	function applyResponsavelData(card, dados) {
		Object.keys(dados || {}).forEach((fieldName) => {
			const control = getResponsavelControl(card, fieldName);
			if (!control) return;
			setControlValue(control, dados[fieldName]);
			clearInvalidControl(control);
		});
	}

	function buscarResponsavelPorCpf(button) {
		const card = button.closest(".responsavel-card");
		if (!card) return;

		const cpfControl = getResponsavelControl(card, "cpf");
		const cpf = getControlValue(cpfControl);

		if (!validateCPF(cpf)) {
			setInvalid(cpfControl, "Informe um CPF válido para buscar.");
			focusControl(cpfControl);
			return;
		}

		setCpfSearchStatus(card, "");
		setLoading(button, true, "Buscando...");

		frappe.call({
			method: "gris.www.responsavel.registro.buscar_responsavel_por_cpf",
			args: { novo_associado_name: novoAssociadoName, cpf: cpf },
			// O msgprint do Frappe não funciona neste portal: os erros são mostrados aqui.
			silent: true,
			callback: function (r) {
				setLoading(button, false);

				const resultado = r && r.message;
				if (!resultado) {
					showErrorDialog(ERRO_GENERICO);
					return;
				}

				if (!resultado.encontrado) {
					const bloqueios = {
						cpf_invalido: "Informe um CPF válido para buscar o responsável.",
						cpf_do_jovem:
							"Este é o CPF do próprio jovem. Informe o CPF do responsável.",
						ja_vinculado: `${
							resultado.nome || "Este responsável"
						} já está no formulário deste jovem. Preencha o outro card ou revise os dados já preenchidos.`,
					};

					if (bloqueios[resultado.motivo]) {
						setCpfSearchStatus(card, bloqueios[resultado.motivo], "error");
						showErrorDialog(bloqueios[resultado.motivo]);
						return;
					}

					setCpfSearchStatus(
						card,
						"Nenhum responsável cadastrado com este CPF. Preencha os dados abaixo."
					);
					showToast(
						"info",
						"Responsável não encontrado",
						"Preencha os dados manualmente."
					);
					return;
				}

				applyResponsavelData(card, resultado.dados);
				// É o id que faz o save vincular o cadastro existente em vez de criar outro.
				card.dataset.responsavelId = resultado.name || "";

				const title = card.querySelector(".responsavel-card__title");
				if (title) {
					title.textContent =
						(resultado.dados && resultado.dados.nome_completo) || "Novo Responsável";
				}

				const sameAddress = card.querySelector(".same-address-check");
				if (sameAddress && sameAddress.checked) {
					sameAddress.checked = false;
					setAddressLocked(card, false);
				}

				if (resultado.vazio) {
					setCpfSearchStatus(
						card,
						"Responsável encontrado, mas sem dados salvos. Preencha os campos abaixo."
					);
					showToast(
						"info",
						"Responsável encontrado",
						"O cadastro está sem dados salvos. Preencha os campos."
					);
					return;
				}

				setCpfSearchStatus(
					card,
					"Dados recuperados do cadastro existente. Revise antes de salvar."
				);
				showToast(
					"success",
					"Responsável encontrado",
					"Os dados foram preenchidos. Revise antes de salvar."
				);
			},
			error: function (response) {
				setLoading(button, false);
				showServerError(response, "Não foi possível buscar o responsável");
			},
			always: function () {
				setLoading(button, false);
			},
		});
	}

	function validateForm() {
		clearValidation();
		let valid = true;
		let firstInvalid = null;

		const markInvalid = (control, message) => {
			setInvalid(control, message);
			valid = false;
			if (!firstInvalid) firstInvalid = control;
		};

		mainMandatoryFields.forEach((fieldName) => {
			const control = getMainControl(fieldName);
			if (!String(getControlValue(control) || "").trim()) {
				markInvalid(control, "Campo obrigatório.");
			}
		});

		document.querySelectorAll(".responsavel-card").forEach((card) => {
			if (isWrapperHidden(card)) return;
			responsavelMandatoryFields.forEach((fieldName) => {
				const control = getResponsavelControl(card, fieldName);
				if (!String(getControlValue(control) || "").trim()) {
					markInvalid(control, "Campo obrigatório.");
				}
			});
		});

		const cpfControl = getMainControl("cpf");
		if (getControlValue(cpfControl) && !validateCPF(getControlValue(cpfControl))) {
			markInvalid(cpfControl, "Informe um CPF válido.");
		}

		const emailControl = getMainControl("email");
		if (getControlValue(emailControl) && !validateEmail(getControlValue(emailControl))) {
			markInvalid(emailControl, "Informe um email válido.");
		}

		const billingEmailControl = getMainControl("email_cobranca");
		if (
			getControlValue(billingEmailControl) &&
			!validateEmail(getControlValue(billingEmailControl))
		) {
			markInvalid(billingEmailControl, "Informe um email de cobrança válido.");
		}

		const celularControl = getMainControl("celular");
		if (
			getControlValue(celularControl) &&
			getControlValue(celularControl).replace(/\D/g, "").length < 10
		) {
			markInvalid(celularControl, "Informe um celular válido.");
		}

		const billingPhoneControl = getMainControl("telefone_cobranca");
		if (
			getControlValue(billingPhoneControl) &&
			getControlValue(billingPhoneControl).replace(/\D/g, "").length < 10
		) {
			markInvalid(billingPhoneControl, "Informe um telefone de cobrança válido.");
		}

		document.querySelectorAll(".responsavel-card").forEach((card) => {
			if (isWrapperHidden(card)) return;
			const name =
				card.querySelector(".responsavel-card__title")?.textContent?.trim() ||
				"Responsável";
			const cpf = getResponsavelControl(card, "cpf");
			if (getControlValue(cpf) && !validateCPF(getControlValue(cpf))) {
				markInvalid(cpf, `Informe um CPF válido para ${name}.`);
			}
			const email = getResponsavelControl(card, "email");
			if (getControlValue(email) && !validateEmail(getControlValue(email))) {
				markInvalid(email, `Informe um email válido para ${name}.`);
			}
		});

		const cpfEntries = [];
		const mainCpfRaw = getControlValue(cpfControl);
		if (mainCpfRaw) {
			cpfEntries.push({
				digits: mainCpfRaw.replace(/\D/g, ""),
				label: "Novo Associado",
				control: cpfControl,
			});
		}
		document.querySelectorAll(".responsavel-card").forEach((card) => {
			if (isWrapperHidden(card)) return;
			const control = getResponsavelControl(card, "cpf");
			const value = getControlValue(control);
			if (value) {
				cpfEntries.push({
					digits: value.replace(/\D/g, ""),
					label:
						card.querySelector(".responsavel-card__title")?.textContent?.trim() ||
						"Responsável",
					control,
				});
			}
		});

		const seen = new Map();
		const duplicates = [];
		cpfEntries.forEach((entry) => {
			if (!entry.digits) return;
			if (seen.has(entry.digits)) {
				duplicates.push(entry, seen.get(entry.digits));
			} else {
				seen.set(entry.digits, entry);
			}
		});
		if (duplicates.length) {
			[...new Set(duplicates)].forEach((entry) =>
				markInvalid(entry.control, "CPF duplicado.")
			);
		}

		const isUnilateral = getControlValue(getMainControl("guarda_unilateral")) === 1;
		if (
			isUnilateral &&
			visibleGuardianChecks().filter((check) => check.checked).length !== 1
		) {
			const guardian = visibleGuardianChecks()[0];
			markInvalid(guardian, "Selecione exatamente um guardião legal.");
		}

		if (!valid) {
			showToast(
				"error",
				"Revise os campos",
				"Preencha os campos obrigatórios e corrija os dados destacados."
			);
			focusControl(firstInvalid);
		}
		return valid;
	}

	function formatLabel(key) {
		if (labelMap[key]) return labelMap[key];
		return key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
	}

	function formatValue(value) {
		if (value === 1 || value === "1" || value === true) return "Sim";
		if (value === 0 || value === "0" || value === false) return "Não";
		if (!value) return "-";
		return String(value);
	}

	function renderRows(data, orderedFields) {
		const seen = new Set();
		const rows = [];
		orderedFields.forEach((key) => {
			if (Object.prototype.hasOwnProperty.call(data, key)) {
				seen.add(key);
				rows.push([formatLabel(key), formatValue(data[key])]);
			}
		});
		Object.keys(data).forEach((key) => {
			if (key === "name" || seen.has(key)) return;
			rows.push([formatLabel(key), formatValue(data[key])]);
		});
		return rows
			.map(
				([label, value]) => `
			<tr>
				<th scope="row">${escapeHtml(label)}</th>
				<td>${escapeHtml(value)}</td>
			</tr>
		`
			)
			.join("");
	}

	function renderSummarySection(title, rowsHtml) {
		return `
			<section class="registro-summary-section">
				<h3>${escapeHtml(title)}</h3>
				<div class="registro-table-wrap">
					<table class="table registro-summary-table">
						<tbody>${rowsHtml}</tbody>
					</table>
				</div>
			</section>
		`;
	}

	function showConfirmationModal(payload) {
		pendingSave = payload;
		setLoading(payload.submitButton, false);
		confirmDataCheck.checked = false;
		confirmImageCheck.checked = false;
		confirmSaveButton.disabled = true;

		const mainOrder = [
			"tipo_de_registro",
			"nome_completo",
			"cpf",
			"rg",
			"data_de_nascimento",
			"email",
			"celular",
			"email_cobranca",
			"telefone_cobranca",
			"cep",
			"endereco",
			"numero",
			"complemento",
			"bairro",
			"cidade",
			"estado",
		];
		let html = renderSummarySection("Novo Associado", renderRows(payload.formData, mainOrder));
		payload.responsaveisData.forEach((responsavel, index) => {
			if (!responsavel.nome_completo && !responsavel.cpf) return;
			html += renderSummarySection(
				`Responsável ${index + 1}`,
				renderRows(responsavel, mainOrder)
			);
		});
		confirmationSummary.innerHTML = html;
		openDialog(confirmationDialog);
	}

	function updateConfirmButton() {
		confirmSaveButton.disabled = !(confirmDataCheck.checked && confirmImageCheck.checked);
	}

	function resetTipoSelection() {
		selectedTipoInput.value = "";
		confirmTipoButton.disabled = true;
		document.querySelectorAll(".registro-option-card").forEach((card) => {
			card.setAttribute("aria-selected", "false");
		});
	}

	function selectTipoCard(card) {
		document.querySelectorAll(".registro-option-card").forEach((item) => {
			item.setAttribute("aria-selected", item === card ? "true" : "false");
		});
		selectedTipoInput.value = card.dataset.value || "";
		confirmTipoButton.disabled = !selectedTipoInput.value;
	}

	function openTipoRegistroModal(payload) {
		pendingSave = payload;
		resetTipoSelection();
		openDialog(tipoDialog);
	}

	function resetPendingSubmit() {
		if (!pendingSave || saving) return;
		setLoading(pendingSave.submitButton, false);
	}

	form.addEventListener("input", (event) => {
		const control = event.target.closest("[data-fieldname]");
		if (!control) return;
		clearInvalidControl(control);
		if (event.target.matches("input[data-fieldname='cpf']")) {
			applyCPFMask(event.target);
		}
	});

	form.addEventListener("change", (event) => {
		const control = event.target.closest("[data-fieldname]") || event.target;
		clearInvalidControl(control);
	});

	form.addEventListener("datepicker:change", (event) => clearInvalidControl(event.target));
	form.addEventListener("phone-input:change", (event) => clearInvalidControl(event.target));

	getMainControl("guarda_unilateral")?.addEventListener("change", toggleGuardiaoLegal);

	document.getElementById("btn-add-responsavel")?.addEventListener("click", addResponsavel);

	document.addEventListener("change", (event) => {
		if (event.target.matches(".guardiao-legal-check[data-fieldname='é_guardiao_legal']")) {
			if (
				getControlValue(getMainControl("guarda_unilateral")) === 1 &&
				event.target.checked
			) {
				visibleGuardianChecks().forEach((check) => {
					if (check !== event.target) check.checked = false;
				});
			}
		}
		if (event.target.matches(".same-address-check")) {
			const card = event.target.closest(".responsavel-card");
			if (!card) return;
			if (event.target.checked) syncAddressToCard(card);
			setAddressLocked(card, event.target.checked);
		}
	});

	addressFields.forEach((fieldName) => {
		const control = getMainControl(fieldName);
		if (!control) return;
		const syncCheckedCards = () => {
			document.querySelectorAll(".same-address-check:checked").forEach((checkbox) => {
				const card = checkbox.closest(".responsavel-card");
				if (card) syncAddressToCard(card);
			});
		};
		control.addEventListener("input", syncCheckedCards);
		control.addEventListener("change", syncCheckedCards);
	});

	document.addEventListener("input", (event) => {
		if (
			!event.target.matches(
				"input[data-fieldname='nome_completo'][data-field-scope='responsavel']"
			)
		)
			return;
		const title = event.target
			.closest(".responsavel-card")
			?.querySelector(".responsavel-card__title");
		if (title) title.textContent = event.target.value || "Novo Responsável";
	});

	form.addEventListener("click", (event) => {
		if (readOnly) return;

		const buscar = event.target.closest("[data-buscar-cpf]");
		if (buscar) {
			event.preventDefault();
			buscarResponsavelPorCpf(buscar);
			return;
		}

		const remover = event.target.closest("[data-remover-responsavel]");
		if (remover) {
			event.preventDefault();
			const card = remover.closest(".responsavel-card");
			if (card) removeResponsavel(card);
		}
	});

	document.querySelectorAll("[data-close-dialog]").forEach((button) => {
		button.addEventListener("click", () => {
			const dialog = document.getElementById(button.dataset.closeDialog);
			closeDialog(dialog);
			if (button.dataset.resetSubmit === "true") resetPendingSubmit();
		});
	});

	document.querySelectorAll(".registro-option-card").forEach((card) => {
		card.addEventListener("click", () => selectTipoCard(card));
		card.addEventListener("keydown", (event) => {
			if (event.key !== "Enter" && event.key !== " ") return;
			event.preventDefault();
			selectTipoCard(card);
		});
	});

	confirmDataCheck?.addEventListener("change", updateConfirmButton);
	confirmImageCheck?.addEventListener("change", updateConfirmButton);

	document.getElementById("btn-adicionar-do-dialogo")?.addEventListener("click", () => {
		movingToConfirmation = true;
		closeDialog(unicoResponsavelDialog);
		movingToConfirmation = false;
		resetPendingSubmit();
		addResponsavel();
	});

	document.getElementById("btn-confirmar-unico-responsavel")?.addEventListener("click", () => {
		if (!pendingSave) return;
		movingToConfirmation = true;
		closeDialog(unicoResponsavelDialog);
		openTipoRegistroModal(pendingSave);
		movingToConfirmation = false;
	});

	unicoResponsavelDialog?.addEventListener("close", () => {
		if (!movingToConfirmation) resetPendingSubmit();
	});

	confirmTipoButton?.addEventListener("click", () => {
		if (!pendingSave || !selectedTipoInput.value) return;
		pendingSave.formData.tipo_de_registro = selectedTipoInput.value;
		movingToConfirmation = true;
		closeDialog(tipoDialog);
		showConfirmationModal(pendingSave);
		movingToConfirmation = false;
	});

	confirmSaveButton?.addEventListener("click", () => {
		if (!pendingSave) return;
		saving = true;
		closeDialog(confirmationDialog);
		setLoading(pendingSave.submitButton, true, "Salvando...");

		frappe.call({
			method: "gris.www.responsavel.registro.update_novo_associado",
			args: {
				novo_associado_name: pendingSave.novoAssociadoName,
				data: JSON.stringify(pendingSave.formData),
				responsaveis_data: JSON.stringify(pendingSave.responsaveisData),
			},
			freeze: true,
			freeze_message: "Salvando...",
			// O msgprint do Frappe não funciona neste portal: os erros são mostrados aqui.
			silent: true,
			callback: function (r) {
				if (!r.exc) {
					showToast(
						"success",
						"Dados atualizados",
						"As informações foram salvas com sucesso."
					);
					reloadSoon();
				}
			},
			error: function (response) {
				saving = false;
				setLoading(pendingSave?.submitButton, false);
				// A mensagem do servidor diz o que corrigir (CPF repetido, guardião legal, etc.).
				showServerError(response, "Não foi possível salvar");
			},
			always: function () {
				saving = false;
				setLoading(pendingSave?.submitButton, false);
			},
		});
	});

	tipoDialog?.addEventListener("close", () => {
		if (!movingToConfirmation) resetPendingSubmit();
	});

	confirmationDialog?.addEventListener("close", () => {
		if (!saving) resetPendingSubmit();
	});

	form.addEventListener("submit", (event) => {
		event.preventDefault();
		if (readOnly) return;
		setLoading(submitButton, true, "Validando...");
		if (!validateForm()) {
			setLoading(submitButton, false);
			return;
		}

		const formData = collectMainData();
		const responsaveisData = collectResponsaveisData();
		if (formData.guarda_unilateral !== 1) {
			document
				.querySelectorAll(".guardiao-legal-check[data-fieldname='é_guardiao_legal']")
				.forEach((check) => {
					check.checked = true;
				});
			responsaveisData.forEach((responsavel) => {
				if (responsavel.nome_completo || responsavel.cpf || responsavel.name) {
					responsavel["é_guardiao_legal"] = 1;
				}
			});
		}

		const payload = { novoAssociadoName, formData, responsaveisData, submitButton };

		// Segundo responsável é opcional, mas salvar sem ele merece uma confirmação.
		if (visibleResponsavelCards().length < 2) {
			pendingSave = payload;
			setLoading(submitButton, false);
			openDialog(unicoResponsavelDialog);
			return;
		}

		openTipoRegistroModal(payload);
	});

	syncAddResponsavelButton();
	toggleGuardiaoLegal();
	if (readOnly) setReadOnlyMode();
});
