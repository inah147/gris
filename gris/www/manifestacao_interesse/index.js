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

	function openDialog(dialog) {
		if (!dialog) return;
		if (typeof dialog.showModal === "function") dialog.showModal();
		else dialog.setAttribute("open", "open");
	}

	function closeDialog(dialog) {
		if (!dialog) return;
		if (typeof dialog.close === "function") dialog.close();
		else dialog.removeAttribute("open");
	}

	function escapeHtml(value) {
		if (value == null) return "";
		return String(value)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
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

	// ===================== Conferência de contato =====================
	//
	// Errar um dígito do celular ou uma letra do e-mail é o engano mais comum deste
	// formulário, e nenhuma validação de formato pega: o dado entra válido e errado, e a
	// recepção fica sem como falar com a família. Só redigitar pega. Ao sair da aba do
	// responsável, os dois campos são pedidos de novo; se o que foi digitado divergir do
	// formulário, as duas versões aparecem e o responsável escolhe a certa.
	//
	// Mesmo desenho da conferência de CPF e data de nascimento em /responsavel/registro.

	const CONFERENCIA_CAMPOS = ["email_responsavel", "celular_responsavel"];
	const CONFERENCIA_ROTULOS = {
		email_responsavel: "E-mail",
		celular_responsavel: "Celular",
	};

	const conferenciaDialog = document.getElementById("conferenciaContatoDialog");
	const conferenciaBotao = document.getElementById("btn-conferencia-contato");

	let conferenciaFase = "digitar";
	let conferenciaDivergencias = [];
	let conferenciaEscolhas = {};
	let conferenciaConcluindo = false;
	let conferenciaConferido = null;

	function digitosTelefone(value) {
		return String(value == null ? "" : value).replace(/\D/g, "");
	}

	function normalizarEmail(value) {
		return String(value == null ? "" : value)
			.trim()
			.toLowerCase();
	}

	function campoDoFormulario(fieldName) {
		if (fieldName === "email_responsavel") return document.getElementById("email_responsavel");
		return document.getElementById("celular_responsavel_input");
	}

	function campoDigitado(fieldName) {
		return conferenciaDialog
			? conferenciaDialog.querySelector('[data-conferencia-campo="' + fieldName + '"]')
			: null;
	}

	// O phone-input expõe o valor completo (+55DDDNÚMERO) no elemento raiz, não no input
	// visível; o e-mail é um input comum.
	function valorDoCampo(fieldName, escopo) {
		if (fieldName === "email_responsavel") {
			const el =
				escopo === "digitado" ? campoDigitado(fieldName) : campoDoFormulario(fieldName);
			return el ? el.value : "";
		}
		if (escopo === "digitado") {
			const raiz = document.getElementById("conferencia_celular_input");
			return raiz ? raiz.value : "";
		}
		const raiz = document.getElementById("celular_responsavel_input");
		return raiz ? raiz.value : "";
	}

	function valoresDeConferencia() {
		return {
			email_responsavel: normalizarEmail(valorDoCampo("email_responsavel", "formulario")),
			celular_responsavel: digitosTelefone(
				valorDoCampo("celular_responsavel", "formulario")
			),
		};
	}

	// Já conferiu e não mexeu em nada desde então: não pede de novo. Voltar para corrigir o
	// e-mail, sim, faz o formulário conferir outra vez.
	function precisaConferir() {
		if (!conferenciaDialog) return false;
		if (!conferenciaConferido) return true;

		const atual = valoresDeConferencia();
		return (
			conferenciaConferido.email_responsavel !== atual.email_responsavel ||
			conferenciaConferido.celular_responsavel !== atual.celular_responsavel
		);
	}

	function marcarConferido() {
		conferenciaConferido = valoresDeConferencia();
	}

	function faseConferencia(fase) {
		return conferenciaDialog
			? conferenciaDialog.querySelector('[data-conferencia-fase="' + fase + '"]')
			: null;
	}

	function limparConferencia() {
		conferenciaFase = "digitar";
		conferenciaDivergencias = [];
		conferenciaEscolhas = {};

		const digitar = faseConferencia("digitar");
		if (digitar) digitar.hidden = false;

		const divergencia = faseConferencia("divergencia");
		if (divergencia) {
			divergencia.hidden = true;
			divergencia.innerHTML = "";
		}

		// Não deixa e-mail nem telefone no DOM depois que a etapa passou.
		CONFERENCIA_CAMPOS.forEach((campo) => {
			const el = campoDigitado(campo);
			if (!el) return;
			el.value = "";
			clearFieldError(el);
		});
		const raiz = document.getElementById("conferencia_celular_input");
		if (raiz) raiz.classList.remove("is-invalid");
	}

	// Valida o que acabou de ser digitado ANTES de comparar: um erro de digitação da própria
	// conferência não pode virar "divergência" e acabar oferecido como opção correta.
	function validarDigitacaoDaConferencia() {
		let valido = true;

		const emailEl = campoDigitado("email_responsavel");
		if (!validateEmail(emailEl ? emailEl.value : "")) {
			setFieldError(emailEl, "Digite um e-mail válido.");
			valido = false;
		}

		const celularEl = campoDigitado("celular_responsavel");
		const raiz = document.getElementById("conferencia_celular_input");
		if (digitosTelefone(raiz ? raiz.value : "").length < 6) {
			if (raiz) raiz.classList.add("is-invalid");
			setFieldError(celularEl, "Digite um número válido com DDD.");
			valido = false;
		} else if (raiz) {
			raiz.classList.remove("is-invalid");
		}

		return valido;
	}

	function saoIguais(fieldName) {
		const formulario = valorDoCampo(fieldName, "formulario");
		const digitado = valorDoCampo(fieldName, "digitado");
		if (fieldName === "email_responsavel") {
			return normalizarEmail(formulario) === normalizarEmail(digitado);
		}
		// Reformatar o telefone não é trocar o telefone.
		return digitosTelefone(formulario) === digitosTelefone(digitado);
	}

	function divergenciasDaConferencia() {
		return CONFERENCIA_CAMPOS.map((fieldName) => {
			if (saoIguais(fieldName)) return null;
			return {
				campo: fieldName,
				formulario: valorDoCampo(fieldName, "formulario"),
				digitado: valorDoCampo(fieldName, "digitado"),
			};
		}).filter(Boolean);
	}

	function formatarValorConferencia(fieldName, value) {
		if (!value) return "Em branco";
		if (fieldName === "email_responsavel") return String(value);
		// Mostra o telefone como o componente o guarda, legível o suficiente para comparar.
		const digitos = digitosTelefone(value);
		const semPais = digitos.startsWith("55") ? digitos.slice(2) : digitos;
		if (semPais.length < 10) return String(value);
		return "(" + semPais.slice(0, 2) + ") " + semPais.slice(2, -4) + "-" + semPais.slice(-4);
	}

	function opcaoDivergenciaHtml(fieldName, origem, rotulo, value) {
		return (
			'<button type="button" class="manifestacao-conferencia__opcao" role="radio"' +
			' aria-checked="false" data-conferencia-opcao="' +
			escapeHtml(fieldName) +
			'" data-conferencia-origem="' +
			escapeHtml(origem) +
			'">' +
			'<span class="manifestacao-conferencia__opcao-rotulo">' +
			escapeHtml(rotulo) +
			"</span>" +
			'<span class="manifestacao-conferencia__opcao-valor">' +
			escapeHtml(formatarValorConferencia(fieldName, value)) +
			"</span>" +
			"</button>"
		);
	}

	function renderDivergencias() {
		const digitar = faseConferencia("digitar");
		if (digitar) digitar.hidden = true;

		const alvo = faseConferencia("divergencia");
		if (!alvo) return;

		alvo.innerHTML =
			'<p class="manifestacao-conferencia__aviso">O que você digitou não confere com o' +
			" formulário. Toque na informação correta.</p>" +
			conferenciaDivergencias
				.map((item) => {
					const rotulo = CONFERENCIA_ROTULOS[item.campo];
					return (
						'<div class="manifestacao-conferencia__campo">' +
						'<p class="manifestacao-conferencia__campo-titulo">' +
						escapeHtml(rotulo) +
						"</p>" +
						'<div class="manifestacao-conferencia__opcoes" role="radiogroup" aria-label="' +
						escapeHtml(rotulo + " correto") +
						'">' +
						opcaoDivergenciaHtml(
							item.campo,
							"formulario",
							"O que está no formulário",
							item.formulario
						) +
						opcaoDivergenciaHtml(
							item.campo,
							"digitado",
							"O que você acabou de digitar",
							item.digitado
						) +
						"</div></div>"
					);
				})
				.join("");
		alvo.hidden = false;
	}

	function atualizarBotaoConferencia() {
		if (!conferenciaBotao) return;

		if (conferenciaFase === "divergencia") {
			conferenciaBotao.textContent = "Confirmar e continuar";
			conferenciaBotao.disabled = conferenciaDivergencias.some(
				(item) => !conferenciaEscolhas[item.campo]
			);
			return;
		}

		conferenciaBotao.textContent = "Confirmar";
		conferenciaBotao.disabled = false;
	}

	// Escrever no controle do formulário é o que faz a correção chegar ao envio: o payload é
	// montado a partir do formulário, depois da conferência.
	function aplicarEscolhasConferencia() {
		conferenciaDivergencias.forEach((item) => {
			if (conferenciaEscolhas[item.campo] !== "digitado") return;

			if (item.campo === "email_responsavel") {
				const el = campoDoFormulario(item.campo);
				if (el) {
					el.value = item.digitado;
					clearFieldError(el);
				}
				return;
			}

			const raiz = document.getElementById("celular_responsavel_input");
			if (raiz) {
				raiz.value = item.digitado;
				raiz.classList.remove("is-invalid");
				clearFieldError(document.getElementById("celular_responsavel"));
			}
		});
	}

	function concluirConferencia() {
		conferenciaConcluindo = true;
		closeDialog(conferenciaDialog);
		conferenciaConcluindo = false;
		limparConferencia();
		marcarConferido();

		// A escolha pode ter trocado o valor do formulário: revalida antes de seguir.
		if (!validateResponsavel()) return;
		showTab("jovem");
	}

	function avancarConferencia() {
		if (conferenciaFase === "divergencia") {
			aplicarEscolhasConferencia();
			concluirConferencia();
			return;
		}

		if (!validarDigitacaoDaConferencia()) return;

		conferenciaDivergencias = divergenciasDaConferencia();
		if (!conferenciaDivergencias.length) {
			concluirConferencia();
			return;
		}

		conferenciaFase = "divergencia";
		conferenciaEscolhas = {};
		renderDivergencias();
		atualizarBotaoConferencia();
	}

	function abrirConferencia() {
		limparConferencia();
		atualizarBotaoConferencia();
		openDialog(conferenciaDialog);
		window.setTimeout(() => {
			const email = campoDigitado("email_responsavel");
			if (email) email.focus();
		}, 100);
	}

	// Os controles da conferência ficam fora do <form>, então não passam pelos ouvintes
	// delegados dele: a limpeza de erro é ligada aqui.
	if (conferenciaDialog) {
		conferenciaDialog.addEventListener("input", function (event) {
			if (!event.target.dataset || !event.target.dataset.conferenciaCampo) return;
			clearFieldError(event.target);
			const raiz = document.getElementById("conferencia_celular_input");
			if (raiz) raiz.classList.remove("is-invalid");
		});

		conferenciaDialog.addEventListener("click", function (event) {
			const opcao = event.target.closest("[data-conferencia-opcao]");
			if (!opcao) return;

			conferenciaEscolhas[opcao.dataset.conferenciaOpcao] = opcao.dataset.conferenciaOrigem;
			opcao
				.closest(".manifestacao-conferencia__opcoes")
				.querySelectorAll("[data-conferencia-opcao]")
				.forEach((item) => {
					item.setAttribute("aria-checked", item === opcao ? "true" : "false");
				});
			atualizarBotaoConferencia();
		});

		// Fechar o diálogo cancela a passagem de aba.
		conferenciaDialog.addEventListener("close", function () {
			if (conferenciaConcluindo) return;
			limparConferencia();
		});

		conferenciaDialog.querySelectorAll("[data-close-dialog]").forEach((botao) => {
			botao.addEventListener("click", function () {
				closeDialog(document.getElementById(botao.dataset.closeDialog));
			});
		});
	}

	if (conferenciaBotao) conferenciaBotao.addEventListener("click", avancarConferencia);

	// ===================== Navigation buttons =====================

	document.querySelectorAll(".btn-next").forEach((btn) =>
		btn.addEventListener("click", function () {
			if (!validateResponsavel()) return;

			if (!precisaConferir()) {
				showTab("jovem");
				return;
			}

			abrirConferencia();
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
