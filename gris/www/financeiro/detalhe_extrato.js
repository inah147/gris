document.addEventListener("DOMContentLoaded", () => {
	const TRANSFER_CATEGORIES = new Set([
		"Transferência entre Contas",
		"Transferência entre Carteiras",
	]);

	const btnSalvar = document.getElementById("btn-salvar-extrato");
	const footerSalvar = document.getElementById("footer-salvar");
	if (!btnSalvar || !footerSalvar) {
		return;
	}

	const editableFields = [
		"descricao",
		"descricao_reduzida",
		"categoria",
		"centro_de_custo",
		"ordinaria_extraordinaria",
		"conta_fixa",
		"beneficiario",
		"repasse_entre_contas",
		"transacao_revisada",
		"observacoes",
	];

	let initialData = {};

	const setHidden = (element, hidden) => {
		if (!element) {
			return;
		}
		element.classList.toggle("hidden", hidden);
	};

	const getFieldElement = (field) => document.querySelector(`[name="${field}"]`);

	const getSelectWrapper = (field) => {
		const input = getFieldElement(field);
		return input ? input.closest(".select") : null;
	};

	const getFieldValue = (field) => {
		const element = getFieldElement(field);
		if (!element) {
			return "";
		}

		if (element.type === "checkbox") {
			return element.checked ? "1" : "0";
		}

		return String(element.value ?? "");
	};

	const getFormData = () => {
		const data = {};
		editableFields.forEach((field) => {
			const element = getFieldElement(field);
			if (!element) {
				return;
			}
			data[field] = getFieldValue(field);
		});
		return data;
	};

	const hasChanges = (currentData) =>
		Object.keys(currentData).some((key) => currentData[key] !== initialData[key]);

	const updateSaveVisibility = () => {
		const currentData = getFormData();
		setHidden(footerSalvar, !hasChanges(currentData));
	};

	const toggleConditionalFields = () => {
		const categoria = getFieldValue("categoria");
		const beneficiarioContainer = document.getElementById("beneficiario-field-container");
		const contaFixaContainer = document.getElementById("conta-fixa-field-container");
		const repasseEntreContas = getFieldElement("repasse_entre_contas");
		const isTransferCategory = TRANSFER_CATEGORIES.has(categoria);

		setHidden(beneficiarioContainer, categoria !== "Contribuição Mensal");
		setHidden(contaFixaContainer, categoria !== "Contas Ordinárias");

		if (repasseEntreContas) {
			repasseEntreContas.checked = isTransferCategory;
			repasseEntreContas.disabled = true;
		}
	};

	const toggleBannerSugestao = () => {
		const banner = document.getElementById("banner-sugestao-contribuicao");
		if (!banner) {
			return;
		}
		const revisada = getFieldElement("transacao_revisada");
		setHidden(banner, Boolean(revisada && revisada.checked));
	};

	const normalizeDocname = (value) => {
		if (!value) {
			return "";
		}

		const raw = String(value);
		try {
			return raw.includes("%") ? decodeURIComponent(raw) : raw;
		} catch (error) {
			return raw;
		}
	};

	const bindFieldListeners = () => {
		editableFields.forEach((field) => {
			const element = getFieldElement(field);
			if (!element) {
				return;
			}

			const onChange = () => {
				if (field === "categoria") {
					toggleConditionalFields();
				}
				if (field === "transacao_revisada") {
					toggleBannerSugestao();
				}
				updateSaveVisibility();
			};

			const selectWrapper = getSelectWrapper(field);
			if (selectWrapper) {
				selectWrapper.addEventListener("change", onChange);
				return;
			}

			if (element.type === "checkbox") {
				element.addEventListener("change", onChange);
				return;
			}

			element.addEventListener("input", onChange);
			element.addEventListener("change", onChange);
		});
	};

	toggleConditionalFields();
	toggleBannerSugestao();
	initialData = getFormData();
	bindFieldListeners();

	btnSalvar.addEventListener("click", () => {
		btnSalvar.disabled = true;
		btnSalvar.textContent = "Salvando...";

		const data = getFormData();
		const qsDocname = new URLSearchParams(window.location.search).get("name");
		const docname = normalizeDocname(
			(window.frappe && frappe.form_dict && frappe.form_dict.name) || qsDocname,
		);

		if (!docname) {
			if (window.frappe && typeof frappe.show_alert === "function") {
				frappe.show_alert({
					message: "ID do documento não encontrado.",
					indicator: "red",
				});
			} else {
				alert("ID do documento não encontrado.");
			}
			btnSalvar.disabled = false;
			btnSalvar.textContent = "Salvar";
			return;
		}

		frappe.call({
			method: "frappe.client.get",
			args: {
				doctype: "Transacao Extrato Geral",
				name: docname,
			},
			callback: (response) => {
				if (!response.message) {
					frappe.show_alert({ message: "Erro ao buscar documento.", indicator: "red" });
					btnSalvar.disabled = false;
					btnSalvar.textContent = "Salvar";
					return;
				}

				const doc = response.message;
				Object.assign(doc, data);

				frappe.call({
					method: "frappe.client.save",
					args: { doc },
					callback: (saveResponse) => {
						if (!saveResponse.exc) {
							initialData = getFormData();
							setHidden(footerSalvar, true);
							frappe.show_alert(__("Alterações salvas com sucesso!"));
						} else {
							frappe.show_alert({
								message: `Erro ao salvar: ${saveResponse.exc}`,
								indicator: "red",
							});
						}
						btnSalvar.disabled = false;
						btnSalvar.textContent = "Salvar";
					},
				});
			},
		});
	});
});
