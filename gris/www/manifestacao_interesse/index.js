frappe.ready(function () {
	"use strict";

	// ===================== Helpers =====================

	function setFieldError(input, message) {
		if (!input) return;
		input.classList.add("is-invalid");
		const fieldEl =
			input.closest(".field") || input.closest(".jovem-entry") || input.parentElement;
		if (!fieldEl) return;
		let error = fieldEl.querySelector(":scope > .field__error");
		if (!error) {
			error = document.createElement("p");
			error.className = "field__error";
			fieldEl.appendChild(error);
		}
		error.textContent = message;
	}

	function clearFieldError(input) {
		if (!input) return;
		input.classList.remove("is-invalid");
		const fieldEl =
			input.closest(".field") || input.closest(".jovem-entry") || input.parentElement;
		const error = fieldEl ? fieldEl.querySelector(":scope > .field__error") : null;
		if (error) error.remove();
	}

	function getTabByKey(key) {
		return document.querySelector('[role="tab"][data-tab-key="' + key + '"]');
	}

	function getPanelByTabKey(key) {
		const tab = getTabByKey(key);
		if (!tab) return null;
		const panelId = tab.getAttribute("aria-controls");
		return panelId ? document.getElementById(panelId) : null;
	}

	function showTab(key) {
		const tab = getTabByKey(key);
		if (!tab) return;
		tab.removeAttribute("aria-disabled");
		tab.setAttribute("tabindex", "0");
		tab.click();
	}

	function notifyDesignSystem() {
		document.dispatchEvent(new CustomEvent("gris:design-system:init"));
	}

	// ===================== Validators (puros) =====================

	function validateCPF(cpf) {
		cpf = (cpf || "").replace(/[^\d]+/g, "");
		if (cpf === "") return false;
		if (
			cpf.length !== 11 ||
			cpf === "00000000000" ||
			cpf === "11111111111" ||
			cpf === "22222222222" ||
			cpf === "33333333333" ||
			cpf === "44444444444" ||
			cpf === "55555555555" ||
			cpf === "66666666666" ||
			cpf === "77777777777" ||
			cpf === "88888888888" ||
			cpf === "99999999999"
		) {
			return false;
		}
		let add = 0;
		for (let i = 0; i < 9; i++) add += parseInt(cpf.charAt(i)) * (10 - i);
		let rev = 11 - (add % 11);
		if (rev === 10 || rev === 11) rev = 0;
		if (rev !== parseInt(cpf.charAt(9))) return false;
		add = 0;
		for (let i = 0; i < 10; i++) add += parseInt(cpf.charAt(i)) * (11 - i);
		rev = 11 - (add % 11);
		if (rev === 10 || rev === 11) rev = 0;
		if (rev !== parseInt(cpf.charAt(10))) return false;
		return true;
	}

	function validateEmail(email) {
		return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email || "");
	}

	function validateName(name) {
		return /^[a-zA-ZÀ-ÿ\s]+$/.test(name || "");
	}

	function validateDate(dateString) {
		if (!dateString) return false;
		const date = new Date(dateString);
		const today = new Date();
		today.setHours(0, 0, 0, 0);
		return date instanceof Date && !isNaN(date) && date < today;
	}

	// ===================== Masks =====================

	function maskCPF(input) {
		let value = input.value.replace(/\D/g, "");
		if (value.length > 11) value = value.slice(0, 11);
		if (value.length > 9)
			value = value.replace(/^(\d{3})(\d{3})(\d{3})(\d{1,2}).*/, "$1.$2.$3-$4");
		else if (value.length > 6) value = value.replace(/^(\d{3})(\d{3})(\d{1,3}).*/, "$1.$2.$3");
		else if (value.length > 3) value = value.replace(/^(\d{3})(\d{1,3}).*/, "$1.$2");
		input.value = value;
	}

	function bindCPFMask(scope) {
		(scope || document).querySelectorAll("#cpf_responsavel, .cpf_jovem").forEach((input) => {
			if (input.dataset.cpfMaskBound) return;
			input.addEventListener("input", () => maskCPF(input));
			input.dataset.cpfMaskBound = "true";
		});
	}

	bindCPFMask();

	// Phone-input: o componente cuida da máscara internamente (Brasil = formato BR; demais = dígitos).

	// ===================== Jovens dynamic forms =====================

	function updateJovensForms() {
		const qtdInput = document.getElementById("qtd_jovens");
		const container = document.getElementById("jovens-container");
		const template = document.getElementById("jovem-template");
		let qtd = parseInt(qtdInput.value, 10);
		if (!Number.isFinite(qtd) || qtd < 1) qtd = 1;
		if (qtd > 10) qtd = 10;
		const currentCount = container.children.length;

		if (qtd > currentCount) {
			for (let i = currentCount; i < qtd; i++) {
				const clone = template.content.cloneNode(true);
				const titleEl = clone.querySelector(".jovem-title");
				if (titleEl) titleEl.textContent = "Jovem " + (i + 1);
				container.appendChild(clone);
			}
		} else if (qtd < currentCount) {
			while (container.children.length > qtd) {
				container.removeChild(container.lastElementChild);
			}
		}

		bindCPFMask(container);
		notifyDesignSystem();
	}

	updateJovensForms();
	document.getElementById("qtd_jovens").addEventListener("input", updateJovensForms);
	document.getElementById("qtd_jovens").addEventListener("change", updateJovensForms);

	// ===================== Tab navigation =====================

	function getResponsavelPanel() {
		return getPanelByTabKey("responsavel");
	}
	function getJovemPanel() {
		return getPanelByTabKey("jovem");
	}

	// Block clicks on disabled tabs
	document.getElementById("manifestacao-tabs").addEventListener(
		"click",
		function (event) {
			const tab = event.target.closest('[role="tab"]');
			if (tab && tab.getAttribute("aria-disabled") === "true") {
				event.stopImmediatePropagation();
				event.preventDefault();
			}
		},
		true
	);

	// ===================== Validation per tab =====================

	function validateResponsavel() {
		let isValid = true;
		const panel = getResponsavelPanel();
		if (!panel) return false;
		panel.querySelectorAll(".is-invalid").forEach((el) => clearFieldError(el));

		const nameField = document.getElementById("nome_responsavel");
		if (!validateName(nameField.value)) {
			setFieldError(
				nameField,
				"Por favor, insira um nome válido (somente letras e espaços)."
			);
			isValid = false;
		}

		const emailField = document.getElementById("email_responsavel");
		if (!validateEmail(emailField.value)) {
			setFieldError(emailField, "Por favor, insira um e-mail válido.");
			isValid = false;
		}

		const phoneRoot = document.getElementById("celular_responsavel_input");
		const phoneVisible = document.getElementById("celular_responsavel");
		const phoneFull = phoneRoot ? phoneRoot.value : "";
		// hidden input só recebe valor se houver dígitos no campo de número
		if (!phoneFull || phoneFull.replace(/\D/g, "").length < 6) {
			if (phoneRoot) phoneRoot.classList.add("is-invalid");
			setFieldError(phoneVisible, "Por favor, insira um número válido com DDD.");
			isValid = false;
		} else if (phoneRoot) {
			phoneRoot.classList.remove("is-invalid");
		}

		const cpfField = document.getElementById("cpf_responsavel");
		if (!validateCPF(cpfField.value)) {
			setFieldError(cpfField, "CPF inválido.");
			isValid = false;
		}

		return isValid;
	}

	function getJovemDataNascimentoValue(entry) {
		const dp = entry.querySelector(".data_nascimento_jovem");
		if (!dp) return "";
		// componente expõe `value` via getter; fallback para o hidden input
		if (typeof dp.value === "string") return dp.value;
		const hidden = dp.querySelector("[data-datepicker-value]");
		return hidden ? hidden.value : "";
	}

	function validateJovens() {
		let isValid = true;
		const panel = getJovemPanel();
		if (!panel) return false;
		panel.querySelectorAll(".is-invalid").forEach((el) => clearFieldError(el));
		// remove erros do datepicker também
		panel
			.querySelectorAll(".datepicker.is-invalid")
			.forEach((el) => el.classList.remove("is-invalid"));
		panel.querySelectorAll(".jovem-entry .field__error").forEach((el) => el.remove());

		const entries = panel.querySelectorAll(".jovem-entry");
		entries.forEach((entry) => {
			const nameField = entry.querySelector(".nome_jovem");
			if (!validateName(nameField.value)) {
				setFieldError(
					nameField,
					"Por favor, insira um nome válido (somente letras e espaços)."
				);
				isValid = false;
			}

			const cpfField = entry.querySelector(".cpf_jovem");
			if (!validateCPF(cpfField.value)) {
				setFieldError(cpfField, "CPF inválido.");
				isValid = false;
			}

			const dataValue = getJovemDataNascimentoValue(entry);
			if (!validateDate(dataValue)) {
				const dp = entry.querySelector(".data_nascimento_jovem");
				if (dp) dp.classList.add("is-invalid");
				const fieldEl = dp ? dp.closest(".field") : null;
				if (fieldEl) {
					let error = fieldEl.querySelector(":scope > .field__error");
					if (!error) {
						error = document.createElement("p");
						error.className = "field__error";
						fieldEl.appendChild(error);
					}
					error.textContent = "Por favor, insira uma data válida anterior a hoje.";
				}
				isValid = false;
			}
		});

		return isValid;
	}

	function validateConfirmacao() {
		let isValid = true;
		const checkDados = document.getElementById("check_dados_corretos");
		const checkLgpd = document.getElementById("check_lgpd");
		if (!checkDados.checked) {
			checkDados.classList.add("is-invalid");
			isValid = false;
		}
		if (!checkLgpd.checked) {
			checkLgpd.classList.add("is-invalid");
			isValid = false;
		}
		return isValid;
	}

	// Limpa "is-invalid" de checkboxes ao alterar
	document.getElementById("check_dados_corretos").addEventListener("change", function () {
		this.classList.remove("is-invalid");
	});
	document.getElementById("check_lgpd").addEventListener("change", function () {
		this.classList.remove("is-invalid");
	});

	// ===================== Navigation buttons =====================

	document.querySelectorAll(".btn-next").forEach((btn) =>
		btn.addEventListener("click", function () {
			if (validateResponsavel()) {
				showTab("jovem");
			}
		})
	);

	document.querySelectorAll(".btn-prev").forEach((btn) =>
		btn.addEventListener("click", function () {
			showTab("responsavel");
		})
	);

	document.querySelectorAll(".btn-prev-confirmacao").forEach((btn) =>
		btn.addEventListener("click", function () {
			showTab("jovem");
		})
	);

	function buildSummary() {
		document.getElementById("summary_nome_responsavel").textContent =
			document.getElementById("nome_responsavel").value;
		document.getElementById("summary_email_responsavel").textContent =
			document.getElementById("email_responsavel").value;
		const phoneRoot = document.getElementById("celular_responsavel_input");
		const phoneFull = phoneRoot ? phoneRoot.value : "";
		const phoneVisible = document.getElementById("celular_responsavel").value;
		document.getElementById("summary_celular_responsavel").textContent = phoneFull
			? phoneFull + (phoneVisible ? " (" + phoneVisible + ")" : "")
			: "";
		document.getElementById("summary_cpf_responsavel").textContent =
			document.getElementById("cpf_responsavel").value;

		const summaryContainer = document.getElementById("summary-jovens-container");
		summaryContainer.innerHTML = "";

		document.querySelectorAll(".jovem-entry").forEach((entry, index) => {
			const nome = entry.querySelector(".nome_jovem").value;
			const cpf = entry.querySelector(".cpf_jovem").value;
			const dataNasc = getJovemDataNascimentoValue(entry);

			let dataFormatada = "";
			if (dataNasc) {
				const dateObj = new Date(dataNasc);
				const adjusted = new Date(dateObj.getTime() + dateObj.getTimezoneOffset() * 60000);
				dataFormatada = adjusted.toLocaleDateString("pt-BR");
			}

			const wrapper = document.createElement("div");
			wrapper.className = "manifestacao__summary-jovem";
			wrapper.innerHTML =
				'<h4 class="manifestacao__summary-jovem-title">Jovem ' +
				(index + 1) +
				"</h4>" +
				'<dl class="manifestacao__summary-grid">' +
				"<div><dt>Nome</dt><dd></dd></div>" +
				"<div><dt>CPF</dt><dd></dd></div>" +
				"<div><dt>Data de nascimento</dt><dd></dd></div>" +
				"</dl>";
			const dds = wrapper.querySelectorAll("dd");
			dds[0].textContent = nome;
			dds[1].textContent = cpf;
			dds[2].textContent = dataFormatada;
			summaryContainer.appendChild(wrapper);
		});
	}

	document.querySelectorAll(".btn-next-jovem").forEach((btn) =>
		btn.addEventListener("click", function () {
			if (!validateJovens()) return;

			// CPF duplicate check
			const cpfRespField = document.getElementById("cpf_responsavel");
			const cpfResp = cpfRespField.value;
			const seen = {};
			if (cpfResp) seen[cpfResp] = [cpfRespField];
			document.querySelectorAll(".jovem-entry").forEach((entry) => {
				const f = entry.querySelector(".cpf_jovem");
				if (f && f.value) {
					if (!seen[f.value]) seen[f.value] = [];
					seen[f.value].push(f);
				}
			});

			let hasDuplicates = false;
			Object.keys(seen).forEach((cpf) => {
				if (seen[cpf].length > 1) {
					hasDuplicates = true;
					seen[cpf].forEach((f) =>
						setFieldError(f, "Este CPF está duplicado em outro campo.")
					);
				}
			});

			if (hasDuplicates) {
				frappe.msgprint({
					title: "Erro de validação",
					indicator: "red",
					message:
						"Existem CPFs duplicados (Responsável ou Jovens). Cada pessoa deve ter um CPF único.",
				});
				return;
			}

			buildSummary();
			showTab("confirmacao");
		})
	);

	// ===================== Submit =====================

	const overlay = document.getElementById("loading-overlay");

	function showOverlay() {
		overlay.hidden = false;
		overlay.setAttribute("aria-hidden", "false");
	}

	function hideOverlay() {
		overlay.hidden = true;
		overlay.setAttribute("aria-hidden", "true");
	}

	function showSuccessMessage(message) {
		const form = document.getElementById("interest-form");
		const msg = document.getElementById("form-message");

		form.style.transition = "opacity 250ms ease";
		form.style.opacity = "0";
		setTimeout(() => {
			form.hidden = true;
			form.style.display = "none";
		}, 260);

		msg.innerHTML =
			'<div class="manifestacao__success-icon">' +
			'<svg class="ds-lucide ds-lucide--lg" viewBox="0 0 24 24" aria-hidden="true">' +
			'<use href="/assets/gris/design_system/icons/lucide/sprite.svg#circle-check-big"></use>' +
			"</svg>" +
			"</div>" +
			'<h2 class="manifestacao__success-title">Sucesso!</h2>' +
			'<p class="manifestacao__success-message"></p>';
		msg.querySelector(".manifestacao__success-message").textContent = message;
		msg.hidden = false;

		// Update stepper
		const step1 = document.getElementById("step-1");
		const step2 = document.getElementById("step-2");
		if (step1) {
			step1.classList.remove("is-active");
			step1.classList.add("is-completed");
		}
		if (step2) step2.classList.add("is-active");

		const offset = msg.getBoundingClientRect().top + window.scrollY - 100;
		window.scrollTo({ top: offset, behavior: "smooth" });
	}

	document.getElementById("interest-form").addEventListener("submit", function (event) {
		event.preventDefault();

		if (!validateResponsavel()) {
			showTab("responsavel");
			return;
		}
		if (!validateJovens()) {
			showTab("jovem");
			return;
		}
		if (!validateConfirmacao()) return;

		const data = {
			nome_responsavel: document.getElementById("nome_responsavel").value,
			email_responsavel: document.getElementById("email_responsavel").value,
			cpf_responsavel: document.getElementById("cpf_responsavel").value,
		};

		const phoneRoot = document.getElementById("celular_responsavel_input");
		data.celular_responsavel = phoneRoot ? phoneRoot.value : "";

		const jovens = [];
		document.querySelectorAll(".jovem-entry").forEach((entry) => {
			jovens.push({
				nome_jovem: entry.querySelector(".nome_jovem").value,
				cpf_jovem: entry.querySelector(".cpf_jovem").value,
				data_nascimento_jovem: getJovemDataNascimentoValue(entry),
			});
		});
		data.jovens = JSON.stringify(jovens);

		showOverlay();

		frappe.call({
			method: "gris.www.manifestacao_interesse.index.submit_interest",
			args: data,
			callback: function (r) {
				hideOverlay();
				if (r.message && r.message.status === "success") {
					showSuccessMessage(r.message.message);
				} else {
					frappe.msgprint({
						title: "Erro",
						indicator: "red",
						message: r.message ? r.message.message : "Ocorreu um erro desconhecido.",
					});
				}
			},
			error: function () {
				hideOverlay();
				frappe.msgprint({
					title: "Erro",
					indicator: "red",
					message: "Não foi possível conectar ao servidor. Tente novamente mais tarde.",
				});
			},
		});
	});
});
