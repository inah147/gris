/*
 * Dialog "Cálculo de Vagas" — ocupação de um ramo e a previsão dos próximos 12 meses
 * (Apache ECharts, carregado sob demanda).
 *
 * Compartilhado pela Fila de Espera (/recepcao/fila_espera, botão no cabeçalho de cada
 * coluna) e pelos modais dos cards da visão geral (/recepcao/visao_geral, ícone ao lado do
 * ramo): as duas telas mostram exatamente o mesmo dialog, com os mesmos números.
 *
 * Marcação, dados (JSON em #vagas-do-ramo-dados) e assets vêm de
 * templates/includes/vagas_do_ramo_dialog.html; a página só chama
 * `window.grisVagasDoRamo.abrir(ramo, { aoFechar })`.
 *
 * `aoFechar` existe por causa da visão geral: lá o dialog abre por cima do modal do card,
 * e showModal() põe o novo na top layer e torna o resto inerte — o modal de origem precisa
 * fechar antes e reabrir depois.
 */
(function () {
	"use strict";

	const CHART_COLORS = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9", "#CC79A7"];

	let dadosPorRamo = null;
	let vagasChart = null;
	let aoFecharPendente = null;

	function lerDados() {
		if (dadosPorRamo) return dadosPorRamo;
		const el = document.getElementById("vagas-do-ramo-dados");
		try {
			dadosPorRamo = JSON.parse((el && el.textContent) || "{}") || {};
		} catch (err) {
			console.warn("Falha ao ler os dados de vagas por ramo:", err);
			dadosPorRamo = {};
		}
		return dadosPorRamo;
	}

	function temDados(ramo) {
		return Boolean(ramo && lerDados()[ramo]);
	}

	// ---------- Helpers de ECharts -------------------------------------------

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
					() => (window.echarts ? resolve() : reject(new Error("ECharts indisponível"))),
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
				window.echarts ? resolve() : reject(new Error("ECharts indisponível"));
			script.onerror = () => reject(new Error("Falha ao carregar ECharts"));
			document.head.appendChild(script);
		});

	function readToken(name, fallback) {
		const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
		return value || fallback;
	}

	function buildVagasChartOption(labels, values) {
		const mutedFg = readToken("--color-muted-foreground", "#64748b");
		const borderColor = readToken("--color-border", "#e2e8f0");
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
					return `<strong>${frappe.utils.escape_html(
						item.name
					)}</strong><br/>Vagas: ${v}`;
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
				name: "Vagas",
				nameTextStyle: { color: mutedFg, fontSize: 11 },
				axisLabel: { color: mutedFg, fontSize: 11 },
				splitLine: { lineStyle: { color: borderColor } },
			},
			series: [
				{
					name: "Vagas",
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

	async function renderVagasChart(labels, values) {
		const target = document.getElementById("vagasChart");
		if (!target) return;
		try {
			await ensureEcharts();
		} catch (err) {
			console.warn(err);
			return;
		}
		if (!labels || !labels.length) {
			if (vagasChart) vagasChart.clear();
			return;
		}
		if (!vagasChart) {
			vagasChart = window.echarts.init(target);
			window.addEventListener("resize", () => vagasChart && vagasChart.resize());
		}
		vagasChart.setOption(buildVagasChartOption(labels, values), true);
		// O <dialog> só calcula tamanho ao abrir; força recálculo após showModal.
		requestAnimationFrame(() => vagasChart && vagasChart.resize());
	}

	// ---------- Dialog --------------------------------------------------------

	function preencher(id, valor) {
		const el = document.getElementById(id);
		if (el) el.textContent = valor ?? "—";
	}

	function abrir(ramo, opcoes) {
		const dialogEl = document.getElementById("modalVagas");
		const dados = lerDados()[ramo];
		if (!dialogEl || !dados) return;

		aoFecharPendente = (opcoes && opcoes.aoFechar) || null;

		preencher("modalVagasRamo", ramo);
		preencher("vagasLimite", dados.limite);
		preencher("vagasAtivos", dados.ativos);
		preencher("vagasNovos", dados.novos);
		preencher("vagasSaindo", dados.saindo);
		preencher("vagasDisponiveis", dados.disponiveis);

		if (typeof dialogEl.showModal === "function" && !dialogEl.open) {
			try {
				dialogEl.showModal();
			} catch (err) {
				console.error('Falha ao abrir dialog "modalVagas":', err);
				frappe.show_alert({
					message: "Não foi possível abrir o modal. Recarregue a página.",
					indicator: "red",
				});
				return;
			}
		}
		renderVagasChart(dados.chart_labels || [], dados.chart_values || []);
	}

	document.addEventListener("DOMContentLoaded", function () {
		const dialogEl = document.getElementById("modalVagas");
		if (!dialogEl) return;

		// O botão "Fechar" do rodapé não depende do handler de cada página.
		dialogEl.querySelectorAll("[data-dialog-close]").forEach((botao) => {
			botao.addEventListener("click", () => dialogEl.open && dialogEl.close());
		});

		dialogEl.addEventListener("close", function () {
			const aoFechar = aoFecharPendente;
			aoFecharPendente = null;
			if (aoFechar) aoFechar();
		});
	});

	window.grisVagasDoRamo = { abrir: abrir, temDados: temDados };
})();
