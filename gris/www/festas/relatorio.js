/* Relatório completo da festa — gráficos (ECharts) e impressão.
 * Os dados das tabelas/cards/markdown são renderizados no servidor (Jinja);
 * aqui só tratamos os gráficos e a ação de imprimir/salvar PDF.
 */
(function () {
	"use strict";

	var data = window._relatorioData || { barracas: [], waterfall: [], resultado: 0, distribuicao: [], entradas: {} };

	// Paleta Okabe-Ito (acessível para daltonismo) — padrão do projeto.
	var CHART_PALETTE = [
		"#0072B2", "#E69F00", "#009E73", "#D55E00",
		"#56B4E9", "#CC79A7", "#F0E442", "#000000",
	];
	var COR_ENTRADA = "#009E73";
	var COR_SAIDA = "#D55E00";
	// Entradas/portaria — mesmas cores da aba Acompanhamento da portaria.
	var COR_ENTROU = "#009E73";
	var COR_NAO_ENTROU = "#D55E00";
	var COR_PORTARIA = "#0072B2";
	var COR_COMPRA_PREVIA = "#56B4E9";
	var COR_COMPRA_PORTARIA = "#E69F00";
	var COR_LINHA = "#0072B2";

	var echartsLoading = null;
	var instances = [];

	function ensureECharts() {
		if (window.echarts) return Promise.resolve();
		if (echartsLoading) return echartsLoading;
		echartsLoading = new Promise(function (resolve, reject) {
			var script = document.createElement("script");
			script.src = "/assets/gris/vendor/echarts/echarts.min.js";
			script.onload = function () {
				if (window.echarts) resolve();
				else reject(new Error("ECharts não carregou."));
			};
			script.onerror = function () { reject(new Error("Falha ao carregar ECharts.")); };
			document.head.appendChild(script);
		});
		return echartsLoading;
	}

	function fmtMoeda(valor) {
		return new Intl.NumberFormat("pt-BR", {
			style: "currency", currency: "BRL", minimumFractionDigits: 2,
		}).format(Number(valor) || 0);
	}

	function initChart(el) {
		var chart = window.echarts.init(el);
		instances.push(chart);
		window.addEventListener("resize", function () { chart.resize(); });
		return chart;
	}

	function renderBarracas() {
		var el = document.getElementById("rel-chart-barracas");
		if (!el) return;
		var itens = data.barracas || [];
		if (!itens.length) {
			el.innerHTML = '<p class="rel-chart__empty">Sem barracas para exibir.</p>';
			return;
		}
		var chart = initChart(el);
		chart.setOption({
			aria: { enabled: true },
			color: CHART_PALETTE,
			tooltip: {
				trigger: "axis",
				axisPointer: { type: "shadow" },
				formatter: function (params) {
					var p = params[0];
					return p.name + "<br/>" + p.marker + " " + fmtMoeda(p.value);
				},
			},
			grid: { left: 16, right: 24, top: 24, bottom: 64, containLabel: true },
			xAxis: {
				type: "category",
				data: itens.map(function (b) { return b.label; }),
				axisLabel: { interval: 0, rotate: itens.length > 4 ? 25 : 0 },
			},
			yAxis: {
				type: "value",
				name: "Arrecadação (R$)",
				nameLocation: "middle", nameGap: 56, nameRotate: 90,
				nameTextStyle: { fontSize: 12 },
				axisLabel: { formatter: function (v) { return "R$ " + Number(v).toLocaleString("pt-BR"); } },
			},
			series: [{
				name: "Arrecadação",
				type: "bar",
				data: itens.map(function (b) { return Number(b.valor) || 0; }),
				barMaxWidth: 64,
				itemStyle: { borderRadius: [4, 4, 0, 0] },
			}],
		}, true);
	}

	function renderWaterfall() {
		var el = document.getElementById("rel-chart-waterfall");
		if (!el) return;
		var passos = data.waterfall || [];
		if (!passos.length) {
			el.innerHTML = '<p class="rel-chart__empty">Sem dados financeiros para exibir.</p>';
			return;
		}

		var cats = [];
		var pontos = [];
		var cores = [];
		var running = 0;
		passos.forEach(function (s, i) {
			var start = running;
			var end = running + (Number(s.valor) || 0);
			pontos.push({ value: [i, start, end, Number(s.valor) || 0] });
			cores.push((Number(s.valor) || 0) >= 0 ? COR_ENTRADA : COR_SAIDA);
			cats.push(s.label);
			running = end;
		});
		var resultado = Number(data.resultado) || 0;
		var idxResultado = passos.length;
		cats.push("Resultado");
		pontos.push({ value: [idxResultado, 0, resultado, resultado] });
		cores.push(resultado >= 0 ? COR_ENTRADA : COR_SAIDA);

		var chart = initChart(el);
		chart.setOption({
			aria: { enabled: true },
			tooltip: {
				trigger: "item",
				formatter: function (p) { return cats[p.value[0]] + "<br/>" + fmtMoeda(p.value[3]); },
			},
			grid: { left: 16, right: 24, top: 32, bottom: 72, containLabel: true },
			xAxis: {
				type: "category",
				data: cats,
				axisLabel: { interval: 0, rotate: cats.length > 4 ? 30 : 0 },
			},
			yAxis: {
				type: "value",
				name: "Valor (R$)",
				nameLocation: "middle", nameGap: 56, nameRotate: 90,
				nameTextStyle: { fontSize: 12 },
				axisLabel: { formatter: function (v) { return "R$ " + Number(v).toLocaleString("pt-BR"); } },
			},
			series: [{
				type: "custom",
				encode: { x: 0, y: [1, 2] },
				data: pontos,
				renderItem: function (params, api) {
					var catIndex = api.value(0);
					var pStart = api.coord([catIndex, api.value(1)]);
					var pEnd = api.coord([catIndex, api.value(2)]);
					var bandWidth = api.size([1, 0])[0];
					var width = Math.min(bandWidth * 0.5, 48);
					var yTop = Math.min(pStart[1], pEnd[1]);
					var height = Math.max(Math.abs(pStart[1] - pEnd[1]), 1);
					return {
						type: "group",
						children: [
							{
								type: "rect",
								shape: { x: pStart[0] - width / 2, y: yTop, width: width, height: height, r: [3, 3, 0, 0] },
								style: { fill: cores[catIndex] },
							},
							{
								type: "text",
								style: {
									text: fmtMoeda(api.value(3)),
									x: pStart[0], y: yTop - 6,
									textAlign: "center", textVerticalAlign: "bottom",
									fontSize: 11, fontWeight: 600, fill: "#1f2937",
								},
							},
						],
					};
				},
			}],
		}, true);
	}

	function renderConvidados() {
		var el = document.getElementById("rel-chart-convidados");
		if (!el) return;
		var dist = data.distribuicao || [];
		var total = dist.reduce(function (a, b) { return a + (Number(b) || 0); }, 0);
		if (!dist.length || total === 0) {
			el.innerHTML = '<p class="rel-chart__empty">Sem respostas numéricas dos convidados.</p>';
			return;
		}
		var chart = initChart(el);
		chart.setOption({
			aria: { enabled: true },
			color: [CHART_PALETTE[0]],
			tooltip: {
				trigger: "axis",
				axisPointer: { type: "shadow" },
				formatter: function (params) {
					var p = params[0];
					return "Nota " + p.name + "<br/>" + p.marker + " " + p.value + " resposta(s)";
				},
			},
			grid: { left: 16, right: 24, top: 24, bottom: 40, containLabel: true },
			xAxis: { type: "category", data: dist.map(function (_v, i) { return String(i); }), name: "Nota" },
			yAxis: {
				type: "value", name: "Respostas", minInterval: 1,
				nameLocation: "middle", nameGap: 40, nameRotate: 90, nameTextStyle: { fontSize: 12 },
			},
			series: [{
				name: "Respostas", type: "bar",
				data: dist.map(function (v) { return Number(v) || 0; }),
				barMaxWidth: 40, itemStyle: { borderRadius: [4, 4, 0, 0] },
			}],
		}, true);
	}

	function pieEntradas(elId, paleta, pares, emptyMsg) {
		var el = document.getElementById(elId);
		if (!el) return;
		var total = pares.reduce(function (a, p) { return a + (Number(p.value) || 0); }, 0);
		if (total === 0) {
			el.innerHTML = '<p class="rel-chart__empty">' + (emptyMsg || "Sem entradas registradas.") + '</p>';
			return;
		}
		var chart = initChart(el);
		chart.setOption({
			aria: { enabled: true },
			color: paleta,
			tooltip: { trigger: "item" },
			legend: { bottom: 0 },
			series: [{
				name: "Entradas",
				type: "pie",
				radius: ["40%", "62%"],
				center: ["50%", "45%"],
				avoidLabelOverlap: true,
				label: {
					show: true,
					formatter: function (p) { return p.name + "\n" + p.value + " (" + p.percent + "%)"; },
				},
				data: pares,
			}],
		}, true);
	}

	function renderEntradasPizza() {
		var pizza = (data.entradas && data.entradas.pizza) || {};
		pieEntradas("rel-chart-entradas-pizza", [COR_ENTROU, COR_NAO_ENTROU, COR_PORTARIA], [
			{ value: Number(pizza.entrou) || 0, name: "Entrou" },
			{ value: Number(pizza.nao_entrou) || 0, name: "Não entrou" },
			{ value: Number(pizza.comprou_portaria) || 0, name: "Comprou na Portaria" },
		]);
	}

	function renderEntradasOrigem() {
		var origem = (data.entradas && data.entradas.origem) || {};
		pieEntradas("rel-chart-entradas-origem", [COR_COMPRA_PREVIA, COR_COMPRA_PORTARIA], [
			{ value: Number(origem.compra_previa) || 0, name: "Compra Prévia" },
			{ value: Number(origem.compra_portaria) || 0, name: "Compra na Portaria" },
		]);
	}

	function renderEntradasPrevia() {
		// De todas as compras prévias (não-portaria), quantos entraram x não entraram.
		var pizza = (data.entradas && data.entradas.pizza) || {};
		pieEntradas("rel-chart-entradas-previa", [COR_ENTROU, COR_NAO_ENTROU], [
			{ value: Number(pizza.entrou) || 0, name: "Entrou" },
			{ value: Number(pizza.nao_entrou) || 0, name: "Não entrou" },
		], "Sem compras prévias registradas.");
	}

	function renderEntradasLinha(elId, modo) {
		var el = document.getElementById(elId);
		if (!el) return;
		var linha = (data.entradas && data.entradas.linha) || [];
		if (!linha.length) {
			el.innerHTML = '<p class="rel-chart__empty">Sem entradas registradas.</p>';
			return;
		}
		var acumulado = modo === "acumulado";
		var xs = linha.map(function (p) {
			var dt = new Date(p.bin);
			return Number.isNaN(dt.getTime())
				? ""
				: dt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
		});
		var valores = linha.map(function (p) {
			return acumulado ? Number(p.acumulado) || 0 : Number(p.qtd) || 0;
		});
		var chart = initChart(el);
		chart.setOption({
			aria: { enabled: true },
			color: [COR_LINHA],
			tooltip: { trigger: "axis" },
			grid: { left: 16, right: 24, top: 24, bottom: 40, containLabel: true },
			xAxis: {
				type: "category",
				data: xs,
				axisLabel: { interval: Math.floor(Math.max(0, xs.length / 8)) },
			},
			yAxis: {
				type: "value", name: "Entradas", minInterval: 1,
				nameLocation: "middle", nameGap: 36, nameRotate: 90, nameTextStyle: { fontSize: 12 },
			},
			series: [{
				name: acumulado ? "Acumulado" : "Por janela (15 min)",
				type: "line",
				// Janela: linha suave com área pintada. Acumulado: linha comum.
				smooth: !acumulado,
				data: valores,
				areaStyle: acumulado ? undefined : { opacity: 0.18 },
			}],
		}, true);
	}

	function renderCharts() {
		ensureECharts().then(function () {
			renderBarracas();
			renderWaterfall();
			renderConvidados();
			renderEntradasPizza();
			renderEntradasOrigem();
			renderEntradasPrevia();
			renderEntradasLinha("rel-chart-entradas-janela", "janela");
			renderEntradasLinha("rel-chart-entradas-acumulado", "acumulado");
		}).catch(function (err) {
			console.error(err);
		});
	}

	function bindPrint() {
		var btn = document.querySelector('[data-action="baixar-pdf"]');
		if (!btn) return;
		btn.addEventListener("click", function () {
			// PDF gerado no servidor (template dedicado), não a impressão da página.
			var festa = btn.getAttribute("data-festa");
			if (!festa) return;
			var url = "/api/method/gris.api.festas.relatorio.download_relatorio_pdf?festa_name=" +
				encodeURIComponent(festa);
			window.open(url, "_blank");
		});
	}

	function init() {
		renderCharts();
		bindPrint();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
