// Respostas da Pesquisa de Novos Associados
// Charts via Apache ECharts; modais via <dialog> do design system Basecoat.

(function () {
	const CHART_COLORS = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9", "#CC79A7"];

	const ensureEcharts = () =>
		new Promise((resolve, reject) => {
			if (window.echarts) {
				resolve();
				return;
			}
			const existing = document.querySelector('script[data-gris-echarts="1"]');
			if (existing) {
				existing.addEventListener(
					"load",
					() =>
						window.echarts ? resolve() : reject(new Error("ECharts não disponível")),
					{ once: true }
				);
				existing.addEventListener(
					"error",
					() => reject(new Error("Falha ao carregar ECharts")),
					{
						once: true,
					}
				);
				return;
			}
			const script = document.createElement("script");
			script.dataset.grisEcharts = "1";
			script.src = "/assets/gris/vendor/echarts/echarts.min.js";
			script.onload = () =>
				window.echarts ? resolve() : reject(new Error("ECharts não disponível"));
			script.onerror = () => reject(new Error("Falha ao carregar ECharts"));
			document.head.appendChild(script);
		});

	const escapeHtml = (value) => frappe.utils.escape_html(value == null ? "" : String(value));

	const npsClass = (score) => {
		const n = parseInt(score, 10);
		if (Number.isNaN(n)) return "survey-nps--neutral";
		if (n >= 9) return "survey-nps--promoter";
		if (n >= 7) return "survey-nps--neutral";
		return "survey-nps--detractor";
	};

	frappe.ready(() => {
		const tableEl = document.getElementById("surveyTable");
		const tbody = tableEl?.querySelector("tbody");
		const searchInput = document.getElementById("f-search");
		const periodTabs = document.querySelector("[data-period-tabs]");
		const chartEmpty = document.getElementById("nps-chart-empty");
		const chartEl = document.getElementById("nps-chart");
		const detailDialog = document.getElementById("surveyDetailDialog");
		const detailBody = document.getElementById("survey-detail-body");

		if (!tbody) return;

		const COLSPAN = 4;
		let allSurveys = [];
		let chart = null;
		let currentPeriod = "monthly";

		function renderLoading() {
			tbody.innerHTML = `
        <tr>
          <td colspan="${COLSPAN}">
            <div class="survey-loading">
              <span class="spinner" role="status" aria-label="Carregando"></span>
              <span>Carregando respostas…</span>
            </div>
          </td>
        </tr>`;
		}

		function renderEmpty(title, description) {
			tbody.innerHTML = `
        <tr>
          <td colspan="${COLSPAN}">
            <section class="empty">
              <h2>${escapeHtml(title)}</h2>
              <p>${escapeHtml(description)}</p>
            </section>
          </td>
        </tr>`;
		}

		function renderRows(rows) {
			if (!rows.length) {
				renderEmpty(
					"Nenhuma resposta encontrada",
					"Tente ajustar a busca ou aguarde novas respostas."
				);
				return;
			}
			tbody.innerHTML = rows
				.map((row) => {
					const responsavel = escapeHtml(
						row.responsavel_nome || row.responsavel || "Desistência"
					);
					const date = escapeHtml(row.creation_formatted || "");
					const score = escapeHtml(row.nps_recepcao);
					const cls = npsClass(row.nps_recepcao);
					const id = encodeURIComponent(row.name);
					return `
            <tr class="survey-table-row" data-name="${id}">
              <td><span class="survey-table-row__name">${responsavel}</span></td>
              <td><span class="survey-table-row__date">${date}</span></td>
              <td><span class="survey-nps ${cls}">${score}</span></td>
              <td class="survey-table-row__actions">
                <button type="button" class="btn-sm-outline" data-action="details" data-name="${id}">
                  Ver detalhes
                </button>
              </td>
            </tr>`;
				})
				.join("");
		}

		function applySearch(term) {
			const q = (term || "").trim().toLowerCase();
			if (!q) {
				renderRows(allSurveys);
				return;
			}
			const filtered = allSurveys.filter((row) => {
				const target = (row.responsavel_nome || row.responsavel || "").toLowerCase();
				return target.includes(q);
			});
			renderRows(filtered);
		}

		function loadSurveys() {
			renderLoading();
			frappe.call({
				method: "gris.www.recepcao.pesquisa_novos_respostas.get_surveys",
				callback: (r) => {
					allSurveys = Array.isArray(r.message) ? r.message : [];
					applySearch(searchInput?.value);
				},
			});
		}

		// ---- Gráfico (ECharts) ------------------------------------------------
		function setEmptyChart(isEmpty) {
			if (!chartEmpty || !chartEl) return;
			chartEmpty.hidden = !isEmpty;
			chartEl.style.visibility = isEmpty ? "hidden" : "visible";
		}

		function readToken(name, fallback) {
			const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
			return value || fallback;
		}

		function buildChartOption(data) {
			const labels = data.labels || [];
			const values = (data.datasets && data.datasets[0] && data.datasets[0].values) || [];
			const mutedFg = readToken("--muted-foreground", "#64748b");
			const borderColor = readToken("--border", "#e2e8f0");
			return {
				color: CHART_COLORS,
				aria: { enabled: true },
				grid: { left: 40, right: 20, top: 24, bottom: 36, containLabel: true },
				tooltip: {
					trigger: "axis",
					axisPointer: { type: "line" },
					formatter: (params) => {
						const item = Array.isArray(params) ? params[0] : params;
						const v = typeof item.value === "number" ? item.value : 0;
						return `<strong>${escapeHtml(item.name)}</strong><br/>NPS: ${v
							.toFixed(1)
							.replace(".", ",")}`;
					},
				},
				legend: { show: false },
				xAxis: {
					type: "category",
					data: labels,
					boundaryGap: false,
					axisLabel: { color: mutedFg, fontSize: 11 },
					axisLine: { lineStyle: { color: borderColor } },
				},
				yAxis: {
					type: "value",
					name: "NPS",
					min: -100,
					max: 100,
					axisLabel: { color: mutedFg, fontSize: 11 },
					splitLine: { lineStyle: { color: borderColor } },
				},
				series: [
					{
						name: "NPS",
						type: "line",
						smooth: true,
						symbol: "circle",
						symbolSize: 8,
						lineStyle: { width: 2, type: "solid" },
						itemStyle: { borderWidth: 2, borderColor: "#fff" },
						areaStyle: {
							color: {
								type: "linear",
								x: 0,
								y: 0,
								x2: 0,
								y2: 1,
								colorStops: [
									{ offset: 0, color: "rgba(0, 114, 178, 0.28)" },
									{ offset: 1, color: "rgba(0, 114, 178, 0.02)" },
								],
							},
						},
						data: values,
					},
				],
			};
		}

		async function renderChart(data) {
			try {
				await ensureEcharts();
			} catch (err) {
				console.warn(err);
				return;
			}
			if (!data || !data.labels || data.labels.length === 0) {
				setEmptyChart(true);
				if (chart) chart.clear();
				return;
			}
			setEmptyChart(false);
			if (!chart) {
				chart = window.echarts.init(chartEl);
				window.addEventListener("resize", () => chart && chart.resize());
			}
			chart.setOption(buildChartOption(data), true);
		}

		function loadChart() {
			frappe.call({
				method: "gris.www.recepcao.pesquisa_novos_respostas.get_nps_chart_data",
				args: { period: currentPeriod },
				callback: (r) => renderChart(r.message),
			});
		}

		// ---- Tabs Mensal/Semanal ---------------------------------------------
		if (periodTabs) {
			periodTabs.addEventListener("click", (event) => {
				const btn = event.target.closest(".survey-period__btn");
				if (!btn) return;
				const period = btn.dataset.period;
				if (!period || period === currentPeriod) return;
				currentPeriod = period;
				periodTabs.querySelectorAll(".survey-period__btn").forEach((b) => {
					b.setAttribute("aria-selected", b === btn ? "true" : "false");
				});
				loadChart();
			});
		}

		// ---- Busca ------------------------------------------------------------
		if (searchInput) {
			searchInput.addEventListener("input", (event) => applySearch(event.target.value));
		}

		// ---- Modal de detalhes ------------------------------------------------
		function renderDetailLoading() {
			detailBody.innerHTML = `
        <div class="survey-detail__loading">
          <span class="spinner" role="status" aria-label="Carregando"></span>
          <span>Carregando detalhes…</span>
        </div>`;
		}

		function renderDetail(data) {
			const s = data.survey || {};
			const beneficiarios = Array.isArray(data.beneficiarios) ? data.beneficiarios : [];

			const beneficiariosHtml = beneficiarios.length
				? `<ul class="survey-detail__beneficiarios">
            ${beneficiarios
				.map(
					(b) => `
                <li class="survey-detail__beneficiario">
                  <span>${escapeHtml(b.nome_completo)}</span>
                  <span class="badge-outline">${escapeHtml(b.tipo)}</span>
                </li>`
				)
				.join("")}
          </ul>`
				: '<p class="text-muted-foreground">Nenhum beneficiário vinculado.</p>';

			const answer = (label, value, opts = {}) => {
				const v = (value || "").toString().trim() || "—";
				const fullClass = opts.full ? " survey-detail__answers--full" : "";
				return `
          <div class="survey-detail__section${fullClass}">
            <p class="survey-detail__label">${escapeHtml(label)}</p>
            <p class="survey-detail__value">${escapeHtml(v)}</p>
          </div>`;
			};

			const npsCls = npsClass(s.nps_recepcao);

			detailBody.innerHTML = `
        <div class="survey-detail__section">
          <p class="survey-detail__label">Responsável</p>
          <p class="survey-detail__value survey-detail__value--strong">
            ${escapeHtml(s.responsavel_nome || s.responsavel || "Desistência")}
          </p>
        </div>

        <div class="survey-detail__section">
          <p class="survey-detail__label">Beneficiários vinculados</p>
          ${beneficiariosHtml}
        </div>

        <hr class="survey-detail__divider" />

        <div class="survey-detail__answers">
          ${answer("Como conheceu o Movimento?", s.como_conheceu_movimento)}
          ${answer("Como conheceu o Grupo?", s.como_você_conheceu_o_nosso_grupo_escoteiro)}
          ${answer("Visão sobre o Movimento", s.visao_sobre_movimento, { full: true })}
          ${answer("O que espera encontrar", s.espera_encontrar_movimento, { full: true })}
          ${answer("O que chamou atenção", s.chamou_atencao_uel, { full: true })}
          <div class="survey-detail__section">
            <p class="survey-detail__label">NPS Recepção</p>
            <span class="survey-nps ${npsCls}">${escapeHtml(s.nps_recepcao)}</span>
          </div>
          <div class="survey-detail__section"></div>
          ${answer("Pontos fortes", s.pontos_fortes_recepcao, { full: true })}
          ${answer("Pontos a melhorar", s.pontos_melhorar_recepcao, { full: true })}
        </div>
      `;
		}

		function openDetails(name) {
			if (!detailDialog || !detailBody) return;
			renderDetailLoading();
			detailDialog.showModal();
			frappe.call({
				method: "gris.www.recepcao.pesquisa_novos_respostas.get_survey_details",
				args: { survey_name: name },
				callback: (r) => {
					if (r.message) renderDetail(r.message);
				},
			});
		}

		tbody.addEventListener("click", (event) => {
			const btn = event.target.closest('button[data-action="details"]');
			if (!btn) return;
			const name = decodeURIComponent(btn.dataset.name || "");
			if (name) openDetails(name);
		});

		if (detailDialog) {
			detailDialog.querySelectorAll("[data-dialog-close]").forEach((btn) => {
				btn.addEventListener("click", () => detailDialog.close());
			});
		}

		// ---- Init -------------------------------------------------------------
		loadSurveys();
		loadChart();
	});
})();
