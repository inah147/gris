frappe.ready(async () => {
	const dataElement = document.getElementById("respostas-entrevista-data");
	if (!dataElement) {
		return;
	}

	let boot = {};
	try {
		boot = JSON.parse(dataElement.textContent || "{}");
	} catch (error) {
		console.error("Falha ao carregar os dados iniciais da entrevista.", error);
		frappe.msgprint(__("Não foi possível carregar os dados iniciais da entrevista."));
		return;
	}

	const config = boot.config || { sections: [], alert_rules: [] };
	const entrevista = boot.entrevista || {};
	const scoreRows = boot.scoreRows || [];
	const alertCategoryDefinitions = boot.alertCategoryDefinitions || [];
	const btnSalvar = document.getElementById("btn-salvar");
	const btnEditar = document.getElementById("btn-editar");
	const btnCancelar = document.getElementById("btn-cancelar");
	const resultadoLeitura = document.getElementById("resultado-leitura");
	const campoResumo = document.getElementById("campo-resumo");
	const modalAlerta = document.getElementById("modal-alerta");
	const modalAlertaMensagem = document.getElementById("modal-alerta-mensagem");
	const modalObservacao = document.getElementById("modal-observacao");
	const modalObservacaoPergunta = document.getElementById("modal-observacao-pergunta");
	const modalObservacaoMensagem = document.getElementById("modal-observacao-mensagem");
	const pageRoot = document.querySelector("[data-entrevista-root]");
	let editMode = false;
	let chart = null;
	let resizeHandlerBound = false;
	let alertSelectionKeys = new Set();
	let alertReasonBySelectionKey = new Map();

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
			Array.from(reasonMap.entries()).map(([key, reasons]) => [key, reasons.join("\n\n")]),
		);
	}

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
			}),
		);
	}

	function getFieldValue(fieldId) {
		return document.getElementById(fieldId)?.value || "";
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
				indicator.classList.toggle("hidden", !hasAlert);
				indicator.disabled = !hasAlert;
				indicator.setAttribute(
					"title",
					hasAlert ? "Ver motivo do alerta" : "Resposta sem alerta",
				);
				indicator.setAttribute(
					"aria-label",
					hasAlert ? "Ver motivo do alerta" : "Resposta sem alerta",
				);
				const questionCard = select.closest(".entrevista-question");
				if (questionCard) {
					questionCard.classList.toggle("entrevista-question--has-alert", hasAlert);
				}
			});
		});
	}

	function openAlertReasonModal(message) {
		if (!modalAlerta || !modalAlertaMensagem) {
			return;
		}

		modalAlertaMensagem.innerHTML = frappe.utils
			.escape_html(message || "Motivo do alerta não informado.")
			.replace(/\n/g, "<br>");
		if (typeof modalAlerta.showModal === "function") {
			modalAlerta.showModal();
		}
	}

	function openObservationModal(question, message) {
		if (!modalObservacao || !modalObservacaoMensagem || !modalObservacaoPergunta) {
			return;
		}

		modalObservacaoPergunta.textContent = question || "Pergunta";
		modalObservacaoMensagem.innerHTML = frappe.utils
			.escape_html(message || "Sem observações para esta resposta.")
			.replace(/\n/g, "<br>");
		if (typeof modalObservacao.showModal === "function") {
			modalObservacao.showModal();
		}
	}

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
					{ once: true },
				);
				existing.addEventListener(
					"error",
					() => reject(new Error("Falha ao carregar ECharts")),
					{ once: true },
				);
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
			if (typeof chart.dispose === "function") {
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
			if (chart && typeof chart.resize === "function") {
				chart.resize();
			}
		});

		resizeHandlerBound = true;
	}

	function bindQuestionFieldEvents() {
		config.sections.forEach((section) => {
			section.fields.forEach((field) => {
				const select = document.getElementById(field.fieldname);
				const obs = document.getElementById(field.observation_fieldname);
				const indicator = document.getElementById(`alert-indicator-${field.fieldname}`);
				const observationIndicator = document.getElementById(
					`obs-indicator-${field.fieldname}`,
				);
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
						const reason =
							alertReasonBySelectionKey.get(key) ||
							"Motivo do alerta não informado.";
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

						openObservationModal(
							field.label,
							obs.value || "Sem observações para esta resposta.",
						);
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
				indicator.classList.toggle("hidden", editMode || !hasObservation);
				indicator.setAttribute(
					"title",
					hasObservation ? "Ver observação" : "Sem observações",
				);
				indicator.setAttribute(
					"aria-label",
					hasObservation ? "Ver observação" : "Sem observações",
				);
			});
		});
	}

	function collectPayload() {
		const payload = {
			motivo_da_entrevista: getFieldValue("motivo_da_entrevista"),
			funcao_atual: getFieldValue("funcao_atual"),
			profissao: getFieldValue("profissao"),
			formacao: getFieldValue("formacao"),
			hobbies_e_interesses: getFieldValue("hobbies_e_interesses"),
			observacoes: getFieldValue("observacoes"),
		};

		config.sections.forEach((section) => {
			section.fields.forEach((field) => {
				payload[field.fieldname] = getFieldValue(field.fieldname);
				payload[field.observation_fieldname] = getFieldValue(field.observation_fieldname);
			});
		});

		return payload;
	}

	function setEditMode(enabled) {
		editMode = enabled;
		document.querySelectorAll("[data-read-mode]").forEach((el) => {
			el.classList.toggle("hidden", enabled);
		});

		document.querySelectorAll("[data-edit-mode]").forEach((el) => {
			el.classList.toggle("hidden", !enabled);
		});

		btnSalvar?.classList.toggle("hidden", !enabled);
		btnEditar?.classList.toggle("hidden", enabled);
		btnCancelar?.classList.toggle("hidden", !enabled);
		resultadoLeitura?.classList.toggle("hidden", enabled);
		pageRoot?.classList.toggle("is-editing", enabled);
		updateObservationIndicators();
		updateQuestionAlertIndicators();
	}

	function getChartSeriesData() {
		const target = document.getElementById("grafico-pontuacoes");
		const generalAlertsCount = (entrevista.alertas || []).filter(
			(alerta) =>
				Array.isArray(alerta.categorias) && alerta.categorias.includes("alerta_geral"),
		).length;

		return {
			target,
			labels: scoreRows.map((item) => item.label),
			scores: scoreRows.map((item) => Number(item.score || 0)),
			alertsByCategory: scoreRows.map((item) => Number(item.alertas_categoria || 0)),
			alertsTotal: scoreRows.map((item) => Number(item.alertas_totais || 0)),
			generalAlertsCount,
		};
	}

	function renderEcharts(
		target,
		labels,
		scores,
		alertsByCategory,
		alertsTotal,
		generalAlertsCount,
	) {
		const styles = getComputedStyle(document.documentElement);
		const barColor = styles.getPropertyValue("--color-chart-1").trim() || "#4477AA";
		const markColor = styles.getPropertyValue("--warning").trim() || "#fde6d4";
		const textColor = styles.getPropertyValue("--color-foreground").trim() || "#111827";
		const mutedColor = styles.getPropertyValue("--color-muted-foreground").trim() || "#6b7280";
		const borderColor = styles.getPropertyValue("--color-border").trim() || "#d1d5db";
		const backgroundColor = styles.getPropertyValue("--color-card").trim() || "#ffffff";
		target.innerHTML = "";
		chart = window.echarts.init(target);
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
			aria: { enabled: true },
			animation: true,
			color: [barColor],
			legend: {
				data: ["Pontuação"],
				top: 0,
				textStyle: { color: textColor },
			},
			grid: { left: 36, right: 20, top: 44, bottom: 90 },
			xAxis: {
				type: "category",
				data: labels,
				axisLabel: { interval: 0, rotate: 35, fontSize: 11, color: mutedColor },
				axisLine: { lineStyle: { color: borderColor } },
			},
			yAxis: {
				type: "value",
				name: "Pontuação",
				minInterval: 1,
				nameTextStyle: { color: mutedColor },
				axisLabel: { color: mutedColor },
				splitLine: { lineStyle: { color: borderColor, opacity: 0.65 } },
			},
			tooltip: {
				trigger: "axis",
				axisPointer: { type: "shadow" },
				backgroundColor: backgroundColor,
				borderColor,
				textStyle: { color: textColor },
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
					itemStyle: { color: barColor, borderRadius: [6, 6, 0, 0] },
					barMaxWidth: 46,
					markPoint: {
						symbol: "circle",
						symbolSize: 24,
						symbolOffset: [0, -24],
						itemStyle: {
							color: "transparent",
							borderColor: markColor,
							borderWidth: 2,
						},
						label: {
							show: true,
							position: "inside",
							align: "center",
							verticalAlign: "middle",
							formatter: ({ value }) => `${value}`,
							fontSize: 10,
							fontWeight: 700,
							color: "#111827",
						},
						data: alertMarkers,
					},
				},
			],
		});
		bindChartResize();
	}

	async function renderChart() {
		const { target, labels, scores, alertsByCategory, alertsTotal, generalAlertsCount } =
			getChartSeriesData();
		if (!target) {
			return;
		}
		if (!labels.length) {
			target.innerHTML =
				'<p class="text-sm text-muted-foreground">Nenhuma pontuação calculada para exibir.</p>';
			return;
		}

		destroyCurrentChart();
		await ensureEcharts();
		renderEcharts(target, labels, scores, alertsByCategory, alertsTotal, generalAlertsCount);
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
				const value = String(attribute.value || "")
					.trim()
					.toLowerCase();

				if (name.startsWith("on") || name === "srcdoc") {
					node.removeAttribute(attribute.name);
					return;
				}

				if (
					(name === "href" || name === "src") &&
					(value.startsWith("javascript:") || value.startsWith("data:text/html"))
				) {
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

	btnEditar?.addEventListener("click", () => setEditMode(true));
	btnCancelar?.addEventListener("click", () => {
		window.location.reload();
	});

	document.querySelectorAll("[data-close-dialog]").forEach((button) => {
		button.addEventListener("click", () => {
			document.getElementById(button.dataset.closeDialog)?.close();
		});
	});

	btnSalvar?.addEventListener("click", async (event) => {
		const button = event.currentTarget;
		button.disabled = true;
		button.setAttribute("aria-busy", "true");

		const payload = collectPayload();
		try {
			await frappe.call({
				method: "gris.api.gestao_adultos.salvar_entrevista",
				args: {
					name: entrevista.name,
					payload: JSON.stringify(payload),
				},
			});
			showToast(
				"success",
				"Entrevista salva",
				"As alterações foram registradas com sucesso.",
			);
			window.setTimeout(() => {
				window.location.reload();
			}, 700);
		} catch (error) {
			console.error(error);
			button.disabled = false;
			button.removeAttribute("aria-busy");
			frappe.msgprint(__("Não foi possível salvar a entrevista."));
		}
	});

	try {
		buildAlertSelectionKeys();
		bindQuestionFieldEvents();
		renderSummary();
		await renderChart();
		setEditMode(false);
	} catch (error) {
		console.error(error);
		frappe.msgprint(__("Não foi possível carregar a entrevista."));
	}
});
