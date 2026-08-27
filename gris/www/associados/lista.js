// JS específico da página Lista de Associados (auto-carregado pelo Frappe quando está ao lado do .html)

frappe.ready(() => {
	const tableEl = document.getElementById("associadosTable");
	const listEl = tableEl?.querySelector("tbody");
	const form = document.getElementById("assoc-filters");
	const resetBtn = document.getElementById("btn-reset");
	const createUsersBtn = document.getElementById("btn-create-users");
	const confirmDlg = document.getElementById("modalCreateUsersConfirm");
	const resultDlg = document.getElementById("modalCreateUsersResult");
	const confirmCreateUsersBtn = document.getElementById("btn-confirm-create-users");
	const resultBody = document.getElementById("create-users-result-body");

	if (!listEl || !form) return;

	// ── Column definitions ──────────────────────────────────────────────────────
	const COLUMNS = [
		{ key: "status", label: "Status", field: "status", always: true },
		{ key: "nome_completo", label: "Nome", field: "nome_completo", always: true },
		{ key: "registro", label: "Nº Registro", field: "registro" },
		{ key: "categoria", label: "Categoria", field: "categoria" },
		{ key: "ramo", label: "Ramo", field: "ramo" },
		{ key: "secao", label: "Seção", field: "secao" },
		{ key: "funcao", label: "Função", field: "funcao" },
		{ key: "area", label: "Área", field: "area" },
		{ key: "validade_registro", label: "Validade do Registro", field: "validade_registro" },
		{ key: "dias_restantes", label: "Dias Restantes", field: null },
	];

	const STORAGE_KEY = "gris_assoc_lista_col_vis_v1";

	// ── Column visibility ───────────────────────────────────────────────────────
	function loadColVisibility() {
		const defaults = Object.fromEntries(COLUMNS.map((c) => [c.key, true]));
		try {
			const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
			if (saved && typeof saved === "object") {
				// ensure always-on columns are never stored as hidden
				COLUMNS.filter((c) => c.always).forEach((c) => {
					saved[c.key] = true;
				});
				return { ...defaults, ...saved };
			}
		} catch (_) {
			/* ignore */
		}
		return defaults;
	}

	function saveColVisibility(vis) {
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(vis));
		} catch (_) {
			/* ignore */
		}
	}

	let colVisible = loadColVisibility();

	function getColspan() {
		return COLUMNS.filter((c) => colVisible[c.key]).length;
	}

	function applyThVisibility() {
		const ths = tableEl.querySelectorAll("thead th");
		COLUMNS.forEach((col, idx) => {
			if (ths[idx]) ths[idx].style.display = colVisible[col.key] ? "" : "none";
		});
	}

	// ── Helpers ─────────────────────────────────────────────────────────────────
	function formatDate(dateStr) {
		if (!dateStr) return null;
		const d = new Date(dateStr + "T00:00:00");
		if (isNaN(d)) return null;
		return d.toLocaleDateString("pt-BR");
	}

	function daysUntil(dateStr) {
		if (!dateStr) return null;
		const today = new Date();
		today.setHours(0, 0, 0, 0);
		const exp = new Date(dateStr + "T00:00:00");
		if (isNaN(exp)) return null;
		return Math.round((exp - today) / 86400000);
	}

	function renderDiasRestantes(dateStr) {
		const days = daysUntil(dateStr);
		if (days === null) return '<span class="text-muted-foreground">—</span>';
		if (days > 30) return `<span class="dias-ok">${days} dias</span>`;
		if (days > 0) return `<span class="dias-warn">${days} dias</span>`;
		if (days === 0) return '<span class="dias-danger">Vence hoje</span>';
		return `<span class="dias-danger">Vencido há ${Math.abs(days)} dias</span>`;
	}

	// ── Render helpers ──────────────────────────────────────────────────────────
	function renderLoading() {
		listEl.innerHTML = `
      <tr>
        <td colspan="${getColspan()}">
          <div class="assoc-loading">
            <span class="spinner" role="status" aria-label="Carregando"></span>
            <span>Carregando associados…</span>
          </div>
        </td>
      </tr>`;
	}

	function renderEmpty(title, description) {
		listEl.innerHTML = `
      <tr>
        <td colspan="${getColspan()}">
          <section class="empty">
            <div class="empty-media">
              <img src="/assets/gris/images/gris-character/gris-search.png" alt="" class="empty-image empty-image--md" loading="lazy" decoding="async" />
            </div>
            <h2>${frappe.utils.escape_html(title)}</h2>
            <p>${frappe.utils.escape_html(description)}</p>
          </section>
        </td>
      </tr>`;
	}

	function statusDot(status) {
		if (status === "Válido") {
			return '<span class="assoc-status-dot assoc-status-dot--ok" aria-label="Registro válido" title="Registro válido"></span>';
		}
		if (status === "Vencido") {
			return '<span class="assoc-status-dot assoc-status-dot--danger" aria-label="Registro vencido" title="Registro vencido"></span>';
		}
		return '<span class="assoc-status-dot assoc-status-dot--warn" aria-label="Atenção necessária" title="Atenção necessária"></span>';
	}

	function badge(text, variant) {
		if (!text) return '<span class="text-muted-foreground">—</span>';
		const cls = variant === "outline" ? "badge-outline" : `badge-${variant}`;
		return `<span class="${cls}">${frappe.utils.escape_html(text)}</span>`;
	}

	let lastRows = [];

	function render(rows) {
		lastRows = rows;
		if (!rows.length) {
			renderEmpty("Nenhum associado encontrado", "Tente ajustar os filtros acima.");
			return;
		}

		const v = colVisible;

		listEl.innerHTML = rows
			.map((row) => {
				const nome = frappe.utils.escape_html(row.nome_completo || row.name || "—");
				const registro = frappe.utils.escape_html(row.registro || "—");
				const status = row.status || "Desconhecido";
				const ramo = row.ramo && row.ramo !== "Não se aplica" ? row.ramo : "";
				const link = `/associados/detalhe?name=${encodeURIComponent(row.name)}`;

				return `
        <tr class="assoc-table-row" data-href="${link}">
          ${v.status ? `<td class="assoc-status-cell">${statusDot(status)}</td>` : ""}
          ${v.nome_completo ? `<td><span class="assoc-name">${nome}</span></td>` : ""}
          ${v.registro ? `<td><span class="text-muted-foreground">${registro}</span></td>` : ""}
          ${v.categoria ? `<td>${badge(row.categoria, "primary")}</td>` : ""}
          ${v.ramo ? `<td>${badge(ramo, "secondary")}</td>` : ""}
          ${v.secao ? `<td>${badge(row.secao, "outline")}</td>` : ""}
          ${v.funcao ? `<td>${badge(row.funcao, "outline")}</td>` : ""}
          ${v.area ? `<td>${badge(row.area, "outline")}</td>` : ""}
          ${
				v.validade_registro
					? `<td><span class="text-muted-foreground">${
							formatDate(row.validade_registro) || "—"
					  }</span></td>`
					: ""
			}
          ${v.dias_restantes ? `<td>${renderDiasRestantes(row.validade_registro)}</td>` : ""}
        </tr>`;
			})
			.join("");
	}

	function getFormFilters() {
		const fd = new FormData(form);
		const get = (k) => (fd.get(k) || "").trim();
		return {
			nome: get("nome"),
			categoria: get("categoria"),
			ramo: get("ramo"),
			secao: get("secao"),
			funcao: get("funcao"),
			area: get("area"),
			status: get("status"),
			status_no_grupo: get("status_no_grupo"),
		};
	}

	async function fetchList() {
		renderLoading();
		const f = getFormFilters();
		const filters = [];
		if (f.status_no_grupo)
			filters.push(["Associado", "status_no_grupo", "=", f.status_no_grupo]);
		if (f.nome) filters.push(["Associado", "nome_completo", "like", `%${f.nome}%`]);
		if (f.categoria) filters.push(["Associado", "categoria", "=", f.categoria]);
		if (f.funcao) filters.push(["Associado", "funcao", "=", f.funcao]);
		if (f.area) filters.push(["Associado", "area", "=", f.area]);
		if (f.secao) filters.push(["Associado", "secao", "=", f.secao]);
		if (f.ramo) filters.push(["Associado", "ramo", "=", f.ramo]);
		if (f.status) filters.push(["Associado", "status", "=", f.status]);

		try {
			const r = await frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Associado",
					fields: [
						"name",
						"nome_completo",
						"registro",
						"status",
						"ramo",
						"categoria",
						"funcao",
						"area",
						"secao",
						"validade_registro",
					],
					filters,
					limit_page_length: 500,
					order_by: "nome_completo asc",
				},
			});
			render(r.message || []);
		} catch (e) {
			console.warn("Erro ao carregar lista de associados", e);
			renderEmpty("Erro ao carregar a lista", "Tente recarregar a página.");
		}
	}

	function resetSelectsToDefault() {
		form.querySelectorAll(".select").forEach((el) => {
			el.value = el.id === "f-status-grupo" ? "Ativo" : "";
		});
	}

	// Listener delegado para navegação ao detalhe
	listEl.addEventListener("click", (e) => {
		const tr = e.target.closest("tr[data-href]");
		if (tr) window.location.href = tr.dataset.href;
	});

	form.addEventListener("submit", (e) => {
		e.preventDefault();
		fetchList();
	});

	form.addEventListener("reset", () => {
		setTimeout(() => {
			resetSelectsToDefault();
			fetchList();
		}, 0);
	});

	if (createUsersBtn && confirmDlg && resultDlg) {
		createUsersBtn.addEventListener("click", () => confirmDlg.showModal());

		confirmDlg.querySelectorAll("[data-dialog-close]").forEach((btn) => {
			btn.addEventListener("click", () => confirmDlg.close());
		});
		resultDlg.querySelectorAll("[data-dialog-close]").forEach((btn) => {
			btn.addEventListener("click", () => resultDlg.close());
		});

		if (confirmCreateUsersBtn) {
			confirmCreateUsersBtn.addEventListener("click", async () => {
				const originalConfirmText = confirmCreateUsersBtn.textContent;
				const originalButtonText = createUsersBtn.textContent;

				confirmCreateUsersBtn.disabled = true;
				confirmCreateUsersBtn.textContent = "Processando…";
				createUsersBtn.disabled = true;
				createUsersBtn.textContent = "Processando…";

				try {
					const response = await frappe.call({
						method: "gris.api.users.user_manager.create_missing_associate_users",
					});
					confirmDlg.close();
					renderResult(response.message || {});
					fetchList();
				} catch (error) {
					console.warn("Erro ao criar usuários pendentes", error);
					confirmDlg.close();
					renderResult({}, true);
				} finally {
					confirmCreateUsersBtn.disabled = false;
					confirmCreateUsersBtn.textContent = originalConfirmText;
					createUsersBtn.disabled = false;
					createUsersBtn.textContent = originalButtonText;
				}
			});
		}
	}

	function renderResult(result, failed = false) {
		if (!resultBody || !resultDlg) return;
		const titleEl = resultDlg.querySelector("h2");
		if (titleEl)
			titleEl.textContent = failed
				? "Erro ao criar usuários"
				: "Criação de usuários concluída";

		if (failed) {
			resultBody.innerHTML =
				'<p class="text-muted-foreground">Não foi possível concluir a criação dos usuários pendentes.</p>';
			resultDlg.showModal();
			return;
		}

		const item = (label, value) => `
      <div class="result-row">
        <span class="result-row__label">${label}</span>
        <span class="result-row__value">${value || 0}</span>
      </div>`;

		resultBody.innerHTML = `
      <div class="result-list">
        ${item("Associados analisados", result.total_associates)}
        ${item("Criados", result.created)}
        ${item("Ignorados (usuário já existe)", result.skipped_existing_user)}
        ${item("Ignorados (status inválido)", result.skipped_invalid_status)}
        ${item("Ignorados (domínio inválido)", result.skipped_invalid_domain)}
        ${item("Ignorados (dados incompletos)", result.skipped_missing_data)}
        ${item("Erros", result.errors)}
      </div>`;
		resultDlg.showModal();
	}

	// ── Column toggle wiring ────────────────────────────────────────────────────
	function initColToggles() {
		const checkboxes = document.querySelectorAll("[data-col-toggle]");
		checkboxes.forEach((cb) => {
			const key = cb.dataset.colToggle;
			cb.checked = colVisible[key] !== false;
			cb.addEventListener("change", () => {
				colVisible[key] = cb.checked;
				saveColVisibility(colVisible);
				applyThVisibility();
				render(lastRows);
			});
		});
	}

	applyThVisibility();
	initColToggles();
	fetchList();
});
