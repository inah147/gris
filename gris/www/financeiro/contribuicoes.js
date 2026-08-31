// Contribuições mensais — gráficos ECharts, filtros e paginação da tabela.
// O detalhe de um contribuinte é uma tela própria: /financeiro/contribuicao.
(function () {
	"use strict";

	const CHART_COLORS = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9", "#CC79A7"];
	const LINHAS_POR_PAGINA = 15;

	let paginaAtual = 1;

	// ─────────────────────────── utilitários ───────────────────────────

	function parseNumber(valor) {
		const numero = typeof valor === "number" ? valor : parseFloat(valor || 0);
		return Number.isFinite(numero) ? numero : 0;
	}

	function formatarMoedaCompleta(valor) {
		return parseNumber(valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
	}

	function formatarPercentual(valor) {
		return `${parseNumber(valor).toFixed(1).replace(".", ",")}%`;
	}

	// Escapa também aspas: o resultado é interpolado em atributos, não só em texto.
	function escapeHtml(texto) {
		return String(texto == null ? "" : texto)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	function isMobile() {
		return window.innerWidth < 640;
	}

	// ─────────────────────────── gráficos ───────────────────────────

	function ensureEcharts() {
		return new Promise((resolve, reject) => {
			if (window.echarts) {
				resolve();
				return;
			}
			const existente = document.querySelector('script[data-gris-echarts="1"]');
			if (existente) {
				existente.addEventListener(
					"load",
					() =>
						window.echarts ? resolve() : reject(new Error("ECharts não disponível")),
					{ once: true }
				);
				existente.addEventListener(
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
	}

	function baseOption(yAxisName) {
		return {
			aria: { enabled: true },
			color: CHART_COLORS,
			animationDuration: 400,
			tooltip: {
				trigger: "axis",
				confine: true,
				className: "echarts-tooltip-modern",
				axisPointer: { type: "shadow" },
			},
			legend: { type: "scroll", top: 4 },
			grid: {
				top: 52,
				left: 14,
				right: 14,
				bottom: isMobile() ? 60 : 32,
				containLabel: true,
			},
			xAxis: {
				type: "category",
				axisTick: { alignWithLabel: true },
				axisLabel: {
					interval: 0,
					rotate: isMobile() ? 40 : 0,
					hideOverlap: true,
					fontSize: isMobile() ? 10 : 12,
				},
			},
			yAxis: { type: "value", name: yAxisName },
		};
	}

	function getChart(id) {
		const alvo = document.getElementById(id);
		if (!alvo || !window.echarts) return null;
		const existente = window.echarts.getInstanceByDom(alvo);
		if (existente) return existente;
		alvo.innerHTML = "";
		return window.echarts.init(alvo);
	}

	function setChartMessage(id, texto) {
		const alvo = document.getElementById(id);
		if (!alvo) return;
		if (window.echarts) {
			const existente = window.echarts.getInstanceByDom(alvo);
			if (existente) existente.dispose();
		}
		alvo.innerHTML = `<div class="text-sm text-muted-foreground px-2 pt-3">${escapeHtml(
			texto
		)}</div>`;
	}

	function temDados(valores) {
		return (valores || []).some((v) => parseNumber(v) !== 0);
	}

	function renderRecebidoEsperado(series) {
		const id = "chart-contrib-recebido-esperado";
		const semDados =
			!temDados(series.recebido) &&
			!temDados(series.esperado) &&
			!temDados(series.nao_vinculado);
		if (semDados) {
			setChartMessage(id, "Nenhuma contribuição registrada no período.");
			return;
		}
		const chart = getChart(id);
		if (!chart) return;

		chart.setOption(
			Object.assign(baseOption("R$"), {
				tooltip: {
					trigger: "axis",
					confine: true,
					className: "echarts-tooltip-modern",
					axisPointer: { type: "shadow" },
					valueFormatter: (valor) => formatarMoedaCompleta(valor),
				},
				xAxis: Object.assign(baseOption().xAxis, { data: series.labels }),
				series: [
					{
						name: "Recebido (identificado)",
						type: "bar",
						stack: "recebido",
						emphasis: { focus: "series" },
						itemStyle: { borderColor: "transparent", borderWidth: 1 },
						data: series.recebido,
					},
					{
						name: "Recebido (a identificar)",
						type: "bar",
						stack: "recebido",
						emphasis: { focus: "series" },
						itemStyle: { borderColor: "transparent", borderWidth: 1 },
						data: series.nao_vinculado,
					},
					{
						name: "Esperado",
						type: "line",
						smooth: false,
						symbol: "diamond",
						symbolSize: 8,
						lineStyle: { type: "dashed", width: 2 },
						data: series.esperado,
					},
				],
			}),
			true
		);
	}

	function renderAdimplencia(series) {
		const id = "chart-contrib-adimplencia";
		if (!temDados(series.adimplencia)) {
			setChartMessage(id, "Sem meses apurados para calcular adimplência.");
			return;
		}
		const chart = getChart(id);
		if (!chart) return;

		chart.setOption(
			Object.assign(baseOption("%"), {
				tooltip: {
					trigger: "axis",
					confine: true,
					className: "echarts-tooltip-modern",
					axisPointer: { type: "line" },
					valueFormatter: (valor) => formatarPercentual(valor),
				},
				xAxis: Object.assign(baseOption().xAxis, { data: series.labels }),
				yAxis: { type: "value", name: "%", max: 100, min: 0 },
				series: [
					{
						name: "Meses quitados",
						type: "line",
						smooth: false,
						symbol: "circle",
						symbolSize: 8,
						lineStyle: { width: 2 },
						areaStyle: { opacity: 0.12 },
						data: series.adimplencia,
					},
				],
			}),
			true
		);
	}

	function initGraficos() {
		const bloco = document.getElementById("contrib-dados-graficos");
		if (!bloco) return;

		let dados;
		try {
			dados = JSON.parse(bloco.textContent || "{}");
		} catch (e) {
			setChartMessage(
				"chart-contrib-recebido-esperado",
				"Não foi possível ler os dados do período."
			);
			setChartMessage(
				"chart-contrib-adimplencia",
				"Não foi possível ler os dados do período."
			);
			return;
		}

		const series = dados.series || {};
		ensureEcharts()
			.then(() => {
				renderRecebidoEsperado(series);
				renderAdimplencia(series);
			})
			.catch(() => {
				setChartMessage(
					"chart-contrib-recebido-esperado",
					"Não foi possível carregar os gráficos."
				);
				setChartMessage(
					"chart-contrib-adimplencia",
					"Não foi possível carregar os gráficos."
				);
			});

		let redimensionando = null;
		window.addEventListener("resize", () => {
			clearTimeout(redimensionando);
			redimensionando = setTimeout(() => {
				["chart-contrib-recebido-esperado", "chart-contrib-adimplencia"].forEach((id) => {
					const alvo = document.getElementById(id);
					if (!alvo || !window.echarts) return;
					const instancia = window.echarts.getInstanceByDom(alvo);
					if (instancia) instancia.resize();
				});
			}, 150);
		});
	}

	// ─────────────────────────── tabela ───────────────────────────

	function getLinhas() {
		return Array.from(document.querySelectorAll("#contribTabela tbody > tr.contrib-linha"));
	}

	function linhasVisiveis() {
		return getLinhas().filter((linha) => !linha.classList.contains("filter-hidden"));
	}

	function aplicarFiltros() {
		const termo = (document.getElementById("filtroAssociado")?.value || "")
			.trim()
			.toLowerCase();
		const situacao =
			document.querySelector('#filtroSituacao > input[type="hidden"]')?.value || "";

		getLinhas().forEach((linha) => {
			const nome = (linha.getAttribute("data-nome") || "").toLowerCase();
			const casaNome = !termo || nome.includes(termo);
			const casaSituacao = !situacao || linha.getAttribute("data-situacao") === situacao;
			linha.classList.toggle("filter-hidden", !(casaNome && casaSituacao));
		});

		paginaAtual = 1;
		atualizarPaginacao();
	}

	function atualizarPaginacao() {
		const visiveis = linhasVisiveis();
		const totalPaginas = Math.max(1, Math.ceil(visiveis.length / LINHAS_POR_PAGINA));
		if (paginaAtual > totalPaginas) paginaAtual = totalPaginas;

		getLinhas().forEach((linha) => linha.classList.add("hidden-by-page"));
		visiveis.forEach((linha, indice) => {
			const pagina = Math.floor(indice / LINHAS_POR_PAGINA) + 1;
			linha.classList.toggle("hidden-by-page", pagina !== paginaAtual);
		});

		const aviso = document.getElementById("contribSemResultado");
		if (aviso) aviso.classList.toggle("hidden", visiveis.length > 0);

		renderControlesPaginacao(totalPaginas, visiveis.length);
	}

	function renderControlesPaginacao(totalPaginas, totalLinhas) {
		const container = document.getElementById("contribPaginacao");
		if (!container) return;
		container.innerHTML = "";
		if (totalLinhas === 0 || totalPaginas <= 1) return;
		container.classList.add("btn-group");

		const addBotao = (rotulo, pagina, desabilitado, ativo) => {
			const botao = document.createElement("button");
			botao.type = "button";
			botao.textContent = rotulo;
			botao.className = ativo ? "btn-sm-primary" : "btn-sm-outline";
			if (ativo) botao.setAttribute("aria-current", "page");
			if (desabilitado) {
				botao.disabled = true;
				botao.setAttribute("aria-disabled", "true");
			} else if (!ativo) {
				botao.addEventListener("click", () => {
					paginaAtual = pagina;
					atualizarPaginacao();
				});
			}
			container.appendChild(botao);
		};

		addBotao("«", 1, paginaAtual === 1, false);
		addBotao("‹", paginaAtual - 1, paginaAtual === 1, false);
		const janela = 5;
		let inicio = Math.max(1, paginaAtual - Math.floor(janela / 2));
		let fim = Math.min(totalPaginas, inicio + janela - 1);
		inicio = Math.max(1, fim - janela + 1);
		for (let pagina = inicio; pagina <= fim; pagina += 1) {
			addBotao(String(pagina), pagina, false, pagina === paginaAtual);
		}
		addBotao("›", paginaAtual + 1, paginaAtual === totalPaginas, false);
		addBotao("»", totalPaginas, paginaAtual === totalPaginas, false);
	}

	// ─────────────────────────── ligações ───────────────────────────

	function init() {
		initGraficos();

		const filtroNome = document.getElementById("filtroAssociado");
		if (filtroNome) filtroNome.addEventListener("input", aplicarFiltros);

		// O macro `select` dispara `change` no próprio componente (não no input hidden,
		// que é filho dele) e só então atualiza o valor do hidden.
		const filtroSituacao = document.getElementById("filtroSituacao");
		if (filtroSituacao) filtroSituacao.addEventListener("change", aplicarFiltros);

		atualizarPaginacao();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
