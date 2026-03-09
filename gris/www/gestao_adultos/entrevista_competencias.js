frappe.ready(() => {
	const filtroAssociado = document.getElementById("filtro-associado");
	const filtroAssociadoList = document.getElementById("filtro-associado-list");
	const btnFiltrar = document.getElementById("btn-filtrar");
	const btnNova = document.getElementById("btn-nova-entrevista");
	const tbody = document.getElementById("lista-entrevistas");

	const modal = document.getElementById("modal-associado");
	const backdrop = document.getElementById("modal-associado-backdrop");
	const selectNovoAssociado = document.getElementById("novo-associado");
	const btnFecharModal = document.getElementById("fechar-modal-associado");
	const btnCancelarModal = document.getElementById("cancelar-modal-associado");
	const btnConfirmarModal = document.getElementById("confirmar-modal-associado");

	let associadosAdultos = [];

	function openModal() {
		backdrop.style.display = "block";
		modal.style.display = "flex";
		document.body.classList.add("modal-open");
	}

	function closeModal() {
		modal.style.display = "none";
		backdrop.style.display = "none";
		document.body.classList.remove("modal-open");
	}

	function fillAssociadoOptions() {
		const options = [];
		associadosAdultos.forEach((row) => {
			options.push(`<option value="${frappe.utils.escape_html(row.nome_completo || row.name)}"></option>`);
		});
		filtroAssociadoList.innerHTML = options.join("");

		const modalOptions = ["<option value=''>Selecione</option>"];
		associadosAdultos.forEach((row) => {
			modalOptions.push(`<option value="${frappe.utils.escape_html(row.name)}">${frappe.utils.escape_html(row.nome_completo || row.name)}</option>`);
		});
		selectNovoAssociado.innerHTML = modalOptions.join("");
	}

	function renderLista(rows) {
		if (!rows.length) {
			tbody.innerHTML = `<tr class="empty-row"><td colspan="3">Nenhuma entrevista encontrada.</td></tr>`;
			return;
		}

		tbody.innerHTML = rows
			.map((row) => {
				const associado = frappe.utils.escape_html(row.associado_nome || row.associado || "-");
				const dataAtualizacao = row.data_da_ultima_atualizacao
					? frappe.datetime.str_to_user(row.data_da_ultima_atualizacao)
					: "-";
				return `
					<tr>
						<td>${associado}</td>
						<td>${frappe.utils.escape_html(dataAtualizacao)}</td>
						<td class="text-end">
							<a class="btn-modern btn-modern--sm" href="/gestao_adultos/respostas_entrevista?name=${encodeURIComponent(row.name)}">Abrir</a>
						</td>
					</tr>
				`;
			})
			.join("");
	}

	async function carregarAssociados() {
		const response = await frappe.call({
			method: "gris.api.gestao_adultos.listar_associados_adultos",
		});
		associadosAdultos = response.message || [];
		fillAssociadoOptions();
	}

	async function carregarEntrevistas() {
		tbody.innerHTML = `<tr class="empty-row"><td colspan="3">Carregando...</td></tr>`;
		const termo = (filtroAssociado.value || "").trim().toLowerCase();
		const response = await frappe.call({
			method: "gris.api.gestao_adultos.listar_entrevistas",
			args: {},
		});
		const rows = response.message || [];
		if (!termo) {
			renderLista(rows);
			return;
		}

		const filtered = rows.filter((row) => {
			const associadoNome = String(row.associado_nome || "").toLowerCase();
			const associadoCodigo = String(row.associado || "").toLowerCase();
			return associadoNome.includes(termo) || associadoCodigo.includes(termo);
		});

		renderLista(filtered);
	}

	async function abrirOuCriarEntrevista() {
		const associado = selectNovoAssociado.value;
		if (!associado) {
			frappe.msgprint("Selecione um associado para continuar.");
			return;
		}

		const response = await frappe.call({
			method: "gris.api.gestao_adultos.obter_ou_criar_entrevista",
			args: { associado },
		});
		const data = response.message || {};
		if (data.name) {
			window.location.href = `/gestao_adultos/respostas_entrevista?name=${encodeURIComponent(data.name)}`;
		}
	}

	btnFiltrar?.addEventListener("click", carregarEntrevistas);
	btnNova?.addEventListener("click", openModal);
	btnFecharModal?.addEventListener("click", closeModal);
	btnCancelarModal?.addEventListener("click", closeModal);
	backdrop?.addEventListener("click", closeModal);
	btnConfirmarModal?.addEventListener("click", abrirOuCriarEntrevista);

	carregarAssociados().then(carregarEntrevistas).catch((error) => {
		console.error(error);
		frappe.msgprint("Não foi possível carregar a página de entrevistas.");
	});
});
