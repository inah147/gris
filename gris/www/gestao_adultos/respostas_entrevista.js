frappe.ready(() => {
	(async function () {
	const entrevistaName = new URLSearchParams(window.location.search).get("name") || "";
	const btnSalvar = document.getElementById("btn-salvar");
	const btnEditar = document.getElementById("btn-editar");
	const btnCancelar = document.getElementById("btn-cancelar");
	const associadoContainer = document.getElementById("associado-container");
	const dadosIniciaisContainer = document.getElementById("dados-iniciais-container");
	const secoesContainer = document.getElementById("secoes-perguntas");
	const resultadoLeitura = document.getElementById("resultado-leitura");
	const listaAlertas = document.getElementById("lista-alertas");
	const campoResumo = document.getElementById("campo-resumo");
	const modalAlerta = document.getElementById("modal-alerta");
	const modalAlertaBackdrop = document.getElementById("modal-alerta-backdrop");
	const modalAlertaMensagem = document.getElementById("modal-alerta-mensagem");
	const btnOkModalAlerta = document.getElementById("ok-modal-alerta");
	const modalObservacao = document.getElementById("modal-observacao");
	const modalObservacaoBackdrop = document.getElementById("modal-observacao-backdrop");
	const modalObservacaoPergunta = document.getElementById("modal-observacao-pergunta");
	const modalObservacaoMensagem = document.getElementById("modal-observacao-mensagem");
	const btnOkModalObservacao = document.getElementById("ok-modal-observacao");

	document.body.classList.remove("modal-open");

	if (!entrevistaName) {
		frappe.msgprint("Entrevista não informada.");
		window.location.href = "/gestao_adultos/entrevista_competencias";
		return;
	}

	let config = null;
	let entrevista = null;
	let editMode = false;
	let chart = null;
	let chartEngine = "echarts";
	let resizeHandlerBound = false;
	let alertSelectionKeys = new Set();
	let alertReasonBySelectionKey = new Map();

	const ALERT_CATEGORY_DEFINITIONS = [
		{ key: "alerta_geral", label: "Alerta Geral" },
		{ key: "pontuacao_dirigente_administrativo_financeiro", label: "Dirigente Adm. Financeiro" },
		{ key: "pontuacao_dirigente_gestao_institucional", label: "Dir. Gestão Institucional" },
		{ key: "pontuacao_dirigente_metodos_educativos", label: "Dir. Métodos Educativos" },
		{ key: "pontuacao_ramo_lobinho", label: "Lobinho" },
		{ key: "pontuacao_ramo_escoteiro", label: "Escoteiro" },
		{ key: "pontuacao_ramo_senior", label: "Sênior" },
		{ key: "pontuacao_ramo_pioneiro", label: "Pioneiro" },
	];

	const INFO_ICON_SVG =
		'<svg class="question-item__icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false"><circle cx="10" cy="10" r="8" /><line x1="10" y1="8" x2="10" y2="13" /><circle cx="10" cy="6" r="0.8" fill="currentColor" stroke="none" /></svg>';
	const ALERT_ICON_SVG =
		'<svg class="question-item__icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false"><path d="M10 2.6 L18 16.5 H2 Z" /><line x1="10" y1="7" x2="10" y2="11.5" /><circle cx="10" cy="14" r="0.9" fill="currentColor" stroke="none" /></svg>';

	function normalizeText(value) {
		return String(value || "")
			.trim()
			.toLowerCase()
			.replace(/\s+/g, " ");
	}

	function buildAlertKey(question, answer) {
		return `${normalizeText(question)}::${normalizeText(answer)}`;
	}

	function buildAlertSelectionKeys() {
		const keys = new Set();
		const reasonMap = new Map();

		(config.alert_rules || []).forEach((alertRule) => {
			const key = buildAlertKey(alertRule.pergunta, alertRule.resposta);
			if (key !== "::") {
				keys.add(key);
				const reason = String(alertRule.motivo_do_alerta || "").trim();
				if (reason) {
					const currentReasons = reasonMap.get(key) || [];
					if (!currentReasons.includes(reason)) {
						currentReasons.push(reason);
						reasonMap.set(key, currentReasons);
					}
				}
			}
		});

		(entrevista.alertas || []).forEach((alerta) => {
			const key = buildAlertKey(alerta.pergunta, alerta.resposta);
			if (key !== "::") {
				keys.add(key);
				const reason = String(alerta.motivo_do_alerta || "").trim();
				if (reason) {
					const currentReasons = reasonMap.get(key) || [];
					if (!currentReasons.includes(reason)) {
						currentReasons.push(reason);
						reasonMap.set(key, currentReasons);
					}
				}
			}
		});
		alertSelectionKeys = keys;
		alertReasonBySelectionKey = new Map(
			Array.from(reasonMap.entries()).map(([key, reasons]) => [key, reasons.join("\n\n")])
		);
	}

	function updateQuestionAlertIndicators() {
		config.sections.forEach((section) => {
			section.fields.forEach((field) => {
				const select = document.getElementById(field.fieldname);
				const indicator = document.getElementById(`alert-indicator-${field.fieldname}`);
				if (!select || !indicator) {
					return;
				}

				const key = buildAlertKey(field.label, select.value);
				const hasAlert = alertSelectionKeys.has(key);
				indicator.classList.toggle("is-visible", hasAlert);
				indicator.disabled = !hasAlert;
				indicator.setAttribute("title", hasAlert ? "Ver motivo do alerta" : "Resposta sem alerta");
				indicator.setAttribute("aria-label", hasAlert ? "Ver motivo do alerta" : "Resposta sem alerta");
				const questionCard = select.closest(".question-item");
				if (questionCard) {
					questionCard.classList.toggle("question-item--has-alert", hasAlert);
				}
			});
		});
	}

	function openAlertReasonModal(message) {
		if (!modalAlerta || !modalAlertaBackdrop || !modalAlertaMensagem) {
			return;
		}

		modalAlertaMensagem.innerHTML = frappe.utils.escape_html(message || "Motivo do alerta não informado.").replace(/\n/g, "<br>");
		modalAlertaBackdrop.style.display = "block";
		modalAlerta.style.display = "flex";
		document.body.classList.add("modal-open");
	}

	function closeAlertReasonModal() {
		if (!modalAlerta || !modalAlertaBackdrop) {
			return;
		}

		modalAlerta.style.display = "none";
		modalAlertaBackdrop.style.display = "none";
		if (modalObservacao?.style.display !== "flex") {
			document.body.classList.remove("modal-open");
		}
	}

	function openObservationModal(question, message) {
		if (!modalObservacao || !modalObservacaoBackdrop || !modalObservacaoMensagem || !modalObservacaoPergunta) {
			return;
		}

		modalObservacaoPergunta.textContent = question || "Pergunta";
		modalObservacaoMensagem.innerHTML = frappe.utils.escape_html(message || "Sem observações para esta resposta.").replace(/\n/g, "<br>");
		modalObservacaoBackdrop.style.display = "block";
		modalObservacao.style.display = "flex";
		document.body.classList.add("modal-open");
	}

	function closeObservationModal() {
		if (!modalObservacao || !modalObservacaoBackdrop) {
			return;
		}

		modalObservacao.style.display = "none";
		modalObservacaoBackdrop.style.display = "none";
		if (modalAlerta?.style.display !== "flex") {
			document.body.classList.remove("modal-open");
		}
	}

	const ensureCharts = () =>
		new Promise((resolve, reject) => {
			if (window.frappe && frappe.Chart) {
				resolve();
				return;
			}

			const script = document.createElement("script");
			script.src = "/assets/frappe/node_modules/frappe-charts/dist/frappe-charts.umd.js";
			script.onload = () => {
				try {
					const namespace = window["frappe-charts"];
					if (namespace && namespace.Chart) {
						frappe.Chart = namespace.Chart;
					}
				} catch (error) {
					console.warn(error);
				}

				if (frappe.Chart) {
					resolve();
				} else {
					reject(new Error("frappe.Chart não disponível"));
				}
			};
			script.onerror = () => reject(new Error("Falha ao carregar gráfico"));
			document.head.appendChild(script);
		});

	const ensureEcharts = () =>
		new Promise((resolve, reject) => {
			if (window.echarts) {
				resolve();
				return;
			}

			const existing = document.querySelector('script[data-gris-echarts="1"]');
			if (existing) {
				existing.addEventListener("load", () => (window.echarts ? resolve() : reject(new Error("ECharts não disponível"))), { once: true });
				existing.addEventListener("error", () => reject(new Error("Falha ao carregar ECharts")), { once: true });
				return;
			}

			const script = document.createElement("script");
			script.dataset.grisEcharts = "1";
			script.src = "/assets/gris/vendor/echarts/echarts.min.js";
			script.onload = () => {
				if (window.echarts) {
					resolve();
				} else {
					reject(new Error("ECharts não disponível"));
				}
			};
			script.onerror = () => reject(new Error("Falha ao carregar ECharts"));
			document.head.appendChild(script);
		});

	function destroyCurrentChart() {
		if (!chart) {
			return;
		}

		try {
			if (chartEngine === "echarts" && typeof chart.dispose === "function") {
				chart.dispose();
			}
		} catch (error) {
			console.warn(error);
		}

		chart = null;
	}

	function bindChartResize() {
		if (resizeHandlerBound) {
			return;
		}

		window.addEventListener("resize", () => {
			if (chartEngine === "echarts" && chart && typeof chart.resize === "function") {
				chart.resize();
			}
		});

		resizeHandlerBound = true;
	}

	function renderDadosIniciais() {
		dadosIniciaisContainer.innerHTML = `
			<h3 class="card-modern__title mb-3">Dados iniciais</h3>
			<div class="row g-3">
				<div class="col-12 col-md-6">
					<label class="form-label-modern">Motivo da entrevista</label>
					<select class="form-input-modern" id="motivo_da_entrevista"></select>
				</div>
				<div class="col-12 col-md-6">
					<label class="form-label-modern">Função atual</label>
					<input type="text" class="form-input-modern" id="funcao_atual" />
				</div>
				<div class="col-12 col-md-6">
					<label class="form-label-modern">Profissão</label>
					<input type="text" class="form-input-modern" id="profissao" />
				</div>
				<div class="col-12 col-md-6">
					<label class="form-label-modern">Formação</label>
					<input type="text" class="form-input-modern" id="formacao" />
				</div>
				<div class="col-12 col-md-6">
					<label class="form-label-modern">Hobbies e interesses</label>
					<input type="text" class="form-input-modern" id="hobbies_e_interesses" />
				</div>
				<div class="col-12">
					<label class="form-label-modern">Observações gerais</label>
					<textarea class="form-input-modern" rows="3" id="observacoes"></textarea>
				</div>
			</div>
		`;

		const motivoSelect = document.getElementById("motivo_da_entrevista");
		motivoSelect.innerHTML = ["<option value=''>Selecione</option>"]
			.concat(config.motivos_entrevista.map((item) => `<option value="${frappe.utils.escape_html(item)}">${frappe.utils.escape_html(item)}</option>`))
			.join("");

		["motivo_da_entrevista", "funcao_atual", "profissao", "formacao", "hobbies_e_interesses", "observacoes"].forEach(
			(field) => {
				const el = document.getElementById(field);
				if (el) {
					el.value = entrevista[field] || "";
				}
			}
		);
	}

	function renderAssociado() {
		const associadoDisplay = entrevista.associado_nome || entrevista.associado || "Não informado";
		if (!associadoContainer) {
			return;
		}

		associadoContainer.innerHTML = `
			<h3 class="card-modern__title mb-2">Associado</h3>
			<p class="mb-0">${frappe.utils.escape_html(associadoDisplay)}</p>
		`;
	}

	function renderSections() {
		secoesContainer.innerHTML = config.sections
			.map(
				(section) => `
					<div class="card-modern mb-4">
						<div class="card-modern__header">
							<h3 class="card-modern__title">${frappe.utils.escape_html(section.label)}</h3>
						</div>
						<div class="card-modern__body">
							${section.fields
								.map(
									(field) => `
										<div class="question-item" data-fieldname="${field.fieldname}">
											<div class="question-item__header">
												<label class="form-label-modern mb-0">${frappe.utils.escape_html(field.label)}</label>
												<div class="question-item__actions">
													<button type="button" id="obs-indicator-${field.fieldname}" class="question-item__info" title="Sem observações" aria-label="Sem observações" disabled>${INFO_ICON_SVG}</button>
													<button type="button" id="alert-indicator-${field.fieldname}" class="question-item__alert" title="Resposta sem alerta" aria-label="Resposta sem alerta" disabled>${ALERT_ICON_SVG}</button>
												</div>
											</div>
											<select class="form-input-modern" id="${field.fieldname}">
												<option value="">Selecione</option>
												${(field.options || [])
													.map(
														(option) => `<option value="${frappe.utils.escape_html(option)}">${frappe.utils.escape_html(option)}</option>`
													)
													.join("")}
											</select>
											<div class="question-item__obs">
												<label class="form-label-modern">Observações da resposta</label>
												<textarea class="form-input-modern" rows="2" id="${field.observation_fieldname}"></textarea>
											</div>
										</div>
									`
								)
								.join("")}
						</div>
					</div>
				`
			)
			.join("");

		config.sections.forEach((section) => {
			section.fields.forEach((field) => {
				const select = document.getElementById(field.fieldname);
				const obs = document.getElementById(field.observation_fieldname);
				const indicator = document.getElementById(`alert-indicator-${field.fieldname}`);
				const observationIndicator = document.getElementById(`obs-indicator-${field.fieldname}`);
				if (select) {
					select.value = entrevista[field.fieldname] || "";
					select.addEventListener("change", () => {
						updateQuestionAlertIndicators();
						updateObservationIndicators();
					});
				}

				if (indicator) {
					indicator.addEventListener("click", () => {
						if (!select) {
							return;
						}

						const key = buildAlertKey(field.label, select.value);
						const reason = alertReasonBySelectionKey.get(key) || "Motivo do alerta não informado.";
						openAlertReasonModal(reason);
					});
				}

				if (obs) {
					obs.value = entrevista[field.observation_fieldname] || "";
					obs.addEventListener("input", () => {
						updateObservationIndicators();
					});
				}

				if (observationIndicator) {
					observationIndicator.addEventListener("click", () => {
						if (!obs) {
							return;
						}

						openObservationModal(field.label, obs.value || "Sem observações para esta resposta.");
					});
				}
			});
		});

		updateQuestionAlertIndicators();
		updateObservationIndicators();
	}

	function updateObservationIndicators() {
		config.sections.forEach((section) => {
			section.fields.forEach((field) => {
				const obs = document.getElementById(field.observation_fieldname);
				const indicator = document.getElementById(`obs-indicator-${field.fieldname}`);
				if (!obs || !indicator) {
					return;
				}

				const hasObservation = String(obs.value || "").trim().length > 0;
				indicator.disabled = !hasObservation;
				indicator.classList.toggle("is-visible", !editMode && hasObservation);
				indicator.setAttribute("title", hasObservation ? "Ver observação" : "Sem observações");
				indicator.setAttribute("aria-label", hasObservation ? "Ver observação" : "Sem observações");
			});
		});
	}

	function collectPayload() {
		const payload = {
			motivo_da_entrevista: document.getElementById("motivo_da_entrevista")?.value || "",
			funcao_atual: document.getElementById("funcao_atual")?.value || "",
			profissao: document.getElementById("profissao")?.value || "",
			formacao: document.getElementById("formacao")?.value || "",
			hobbies_e_interesses: document.getElementById("hobbies_e_interesses")?.value || "",
			observacoes: document.getElementById("observacoes")?.value || "",
		};

		config.sections.forEach((section) => {
			section.fields.forEach((field) => {
				payload[field.fieldname] = document.getElementById(field.fieldname)?.value || "";
				payload[field.observation_fieldname] = document.getElementById(field.observation_fieldname)?.value || "";
			});
		});

		return payload;
	}

	function setEditMode(enabled) {
		editMode = enabled;
		document.querySelectorAll("#dados-iniciais-container input, #dados-iniciais-container textarea, #dados-iniciais-container select, #secoes-perguntas textarea, #secoes-perguntas select").forEach((el) => {
			el.disabled = !enabled;
		});

		document.querySelectorAll("#secoes-perguntas .question-item__obs").forEach((el) => {
			el.style.display = enabled ? "block" : "none";
		});

		document.querySelectorAll("#secoes-perguntas .question-item__info").forEach((el) => {
			el.classList.toggle("is-visible", !enabled);
		});

		btnSalvar.style.display = enabled ? "inline-flex" : "none";
		btnEditar.style.display = enabled ? "none" : "inline-flex";
		btnCancelar.style.display = enabled ? "inline-flex" : "none";
		resultadoLeitura.style.display = enabled ? "none" : "block";
		updateObservationIndicators();
	}

	function getChartSeriesData() {
		const target = document.getElementById("grafico-pontuacoes");

		const categoryMetrics = [
			{
				key: "pontuacao_dirigente_administrativo_financeiro",
				label: "Dir. Adm. Financeiro",
				score: Number(entrevista.pontuacao_dirigente_administrativo_financeiro || 0),
			},
			{
				key: "pontuacao_dirigente_gestao_institucional",
				label: "Dir. Gestão Institucional",
				score: Number(entrevista.pontuacao_dirigente_gestao_institucional || 0),
			},
			{
				key: "pontuacao_dirigente_metodos_educativos",
				label: "Dir. Métodos Educativos",
				score: Number(entrevista.pontuacao_dirigente_metodos_educativos || 0),
			},
			{ key: "pontuacao_ramo_lobinho", label: "Ramo Lobinho", score: Number(entrevista.pontuacao_ramo_lobinho || 0) },
			{ key: "pontuacao_ramo_escoteiro", label: "Ramo Escoteiro", score: Number(entrevista.pontuacao_ramo_escoteiro || 0) },
			{ key: "pontuacao_ramo_senior", label: "Ramo Sênior", score: Number(entrevista.pontuacao_ramo_senior || 0) },
			{ key: "pontuacao_ramo_pioneiro", label: "Ramo Pioneiro", score: Number(entrevista.pontuacao_ramo_pioneiro || 0) },
		];

		const alertCountByCategory = categoryMetrics.reduce((acc, category) => {
			acc[category.key] = 0;
			return acc;
		}, {});
		let generalAlertsCount = 0;

		(entrevista.alertas || []).forEach((alerta) => {
			const categoriasOriginais = Array.isArray(alerta.categorias) ? alerta.categorias : [];
			const categorias = categoriasOriginais.includes("alerta_geral") ? ["alerta_geral"] : categoriasOriginais;
			if (categorias.includes("alerta_geral")) {
				generalAlertsCount += 1;
			}
			categorias.forEach((categoria) => {
				if (Object.prototype.hasOwnProperty.call(alertCountByCategory, categoria)) {
					alertCountByCategory[categoria] += 1;
				}
			});
		});

		const sortedMetrics = categoryMetrics
			.map((item) => {
				const alertsByCategory = alertCountByCategory[item.key] || 0;
				return {
					...item,
					alertsByCategory,
					alertsTotal: alertsByCategory + generalAlertsCount,
				};
			})
			.sort((a, b) => b.score - a.score);

		return {
			target,
			labels: sortedMetrics.map((item) => item.label),
			scores: sortedMetrics.map((item) => item.score),
			alertsByCategory: sortedMetrics.map((item) => item.alertsByCategory),
			alertsTotal: sortedMetrics.map((item) => item.alertsTotal),
			generalAlertsCount,
		};
	}

	function renderFrappeChart(target, labels, scores, alertsTotal) {
		target.innerHTML = "";
		chartEngine = "frappe";
		const labelsWithAlerts = labels.map((label, index) => `${label} (${alertsTotal[index] || 0})`);
		chart = new frappe.Chart(target, {
			type: "bar",
			height: 320,
			data: {
				labels: labelsWithAlerts,
				datasets: [{ name: "Pontuação", values: scores }],
			},
			barOptions: { stacked: false, spaceRatio: 0.3 },
		});
	}

	function renderEcharts(target, labels, scores, alertsByCategory, alertsTotal, generalAlertsCount) {
		target.innerHTML = "";
		chartEngine = "echarts";
		chart = window.echarts.init(target);
		const warningColor = getComputedStyle(document.documentElement).getPropertyValue("--color-warning").trim() || "#dfb600";
		const warningLightColor = getComputedStyle(document.documentElement).getPropertyValue("--color-warning-light").trim() || "#fff8dd";
		const roundedTriangleSymbol =
			"path://M0,-100 Q12,-90 24,-78 L82,28 Q92,42 82,56 L20,92 Q0,104 -20,92 L-82,56 Q-92,42 -82,28 L-24,-78 Q-12,-90 0,-100 Z";
		const alertMarkers = alertsTotal
			.map((total, index) => {
				if (!total) {
					return null;
				}

				return {
					name: "Alerta",
					coord: [index, scores[index]],
					value: total,
				};
			})
			.filter(Boolean);
		chart.setOption({
			animation: true,
			grid: { left: 36, right: 20, top: 28, bottom: 90 },
			xAxis: {
				type: "category",
				data: labels,
				axisLabel: { interval: 0, rotate: 35, fontSize: 11 },
			},
			yAxis: {
				type: "value",
				name: "Pontuação",
				minInterval: 1,
			},
			tooltip: {
				trigger: "axis",
				axisPointer: { type: "shadow" },
				formatter(params) {
					const item = Array.isArray(params) ? params[0] : params;
					const index = item?.dataIndex ?? 0;
					const score = scores[index] || 0;
					const total = alertsTotal[index] || 0;
					const byCategory = alertsByCategory[index] || 0;
					return [
						`<strong>${labels[index]}</strong>`,
						`Pontuação: ${score}`,
						`Alertas (total): ${total}`,
						`Alertas da categoria: ${byCategory}`,
						`Alertas gerais: ${generalAlertsCount}`,
					].join("<br/>");
				},
			},
			series: [
				{
					name: "Pontuação",
					type: "bar",
					data: scores,
					itemStyle: { color: "#0d4d91", borderRadius: [4, 4, 0, 0] },
					barMaxWidth: 46,
					markPoint: {
						symbol: roundedTriangleSymbol,
						symbolSize: 30,
						symbolOffset: [0, -22],
						itemStyle: {
							color: warningLightColor,
							borderColor: warningColor,
							borderWidth: 2,
						},
						label: {
							show: true,
							position: "inside",
							align: "center",
							verticalAlign: "middle",
							offset: [0, 2],
							formatter: ({ value }) => `${value}`,
							fontSize: 10,
							fontWeight: 700,
							color: warningColor,
						},
						data: alertMarkers,
					},
				},
			],
		});
		bindChartResize();
	}

	async function renderChart() {
		const { target, labels, scores, alertsByCategory, alertsTotal, generalAlertsCount } = getChartSeriesData();
		if (!target) {
			return;
		}

		destroyCurrentChart();

		try {
			await ensureEcharts();
			renderEcharts(target, labels, scores, alertsByCategory, alertsTotal, generalAlertsCount);
		} catch (error) {
			console.warn("ECharts indisponível, usando Frappe Charts.", error);
			await ensureCharts();
			renderFrappeChart(target, labels, scores, alertsTotal);
		}
	}

	function renderAlertas() {
		const alertas = entrevista.alertas || [];
		if (!alertas.length) {
			listaAlertas.innerHTML = '<p class="text-muted mb-0">Nenhum alerta identificado para as respostas selecionadas.</p>';
			return;
		}

		const groupedByCategory = ALERT_CATEGORY_DEFINITIONS.reduce((acc, category) => {
			acc[category.key] = [];
			return acc;
		}, {});

		alertas.forEach((alerta) => {
			const categoriasOriginais = Array.isArray(alerta.categorias) ? alerta.categorias : [];
			const categorias = categoriasOriginais.includes("alerta_geral")
				? ["alerta_geral"]
				: categoriasOriginais;
			categorias.forEach((categoria) => {
				if (groupedByCategory[categoria]) {
					groupedByCategory[categoria].push(alerta);
				}
			});
		});

		const renderedCategories = ALERT_CATEGORY_DEFINITIONS.filter(
			(category) => (groupedByCategory[category.key] || []).length
		);

		if (!renderedCategories.length) {
			listaAlertas.innerHTML = '<p class="text-muted mb-0">Não foi possível classificar os alertas por categoria.</p>';
			return;
		}

		listaAlertas.innerHTML = `
			<div class="d-grid gap-4">
				${renderedCategories.map((category) => {
					const categoryAlerts = groupedByCategory[category.key] || [];
					return `
						<div class="alert-category">
							<h4 class="alert-category__title">${frappe.utils.escape_html(category.label)}</h4>
							<div class="alert-category__cards">
								${categoryAlerts
									.map(
										(alerta) => `
											<div class="question-item question-item--alert-only">
												<p class="mb-0">${frappe.utils.escape_html(alerta.motivo_do_alerta || "Alerta sem descrição.")}</p>
											</div>
										`
									)
									.join("")}
							</div>
						</div>
					`;
				}).join("")}
			</div>
		`;
	}

	function sanitizeRenderedHtml(html) {
		const container = document.createElement("div");
		container.innerHTML = html || "";

		container
			.querySelectorAll("script, style, iframe, object, embed, link, meta, base, form")
			.forEach((node) => node.remove());

		container.querySelectorAll("*").forEach((node) => {
			Array.from(node.attributes).forEach((attribute) => {
				const name = String(attribute.name || "").toLowerCase();
				const value = String(attribute.value || "").trim().toLowerCase();

				if (name.startsWith("on") || name === "srcdoc") {
					node.removeAttribute(attribute.name);
					return;
				}

				if ((name === "href" || name === "src") && (value.startsWith("javascript:") || value.startsWith("data:text/html"))) {
					node.removeAttribute(attribute.name);
				}
			});
		});

		return container.innerHTML;
	}

	function normalizeResumoMarkdown(texto) {
		return String(texto || "")
			.replace(/\\\*/g, "*")
			.replace(/^\s*\*Recomendação\*\s*:/im, "**Recomendação**:");
	}

	function renderSimpleMarkdown(texto) {
		const escaped = frappe.utils.escape_html(texto || "");
		return escaped
			.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
			.replace(/\*(.+?)\*/g, "<em>$1</em>")
			.replace(/\n/g, "<br>");
	}

	function renderResumoMarkdown(textoResumo) {
		const texto = normalizeResumoMarkdown(textoResumo).trim();
		if (!texto) {
			campoResumo.classList.add("text-muted");
			campoResumo.innerHTML = "Resumo ainda não preenchido.";
			return;
		}

		let html = "";
		if (window.frappe && typeof frappe.markdown === "function") {
			html = frappe.markdown(texto);
		} else {
			html = renderSimpleMarkdown(texto);
		}

		const markdownNotRendered = /(\*\*[^*]+\*\*)|(\*[^*]+\*)/.test(html || "");
		if (markdownNotRendered) {
			html = renderSimpleMarkdown(texto);
		}

		campoResumo.classList.remove("text-muted");
		campoResumo.innerHTML = sanitizeRenderedHtml(html);
	}

	function renderSummary() {
		renderResumoMarkdown(entrevista.resumo);
	}

	async function carregarEntrevista() {
		const response = await frappe.call({
			method: "gris.api.gestao_adultos.obter_formulario_entrevista",
			args: { name: entrevistaName },
		});
		const data = response.message || {};
		config = data.config;
		entrevista = data.entrevista;
		buildAlertSelectionKeys();

		renderAssociado();
		renderDadosIniciais();
		renderSections();
		renderAlertas();
		renderSummary();
		await renderChart();
		setEditMode(false);
	}

	btnEditar?.addEventListener("click", () => setEditMode(true));
	btnCancelar?.addEventListener("click", async () => {
		try {
			await carregarEntrevista();
			frappe.show_alert({ message: "Edição cancelada.", indicator: "orange" });
		} catch (error) {
			console.error(error);
			frappe.msgprint("Não foi possível cancelar a edição.");
		}
	});
	btnOkModalAlerta?.addEventListener("click", closeAlertReasonModal);
	modalAlertaBackdrop?.addEventListener("click", closeAlertReasonModal);
	btnOkModalObservacao?.addEventListener("click", closeObservationModal);
	modalObservacaoBackdrop?.addEventListener("click", closeObservationModal);
	document.addEventListener("keydown", (event) => {
		if (event.key === "Escape" && modalAlerta?.style.display === "flex") {
			closeAlertReasonModal();
			return;
		}

		if (event.key === "Escape" && modalObservacao?.style.display === "flex") {
			closeObservationModal();
		}
	});

	btnSalvar?.addEventListener("click", async () => {
		const payload = collectPayload();
		await frappe.call({
			method: "gris.api.gestao_adultos.salvar_entrevista",
			args: {
				name: entrevistaName,
				payload: JSON.stringify(payload),
			},
		});
		window.location.reload();
	});

	try {
		await carregarEntrevista();
	} catch (error) {
		console.error(error);
		frappe.msgprint("Não foi possível carregar a entrevista.");
	}
	})();
});
