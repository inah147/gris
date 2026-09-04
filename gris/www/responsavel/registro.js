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

	// Ramo Filhotes: a idade de transição vem do Single Vagas, pelo dataset do form.
	const idadeTransicaoFilhotes = Number(form.dataset.idadeTransicaoFilhotes || 0);
	const filhotesAviso = document.querySelector(".registro-filhotes-aviso");
	const filhotesTotal = document.getElementById("filhotes-total");
	const filhotesTotalValor = document.getElementById("filhotes-total-valor");
	const filhotesTotalDetalhe = document.getElementById("filhotes-total-detalhe");
	const filhotesCiencia = document.getElementById("filhotes-ciencia");
	const cienciaPagamentoCheck = document.getElementById("ciencia-pagamento-check");
	const cienciaAcompanhamentoCheck = document.getElementById("ciencia-acompanhamento-check");
	const tipoOptions = document.getElementById("registro-type-options");
	const provisorioCard = document.querySelector(
		'.registro-option-card[data-value="Provisório"]'
	);
	const proximosPassosDialog = document.getElementById("proximosPassosDialog");
	const proximosPassosLista = document.getElementById("proximos-passos-declaracoes");
	const enviarDeclaracaoDialog = document.getElementById("enviarDeclaracaoDialog");
	const conferenciaDialog = document.getElementById("conferenciaDialog");
	const conferenciaProgresso = document.getElementById("conferencia-progresso");
	const conferenciaProximoButton = document.getElementById("btn-conferencia-proximo");

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
		sera_registrado: "Será registrado",
		link_documento_identificacao: "Documento de identificação",
		ciente_registro_responsavel_filhotes: "Ciente do pagamento dos dois registros",
		ciente_acompanhamento_filhotes: "Ciente do acompanhamento no ramo Filhotes",
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

	// ----------------------------------------------------------------------------------
	// Ramo Filhotes
	//
	// O ramo é decidido pela data de nascimento, e ela é editável nesta tela: ler o campo
	// `ramo` gravado deixaria a UI defasada de quem corrigiu a data agora. Os blocos do
	// ramo são renderizados sempre e escondidos aqui — assim eles trazem o que já está
	// gravado e o registro de um irmão mais velho não apaga o cadastro do responsável.
	// ----------------------------------------------------------------------------------

	function parseIsoDate(value) {
		const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ""));
		if (!match) return null;
		const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
		return Number.isNaN(date.getTime()) ? null : date;
	}

	// Espelha idade_decimal() de novo_associado.py: anos inteiros + fração de meses.
	function idadeDecimal(value) {
		const nascimento = parseIsoDate(value);
		if (!nascimento) return null;

		const hoje = new Date();
		let anos = hoje.getFullYear() - nascimento.getFullYear();
		let meses = hoje.getMonth() - nascimento.getMonth();
		if (hoje.getDate() < nascimento.getDate()) meses -= 1;
		if (meses < 0) {
			anos -= 1;
			meses += 12;
		}
		return anos + meses / 12;
	}

	function isFilhotes() {
		if (!idadeTransicaoFilhotes) return false;
		const idade = idadeDecimal(getControlValue(getMainControl("data_de_nascimento")));
		return idade !== null && idade <= idadeTransicaoFilhotes;
	}

	function seraRegistradoChecks() {
		return Array.from(
			document.querySelectorAll(".sera-registrado-check[data-fieldname='sera_registrado']")
		).filter((check) => !check.closest(".responsavel-wrapper")?.hidden);
	}

	function formatBRL(value) {
		return `R$ ${Number(value || 0)
			.toFixed(2)
			.replace(".", ",")
			.replace(/\B(?=(\d{3})+(?!\d))/g, ".")}`;
	}

	// Erros dos campos do ramo ficam fora de `.registro-field`, então não passam pelo
	// setInvalid genérico; `clearValidation` ainda limpa os dois, por [data-field-error].
	function setFilhotesError(scope, fieldName, message) {
		const error = scope?.querySelector(`[data-field-error="${fieldName}"]`);
		if (!error) return;
		error.textContent = message;
		error.hidden = false;
	}

	function syncSeraRegistrado() {
		const checks = seraRegistradoChecks();
		// Com um responsável só não há escolha a fazer: é ele quem será registrado.
		const unico = checks.length === 1;
		checks.forEach((check) => {
			if (unico) check.checked = true;
			check.disabled = readOnly || unico;
		});
	}

	function applyFilhotesMode() {
		const filhotes = isFilhotes();
		// A visibilidade dos blocos do ramo é do CSS, por este atributo: no primeiro paint
		// ele já vem com o valor calculado no servidor.
		form.dataset.filhotes = filhotes ? "true" : "false";
		if (filhotes) syncSeraRegistrado();
	}

	function atualizarTotalFilhotes() {
		if (!filhotesTotal) return;

		const valor = Number(filhotesTotal.dataset.valorDefinitivo || 0);
		const marcados = seraRegistradoChecks().filter((check) => check.checked).length;

		if (filhotesTotalValor) filhotesTotalValor.textContent = formatBRL(valor * (1 + marcados));
		if (filhotesTotalDetalhe) {
			const plural = marcados === 1 ? "responsável" : "responsáveis";
			filhotesTotalDetalhe.textContent =
				`${formatBRL(valor)} do jovem + ${marcados} ${plural} × ${formatBRL(valor)}. ` +
				"O pagamento é combinado com a secretaria depois do envio dos dados.";
		}
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
		applyFilhotesMode();

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

		// Sobrou um responsável só: ele volta a ser obrigatoriamente o registrado.
		const status = card.querySelector("[data-documento-status]");
		if (status) status.hidden = true;

		syncAddResponsavelButton();
		toggleGuardiaoLegal();
		applyFilhotesMode();
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
				card.dispatchEvent(
					new CustomEvent("gris:responsavel-preenchido", {
						bubbles: true,
						detail: { card },
					})
				);

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

		if (isFilhotes()) {
			const checks = seraRegistradoChecks();
			if (!checks.some((check) => check.checked)) {
				setFilhotesError(
					checks[0]?.closest(".registro-filhotes-registro"),
					"sera_registrado",
					"Selecione ao menos um responsável que será registrado."
				);
				valid = false;
				if (!firstInvalid) firstInvalid = checks[0];
			}

			// Naturalidade é obrigatória para todo responsável do ramo, não só para quem
			// será registrado: é o dado que a declaração de idoneidade exige.
			visibleResponsavelCards().forEach((card) => {
				["cidade_de_nascimento", "uf_de_nascimento"].forEach((fieldName) => {
					const control = getResponsavelControl(card, fieldName);
					if (!String(getControlValue(control) || "").trim()) {
						markInvalid(control, "Campo obrigatório.");
					}
				});
			});

			visibleResponsavelCards().forEach((card) => {
				const check = card.querySelector(
					".sera-registrado-check[data-fieldname='sera_registrado']"
				);
				if (!check?.checked) return;

				const nome =
					card.querySelector(".responsavel-card__title")?.textContent?.trim() ||
					"o responsável";

				const documento = card.querySelector("[data-documento-identificacao]");
				const link = documento
					?.querySelector("input[data-fieldname='link_documento_identificacao']")
					?.value?.trim();
				if (!link) {
					setFilhotesError(
						documento,
						"link_documento_identificacao",
						`Envie o documento de identificação com foto de ${nome}.`
					);
					valid = false;
					if (!firstInvalid) firstInvalid = documento;
				}
			});
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

	// ----------------------------------------------------------------------------------
	// Conferência por dupla digitação
	//
	// Errar um dígito do CPF ou o ano de nascimento é o engano mais comum deste formulário, e
	// nem o dígito verificador nem o resumo final pegam isso: só redigitar pega. Antes de
	// qualquer outro diálogo do save, quem mexeu nesses dois campos redigita os dois; se o que
	// foi digitado divergir do formulário, as duas versões aparecem e o usuário escolhe a certa.
	//
	// No primeiro envio todo mundo confere, porque nada ali passou por conferência ainda — o
	// que o servidor renderizou veio da recepção ou de um preenchimento anterior, e é
	// exatamente onde mora o erro que este passo existe para pegar. Depois de enviado, só
	// confere quem teve CPF ou data alterados: cobrar tudo de novo de quem voltou só para
	// arrumar o endereço seria atrito sem ganho.
	// ----------------------------------------------------------------------------------

	const CONFERENCIA_CAMPOS = ["cpf", "data_de_nascimento"];
	const CONFERENCIA_ROTULOS = { cpf: "CPF", data_de_nascimento: "Data de nascimento" };

	const registroJaEnviado = form.dataset.registroEnviado === "true";
	const conferenciaBaseline = new Map();
	const conferenciaConferidos = new Set();
	let conferenciaEtapas = [];
	let conferenciaIndice = 0;
	let conferenciaFase = "digitar";
	let conferenciaDivergencias = [];
	let conferenciaEscolhas = {};
	let conferenciaConcluindo = false;

	function digitosCpf(value) {
		return String(value == null ? "" : value).replace(/\D/g, "");
	}

	// `null` é o beneficiário; um card é o responsável daquele card.
	function controleDoFormulario(card, fieldName) {
		return card ? getResponsavelControl(card, fieldName) : getMainControl(fieldName);
	}

	function valoresDeConferencia(card) {
		return {
			cpf: digitosCpf(getControlValue(controleDoFormulario(card, "cpf"))),
			data_de_nascimento: String(
				getControlValue(controleDoFormulario(card, "data_de_nascimento")) || ""
			),
		};
	}

	function registrarBaselineConferencia(card) {
		conferenciaBaseline.set(card || "main", valoresDeConferencia(card));
	}

	// Chamado ao fim de cada etapa: o valor confirmado vira o novo baseline e a pessoa fica
	// marcada como conferida nesta sessão.
	function marcarConferido(card) {
		registrarBaselineConferencia(card);
		conferenciaConferidos.add(card || "main");
	}

	function conferenciaPendente(card) {
		const baseline = conferenciaBaseline.get(card || "main");
		// Sem baseline (card que nem existia no primeiro paint) o lado seguro é conferir.
		if (!baseline) return true;

		const atual = valoresDeConferencia(card);
		return (
			baseline.cpf !== atual.cpf || baseline.data_de_nascimento !== atual.data_de_nascimento
		);
	}

	function precisaConferir(card) {
		// Mexeu no CPF ou na data agora: confere, mesmo que já tenha conferido antes.
		if (conferenciaPendente(card)) return true;

		// Primeiro envio: confere uma vez por pessoa. O `Set` é o que evita repetir tudo se o
		// save falhar por outro motivo (telefone de cobrança inválido, por exemplo) e o
		// responsável corrigir e salvar de novo sem sair da página.
		return !registroJaEnviado && !conferenciaConferidos.has(card || "main");
	}

	function etapasDeConferencia() {
		if (!conferenciaDialog) return [];

		const etapas = [];
		if (precisaConferir(null)) etapas.push({ slot: "main", card: null });

		// Card escondido é responsável que não será salvo: conferir os dados dele não faz
		// sentido. O índice do slot acompanha a ordem em que o template renderizou os cards.
		const todos = Array.from(document.querySelectorAll(".responsavel-card"));
		visibleResponsavelCards().forEach((card) => {
			if (!precisaConferir(card)) return;
			etapas.push({ slot: `responsavel-${todos.indexOf(card) + 1}`, card });
		});

		return etapas;
	}

	function blocoDaEtapa(etapa) {
		return conferenciaDialog.querySelector(`[data-conferencia-slot="${etapa.slot}"]`);
	}

	function faseDaEtapa(etapa, fase) {
		return blocoDaEtapa(etapa).querySelector(`[data-conferencia-fase="${fase}"]`);
	}

	function campoDigitado(etapa, fieldName) {
		return blocoDaEtapa(etapa).querySelector(`[data-conferencia-campo="${fieldName}"]`);
	}

	function nomeDaEtapa(etapa) {
		const nome = String(
			getControlValue(controleDoFormulario(etapa.card, "nome_completo")) || ""
		).trim();
		if (nome) return nome;
		return etapa.card ? "Responsável" : "Novo Associado";
	}

	function formatarDataBR(value) {
		const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ""));
		return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value || "");
	}

	function aplicarMascaraData(input) {
		let value = input.value.replace(/\D/g, "").slice(0, 8);
		if (value.length > 4) {
			value = value.replace(/^(\d{2})(\d{2})(\d{1,4}).*/, "$1/$2/$3");
		} else if (value.length > 2) {
			value = value.replace(/^(\d{2})(\d{1,2}).*/, "$1/$2");
		}
		input.value = value;
	}

	// "dd/mm/aaaa" -> "aaaa-mm-dd", o formato em que o formulário guarda a data. Devolve vazio
	// quando a data não existe no calendário: o Date normaliza 31/02 para 03/03 em silêncio, e
	// aceitar isso gravaria uma data que ninguém digitou.
	function dataDigitadaParaIso(value) {
		const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(String(value || "").trim());
		if (!match) return "";

		const [, dia, mes, ano] = match;
		const data = new Date(Number(ano), Number(mes) - 1, Number(dia));
		const confere =
			data.getFullYear() === Number(ano) &&
			data.getMonth() === Number(mes) - 1 &&
			data.getDate() === Number(dia);

		return confere ? `${ano}-${mes}-${dia}` : "";
	}

	// O CPF é comparado como está; a data digitada vira ISO para bater com o formulário.
	function valorDigitadoNaConferencia(etapa, fieldName) {
		const bruto = String(getControlValue(campoDigitado(etapa, fieldName)) || "").trim();
		return fieldName === "data_de_nascimento" ? dataDigitadaParaIso(bruto) : bruto;
	}

	function formatarValorConferencia(fieldName, value) {
		if (!value) return "Em branco";
		return fieldName === "data_de_nascimento" ? formatarDataBR(value) : String(value);
	}

	function validarEtapaConferencia(etapa) {
		let valido = true;

		const cpfControl = campoDigitado(etapa, "cpf");
		const cpf = String(getControlValue(cpfControl) || "").trim();
		if (!cpf) {
			setInvalid(cpfControl, "Digite o CPF novamente.");
			valido = false;
		} else if (!validateCPF(cpf)) {
			// Barrar aqui evita que um erro de digitação da própria conferência vire uma
			// "divergência" e acabe oferecido como opção correta.
			setInvalid(cpfControl, "CPF inválido. Confira a digitação.");
			valido = false;
		}

		const dataControl = campoDigitado(etapa, "data_de_nascimento");
		const data = String(getControlValue(dataControl) || "").trim();
		if (!data) {
			setInvalid(dataControl, "Digite a data de nascimento novamente.");
			valido = false;
		} else if (!dataDigitadaParaIso(data)) {
			// Mesmo motivo do CPF: erro de digitação da própria conferência não pode virar
			// uma "divergência" e acabar oferecido como opção correta.
			setInvalid(dataControl, "Data inválida. Use o formato dd/mm/aaaa.");
			valido = false;
		}

		return valido;
	}

	function divergenciasDaEtapa(etapa) {
		return CONFERENCIA_CAMPOS.map((fieldName) => {
			const atual = String(
				getControlValue(controleDoFormulario(etapa.card, fieldName)) || ""
			);
			const digitado = valorDigitadoNaConferencia(etapa, fieldName);
			// Reformatar o CPF não é alterar o CPF.
			const iguais =
				fieldName === "cpf"
					? digitosCpf(atual) === digitosCpf(digitado)
					: atual === digitado;
			return iguais ? null : { campo: fieldName, atual, digitado };
		}).filter(Boolean);
	}

	function opcaoDivergenciaHtml(fieldName, origem, rotulo, value) {
		return `
			<button type="button" class="registro-conferencia-opcao" role="radio" aria-checked="false"
				data-conferencia-opcao="${escapeHtml(fieldName)}"
				data-conferencia-origem="${escapeHtml(origem)}">
				<span class="registro-conferencia-opcao__rotulo">${escapeHtml(rotulo)}</span>
				<span class="registro-conferencia-opcao__valor">${escapeHtml(
					formatarValorConferencia(fieldName, value)
				)}</span>
			</button>
		`;
	}

	function renderDivergencias(etapa) {
		faseDaEtapa(etapa, "digitar").hidden = true;

		const alvo = faseDaEtapa(etapa, "divergencia");
		alvo.innerHTML =
			`<p class="registro-conferencia-aviso">
				O que você digitou não confere com o formulário. Toque na informação correta.
			</p>` +
			conferenciaDivergencias
				.map((item) => {
					const rotulo = CONFERENCIA_ROTULOS[item.campo];
					return `
				<div class="registro-conferencia-campo">
					<p class="registro-conferencia-campo__titulo">${escapeHtml(rotulo)}</p>
					<div class="registro-conferencia-opcoes" role="radiogroup" aria-label="${escapeHtml(
						`${rotulo} correto`
					)}">
						${opcaoDivergenciaHtml(item.campo, "formulario", "O que está no formulário", item.atual)}
						${opcaoDivergenciaHtml(item.campo, "digitado", "O que você acabou de digitar", item.digitado)}
					</div>
				</div>
			`;
				})
				.join("");
		alvo.hidden = false;
	}

	function atualizarBotaoConferencia() {
		if (!conferenciaProximoButton) return;

		if (conferenciaFase === "divergencia") {
			conferenciaProximoButton.textContent = "Confirmar e continuar";
			conferenciaProximoButton.disabled = conferenciaDivergencias.some(
				(item) => !conferenciaEscolhas[item.campo]
			);
			return;
		}

		const ultima = conferenciaIndice === conferenciaEtapas.length - 1;
		conferenciaProximoButton.textContent = ultima ? "Confirmar dados" : "Próximo";
		conferenciaProximoButton.disabled = false;
	}

	// Limpa todos os blocos, não só o da etapa: o que foi digitado e as opções de divergência
	// carregam CPF e data, e não têm por que continuar no DOM depois que a etapa passou.
	function limparBlocosConferencia() {
		conferenciaDialog.querySelectorAll("[data-conferencia-slot]").forEach((bloco) => {
			bloco.hidden = true;
			bloco.querySelector("[data-conferencia-fase='digitar']").hidden = false;

			const divergencia = bloco.querySelector("[data-conferencia-fase='divergencia']");
			divergencia.hidden = true;
			divergencia.innerHTML = "";

			bloco.querySelectorAll("[data-conferencia-campo]").forEach((control) => {
				setControlValue(control, "");
				clearInvalidControl(control);
			});
		});
	}

	function renderEtapaConferencia() {
		const etapa = conferenciaEtapas[conferenciaIndice];
		if (!etapa) return;

		conferenciaFase = "digitar";
		conferenciaDivergencias = [];
		conferenciaEscolhas = {};

		limparBlocosConferencia();

		const bloco = blocoDaEtapa(etapa);
		bloco.hidden = false;
		bloco.querySelector("[data-conferencia-nome]").textContent = nomeDaEtapa(etapa);

		if (conferenciaProgresso) {
			conferenciaProgresso.textContent = `Etapa ${conferenciaIndice + 1} de ${
				conferenciaEtapas.length
			}`;
		}

		atualizarBotaoConferencia();
		window.setTimeout(() => campoDigitado(etapa, "cpf")?.focus(), 100);
	}

	function aplicarEscolhasConferencia(etapa) {
		conferenciaDivergencias.forEach((item) => {
			if (conferenciaEscolhas[item.campo] !== "digitado") return;
			// Escrever no controle do formulário é o que faz a correção chegar ao save: as
			// coletoras do payload leem o formulário depois da conferência.
			const control = controleDoFormulario(etapa.card, item.campo);
			setControlValue(control, item.digitado);
			clearInvalidControl(control);
		});
	}

	function proximaEtapaConferencia() {
		if (conferenciaIndice < conferenciaEtapas.length - 1) {
			conferenciaIndice += 1;
			renderEtapaConferencia();
			return;
		}
		concluirConferencia();
	}

	function concluirConferencia() {
		conferenciaConcluindo = true;
		closeDialog(conferenciaDialog);
		conferenciaConcluindo = false;
		conferenciaEtapas = [];
		limparBlocosConferencia();

		// A correção pode ter criado um problema novo: um CPF que agora duplica o de outra
		// pessoa, ou uma data que joga o jovem no ramo Filhotes e passa a exigir naturalidade e
		// documento com foto. Revalidar aqui devolve o usuário ao campo certo, em vez de deixar
		// o erro aparecer só na resposta do servidor.
		if (!validateForm()) return;
		continuarSubmit();
	}

	function avancarConferencia() {
		const etapa = conferenciaEtapas[conferenciaIndice];
		if (!etapa) return;

		if (conferenciaFase === "divergencia") {
			aplicarEscolhasConferencia(etapa);
			marcarConferido(etapa.card);
			proximaEtapaConferencia();
			return;
		}

		if (!validarEtapaConferencia(etapa)) return;

		conferenciaDivergencias = divergenciasDaEtapa(etapa);
		if (!conferenciaDivergencias.length) {
			marcarConferido(etapa.card);
			proximaEtapaConferencia();
			return;
		}

		conferenciaFase = "divergencia";
		conferenciaEscolhas = {};
		renderDivergencias(etapa);
		atualizarBotaoConferencia();
	}

	function abrirConferencia(etapas) {
		conferenciaEtapas = etapas;
		conferenciaIndice = 0;
		renderEtapaConferencia();
		openDialog(conferenciaDialog);
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

	// A URL do Drive não diz nada a quem está conferindo os dados; o card já mostra o
	// estado do envio com um link clicável.
	const summarySkipFields = new Set(["name", "link_documento_identificacao"]);

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
			if (summarySkipFields.has(key) || seen.has(key)) return;
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
		if (card.hidden) return;
		document.querySelectorAll(".registro-option-card").forEach((item) => {
			item.setAttribute("aria-selected", item === card ? "true" : "false");
		});
		selectedTipoInput.value = card.dataset.value || "";
		updateTipoContinueButton();
	}

	// No ramo Filhotes o "Continuar" também depende das duas ciências sobre o registro
	// do responsável, que é o que muda de fato no fluxo desse ramo.
	function updateTipoContinueButton() {
		const cienciasOk =
			!isFilhotes() ||
			Boolean(cienciaPagamentoCheck?.checked && cienciaAcompanhamentoCheck?.checked);
		confirmTipoButton.disabled = !(selectedTipoInput.value && cienciasOk);
	}

	function openTipoRegistroModal(payload) {
		pendingSave = payload;
		resetTipoSelection();

		const filhotes = isFilhotes();
		if (filhotesAviso) filhotesAviso.hidden = !filhotes;
		if (filhotesTotal) filhotesTotal.hidden = !filhotes;
		if (filhotesCiencia) filhotesCiencia.hidden = !filhotes;
		if (provisorioCard) provisorioCard.hidden = filhotes;
		// Com uma opção só, o grid de duas colunas deixaria o card encostado à esquerda.
		tipoOptions?.classList.toggle("registro-type-options--single", filhotes);

		if (filhotes) {
			if (cienciaPagamentoCheck) cienciaPagamentoCheck.checked = false;
			if (cienciaAcompanhamentoCheck) cienciaAcompanhamentoCheck.checked = false;
			atualizarTotalFilhotes();
			// Definitivo é a única opção do ramo: já entra selecionado.
			const definitivo = document.querySelector(
				'.registro-option-card[data-value="Definitivo"]'
			);
			if (definitivo) selectTipoCard(definitivo);
		}

		updateTipoContinueButton();
		openDialog(tipoDialog);
	}

	function resetPendingSubmit() {
		if (!pendingSave || saving) return;
		setLoading(pendingSave.submitButton, false);
	}

	function renderProximosPassos(responsaveis) {
		if (!proximosPassosLista) return;

		proximosPassosLista.innerHTML = responsaveis
			.map(
				(responsavel) => `
			<div class="registro-declaracao-item" data-responsavel="${escapeHtml(responsavel.name)}">
				<strong class="registro-declaracao-item__nome">${escapeHtml(responsavel.nome_completo)}</strong>
				<button type="button" class="btn-sm-outline" data-baixar-declaracao="${escapeHtml(
					responsavel.name
				)}">Baixar declaração</button>
			</div>
		`
			)
			.join("");
	}

	// A geração é síncrona de propósito: quem clica está esperando o arquivo. O endpoint é
	// idempotente, então clicar de novo devolve o mesmo PDF em vez de gerar outro.
	// O arquivo vem pelo GRIS, não pelo link do Drive: a pasta é de acesso restrito e o
	// responsável não tem conta no drive do grupo. Usamos fetch em vez de abrir a URL numa
	// aba para manter o estado de carregando e mostrar o erro no diálogo da página — numa
	// aba nova a falha apareceria como JSON cru.
	async function baixarArquivoDoServidor(button, method, args, rotuloCarregando, tituloErro) {
		setLoading(button, true, rotuloCarregando);

		try {
			const resposta = await fetch(`/api/method/${method}`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Accept: "application/pdf, application/json",
					"X-Frappe-CSRF-Token": frappe.csrf_token || "",
				},
				credentials: "same-origin",
				body: JSON.stringify(args),
			});

			// Erro vem como JSON; sucesso vem como o arquivo.
			const tipo = resposta.headers.get("Content-Type") || "";
			if (!resposta.ok || tipo.includes("application/json")) {
				let mensagem = "";
				try {
					mensagem = serverMessages(await resposta.json())[0];
				} catch (e) {
					mensagem = "";
				}
				showErrorDialog(mensagem, tituloErro);
				return;
			}

			const blob = await resposta.blob();
			const url = URL.createObjectURL(blob);
			const nome = nomeDoContentDisposition(resposta) || "documento.pdf";
			const link = document.createElement("a");
			link.href = url;
			link.download = nome;
			document.body.appendChild(link);
			link.click();
			link.remove();
			// Revogar na hora cancelaria o download em alguns navegadores.
			window.setTimeout(() => URL.revokeObjectURL(url), 60000);
		} catch (error) {
			showErrorDialog("", tituloErro);
		} finally {
			setLoading(button, false);
		}
	}

	function nomeDoContentDisposition(resposta) {
		const header = resposta.headers.get("Content-Disposition") || "";
		const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header);
		if (!match) return "";
		try {
			return decodeURIComponent(match[1]);
		} catch (e) {
			return match[1];
		}
	}

	function baixarDeclaracao(button) {
		const responsavelName = button.dataset.baixarDeclaracao;
		if (!responsavelName) return;

		baixarArquivoDoServidor(
			button,
			"gris.www.responsavel.registro.baixar_declaracao_idoneidade",
			{ novo_associado_name: novoAssociadoName, responsavel_name: responsavelName },
			"Gerando...",
			"Não foi possível gerar a declaração"
		);
	}

	function baixarDocumentoIdentificacao(button) {
		const responsavelName = button.dataset.baixarDocumento;
		if (!responsavelName) return;

		baixarArquivoDoServidor(
			button,
			"gris.www.responsavel.registro.baixar_documento_identificacao",
			{ novo_associado_name: novoAssociadoName, responsavel_name: responsavelName },
			"Abrindo...",
			"Não foi possível abrir o documento"
		);
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
		const card = event.target.closest(".responsavel-card");
		const title = card?.querySelector(".responsavel-card__title");
		if (title) title.textContent = event.target.value || "Novo Responsável";
		sincronizarNomeNoUpload(card);
	});

	// O nome do arquivo no Drive é "Documento de identidade - <nome do responsável>", e o
	// upload acontece antes do save: o nome tem que vir do card, atualizado enquanto digita.
	function sincronizarNomeNoUpload(card) {
		const componente = card?.querySelector(
			"[data-documento-identificacao] [data-file-upload]"
		);
		if (!componente) return;

		let params = {};
		try {
			params = JSON.parse(componente.dataset.extraParams || "{}");
		} catch (e) {
			params = {};
		}
		params.responsavel_nome =
			getControlValue(getResponsavelControl(card, "nome_completo")) || "";
		componente.dataset.extraParams = JSON.stringify(params);
	}

	// Busca por CPF preenche o nome sem passar pelo evento de digitação.
	document.addEventListener("gris:responsavel-preenchido", (event) => {
		sincronizarNomeNoUpload(event.detail?.card);
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

	// Os controles da conferência ficam fora do <form>, então não passam pelos ouvintes
	// delegados dele: máscara e limpeza de erro são ligadas aqui.
	conferenciaDialog?.addEventListener("input", (event) => {
		const campo = event.target.dataset?.conferenciaCampo;
		if (!campo) return;
		if (campo === "cpf") applyCPFMask(event.target);
		if (campo === "data_de_nascimento") aplicarMascaraData(event.target);
		clearInvalidControl(event.target);
	});

	conferenciaDialog?.addEventListener("click", (event) => {
		const opcao = event.target.closest("[data-conferencia-opcao]");
		if (!opcao) return;

		conferenciaEscolhas[opcao.dataset.conferenciaOpcao] = opcao.dataset.conferenciaOrigem;
		opcao
			.closest(".registro-conferencia-opcoes")
			.querySelectorAll("[data-conferencia-opcao]")
			.forEach((item) => {
				item.setAttribute("aria-checked", item === opcao ? "true" : "false");
			});
		atualizarBotaoConferencia();
	});

	conferenciaProximoButton?.addEventListener("click", avancarConferencia);

	// Fechar o diálogo cancela o save. O botão de salvar já voltou ao estado normal antes de
	// ele abrir, então só o estado da conferência precisa ser descartado.
	conferenciaDialog?.addEventListener("close", () => {
		if (conferenciaConcluindo) return;
		conferenciaEtapas = [];
		conferenciaDivergencias = [];
		conferenciaEscolhas = {};
		limparBlocosConferencia();
	});

	confirmDataCheck?.addEventListener("change", updateConfirmButton);
	confirmImageCheck?.addEventListener("change", updateConfirmButton);
	cienciaPagamentoCheck?.addEventListener("change", updateTipoContinueButton);
	cienciaAcompanhamentoCheck?.addEventListener("change", updateTipoContinueButton);

	// A data de nascimento decide o ramo, e ela é editável: a UI do ramo Filhotes acompanha
	// a mudança sem exigir reload.
	const dataNascimentoControl = getMainControl("data_de_nascimento");
	dataNascimentoControl?.addEventListener("datepicker:change", applyFilhotesMode);
	dataNascimentoControl?.addEventListener("change", applyFilhotesMode);

	document.addEventListener("change", (event) => {
		if (event.target.matches(".sera-registrado-check[data-fieldname='sera_registrado']")) {
			atualizarTotalFilhotes();
		}
	});

	document.getElementById("btn-abrir-declaracao")?.addEventListener("click", () => {
		openDialog(enviarDeclaracaoDialog);
	});

	document.addEventListener("click", (event) => {
		const baixarDecl = event.target.closest("[data-baixar-declaracao]");
		if (baixarDecl) {
			event.preventDefault();
			baixarDeclaracao(baixarDecl);
			return;
		}

		const baixarDoc = event.target.closest("[data-baixar-documento]");
		if (baixarDoc) {
			event.preventDefault();
			baixarDocumentoIdentificacao(baixarDoc);
		}
	});

	// O componente de upload manda o arquivo direto para o Drive e devolve o link; aqui só
	// guardamos o link no card, para o save amarrá-lo ao responsável.
	document.addEventListener("gris:file-upload:success", (event) => {
		const link = event.detail?.files?.[0]?.file_url || "";
		if (!link) return;

		const documento = event.target.closest("[data-documento-identificacao]");
		if (documento) {
			const hidden = documento.querySelector(
				"input[data-fieldname='link_documento_identificacao']"
			);
			if (hidden) hidden.value = link;

			const status = documento.querySelector("[data-documento-status]");
			if (status) status.hidden = false;

			// O botão baixa pelo `name` do Responsavel, que só existe depois do save: num
			// card de responsável novo ele fica escondido até a página recarregar.
			const botao = documento.querySelector("[data-documento-link]");
			const responsavelId =
				documento.closest(".responsavel-card")?.dataset.responsavelId || "";
			if (botao) {
				botao.dataset.baixarDocumento = responsavelId;
				botao.hidden = !responsavelId;
			}

			const erro = documento.querySelector(
				"[data-field-error='link_documento_identificacao']"
			);
			if (erro) {
				erro.textContent = "";
				erro.hidden = true;
			}
			return;
		}

		if (event.target.closest(".registro-declaracao-item")) {
			showToast(
				"success",
				"Declaração enviada",
				"A declaração de idoneidade assinada foi recebida."
			);
			reloadSoon();
		}
	});

	proximosPassosDialog?.addEventListener("close", () => {
		// O reload é adiado até aqui para o responsável conseguir baixar as declarações.
		window.location.reload();
	});

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
		if (isFilhotes()) {
			pendingSave.formData.ciente_registro_responsavel_filhotes =
				cienciaPagamentoCheck?.checked ? 1 : 0;
			pendingSave.formData.ciente_acompanhamento_filhotes =
				cienciaAcompanhamentoCheck?.checked ? 1 : 0;
		}
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
				if (r.exc) return;

				showToast(
					"success",
					"Dados atualizados",
					"As informações foram salvas com sucesso."
				);

				// No ramo Filhotes ainda faltam o curso e a declaração de idoneidade: o
				// dialog explica os dois e o reload só acontece quando ele é fechado.
				const resultado = r.message || {};
				const paraRegistro = resultado.responsaveis_para_registro || [];
				if (
					Number(resultado.is_filhotes) === 1 &&
					paraRegistro.length &&
					proximosPassosDialog
				) {
					renderProximosPassos(paraRegistro);
					openDialog(proximosPassosDialog);
					return;
				}

				reloadSoon();
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

	// Roda depois da conferência: o payload precisa ser coletado do formulário já corrigido.
	function continuarSubmit() {
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
	}

	form.addEventListener("submit", (event) => {
		event.preventDefault();
		if (readOnly) return;
		setLoading(submitButton, true, "Validando...");
		if (!validateForm()) {
			setLoading(submitButton, false);
			return;
		}
		setLoading(submitButton, false);

		// A conferência vem antes da coleta do payload de propósito: ela corrige os controles
		// do formulário, e as coletoras leem o formulário. Ninguém mexeu em CPF nem em data de
		// nascimento? Então não há o que conferir, e o fluxo segue como sempre foi.
		const etapas = etapasDeConferencia();
		if (!etapas.length) {
			continuarSubmit();
			return;
		}

		abrirConferencia(etapas);
	});

	syncAddResponsavelButton();
	toggleGuardiaoLegal();
	applyFilhotesMode();

	// O baseline é o que o servidor renderizou: é contra ele que a conferência decide quem
	// precisa redigitar CPF e data de nascimento.
	registrarBaselineConferencia(null);
	document
		.querySelectorAll(".responsavel-card")
		.forEach((card) => registrarBaselineConferencia(card));

	if (readOnly) setReadOnlyMode();

	// Registro salvo e declaração assinada pendente: é o momento em que o responsável tem o
	// arquivo em mãos, então o pedido aparece sem depender de ele achar o banner.
	if (enviarDeclaracaoDialog) openDialog(enviarDeclaracaoDialog);
});
