frappe.ready(() => {
	const btnFiltrar = document.getElementById("btn-filtrar");
	const btnNova = document.getElementById("btn-nova-entrevista");
	const btnConfirmar = document.getElementById("confirmar-modal-associado");
	const tbody = document.getElementById("lista-entrevistas");
	const loadingState = document.getElementById("entrevistas-loading");
	const emptyState = document.getElementById("entrevistas-empty");
	const tableWrapper = document.getElementById("entrevistas-table-wrapper");

	let associadosAdultos = [];
	let entrevistas = [];

	const setState = (state) => {
		loadingState?.classList.toggle("hidden", state !== "loading");
		emptyState?.classList.toggle("hidden", state !== "empty");
		tableWrapper?.classList.toggle("hidden", state !== "table");
	};

	const getFilterSelect = () => document.getElementById("filtro-associado");
	const getModalSelect = () => document.getElementById("novo-associado");

	const buildAssociateItems = (emptyLabel) => {
		const items = [{ value: "", label: emptyLabel }];
		for (const row of associadosAdultos) {
			const label = row.nome_completo || row.name;
			items.push({
				value: row.name,
				label,
				attrs: { "data-keywords": `${row.name} ${row.nome_completo || ""}`.trim() },
			});
		}
		return items;
	};

	const renderRows = (rows) => {
		if (!tbody) {
			return;
		}

		if (!rows.length) {
			tbody.innerHTML = "";
			setState("empty");
			return;
		}

		tbody.innerHTML = rows
			.map((row) => {
				const associado = frappe.utils.escape_html(
					row.associado_nome || row.associado || "-",
				);
				const atualizacao = row.data_da_ultima_atualizacao
					? frappe.utils.escape_html(
							frappe.datetime.str_to_user(row.data_da_ultima_atualizacao),
						)
					: "-";
				const href = `/gestao_adultos/respostas_entrevista?name=${encodeURIComponent(
					row.name,
				)}`;
				return `
					<tr>
						<td>${associado}</td>
						<td>${atualizacao}</td>
						<td class="interview-table__actions">
							<a class="btn-sm-outline" href="${href}">Abrir</a>
						</td>
					</tr>
				`;
			})
			.join("");
		setState("table");
	};

	const applyFilter = () => {
		const associado = getSelectValue(getFilterSelect());
		if (!associado) {
			renderRows(entrevistas);
			return;
		}
		renderRows(entrevistas.filter((row) => String(row.associado || "") === String(associado)));
	};

	const carregarAssociados = async () => {
		const response = await frappe.call({
			method: "gris.api.gestao_adultos.listar_associados_adultos",
		});
		associadosAdultos = response.message || [];
		repopulateSelect("filtro-associado", buildAssociateItems("Todos os associados"));
		repopulateSelect("novo-associado", buildAssociateItems("Selecione um associado"));
	};

	const carregarEntrevistas = async () => {
		setState("loading");
		const response = await frappe.call({
			method: "gris.api.gestao_adultos.listar_entrevistas",
			args: {},
		});
		entrevistas = response.message || [];
		applyFilter();
	};

	const abrirOuCriarEntrevista = async () => {
		const associado = getSelectValue(getModalSelect());
		if (!associado) {
			frappe.msgprint(__("Selecione um associado para continuar."));
			return;
		}

		const response = await frappe.call({
			method: "gris.api.gestao_adultos.obter_ou_criar_entrevista",
			args: { associado },
		});
		const data = response.message || {};
		if (data.name) {
			window.location.href = `/gestao_adultos/respostas_entrevista?name=${encodeURIComponent(
				data.name,
			)}`;
		}
	};

	btnFiltrar?.addEventListener("click", applyFilter);
	document.addEventListener("change", (event) => {
		if (event.target.closest && event.target.closest("#filtro-associado")) {
			applyFilter();
		}
	});
	btnNova?.addEventListener("click", () => {
		const modalSelect = getModalSelect();
		if (modalSelect) {
			modalSelect.value = "";
		}
		openDialog("novo-associado-dialog");
	});
	btnConfirmar?.addEventListener("click", abrirOuCriarEntrevista);

	carregarAssociados()
		.then(carregarEntrevistas)
		.catch((error) => {
			console.error(error);
			setState("empty");
			frappe.msgprint(__("Não foi possível carregar a página de entrevistas."));
		});
});

function getSelectValue(element) {
	if (!element) {
		return "";
	}
	const value = element.value;
	return Array.isArray(value) ? value[0] || "" : value || "";
}

function repopulateSelect(id, items) {
	const oldElement = document.getElementById(id);
	if (!oldElement) {
		return;
	}

	const listbox = oldElement.querySelector('[role="listbox"]');
	const hiddenInput = oldElement.querySelector('input[type="hidden"]');
	const triggerLabel = oldElement.querySelector(":scope > button > span");
	if (!listbox || !hiddenInput || !triggerLabel) {
		return;
	}

	listbox.innerHTML = (items || [])
		.map((item, index) => {
			const attrs = Object.entries(item.attrs || {})
				.map(([key, value]) => ` ${key}="${escapeAttribute(String(value))}"`)
				.join("");
			return `<div id="${id}-items-${index + 1}" role="option" data-value="${escapeAttribute(
				String(item.value ?? ""),
			)}"${attrs}>${frappe.utils.escape_html(item.label || "")}</div>`;
		})
		.join("");

	hiddenInput.value = "";
	triggerLabel.textContent = items?.[0]?.label || "Selecione";

	const newElement = oldElement.cloneNode(true);
	newElement.removeAttribute("data-select-initialized");
	oldElement.parentNode.replaceChild(newElement, oldElement);
}

function escapeAttribute(value) {
	return value
		.replaceAll("&", "&amp;")
		.replaceAll('"', "&quot;")
		.replaceAll("<", "&lt;")
		.replaceAll(">", "&gt;");
}

function openDialog(id) {
	const dialog = document.getElementById(id);
	if (!dialog || typeof dialog.showModal !== "function") {
		return;
	}
	if (!dialog.open) {
		dialog.showModal();
	}
}
