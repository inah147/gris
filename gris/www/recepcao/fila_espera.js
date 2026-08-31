// Fila de Espera da Recepção — interações cliente
// Usa exclusivamente o design system Basecoat (<dialog> HTML5 + alert + badge)
// e Apache ECharts para a previsão de vagas.

(function () {
	const CHART_COLORS = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9", "#CC79A7"];

	let currentFilaId = null;
	let currentAssociadoId = null;
	let currentAssociadoNome = "";
	let vagasChart = null;

	// ---------- Helpers de dialog --------------------------------------------

	function openDialog(id) {
		const el = document.getElementById(id);
		if (!el || typeof el.showModal !== "function" || el.open) return;
		try {
			el.showModal();
		} catch (err) {
			console.error(`Falha ao abrir dialog "${id}":`, err);
			frappe.show_alert({
				message: "Não foi possível abrir o modal. Recarregue a página.",
				indicator: "red",
			});
		}
	}

	function closeDialog(id) {
		const el = document.getElementById(id);
		if (el && el.open) el.close();
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

	// ---------- Modal de detalhes da fila ------------------------------------

	function openFilaModal(card) {
		currentFilaId = card.dataset.id;
		currentAssociadoId = card.dataset.associado;
		currentAssociadoNome = card.dataset.nome || "este associado";

		document.getElementById("modalAssociadoNome").textContent = card.dataset.nome || "";
		document.getElementById("modalResponsavelNome").textContent =
			card.dataset.responsavel || "";
		document.getElementById("modalPosicao").textContent = "#" + (card.dataset.posicao || "");
		document.getElementById("modalPrevisao").textContent =
			card.dataset.previsao || "Sem previsão";
		document.getElementById("modalDataInclusao").textContent = card.dataset.dataInclusao || "";

		openDialog("modalFilaEspera");
	}

	function abrirFicha() {
		if (currentAssociadoId) {
			window.location.href = `/recepcao/ficha_registro?name=${encodeURIComponent(
				currentAssociadoId
			)}`;
		}
	}

	// ---------- Modal de confirmação de chamada ------------------------------

	function abrirConfirmarChamada() {
		if (!currentFilaId) return;
		document.getElementById("modalChamadaNome").textContent = currentAssociadoNome;
		closeDialog("modalFilaEspera");
		openDialog("modalConfirmarChamada");
	}

	function cancelarChamada() {
		closeDialog("modalConfirmarChamada");
		// Reabre o modal anterior caso ainda haja contexto.
		if (currentFilaId) openDialog("modalFilaEspera");
	}

	function confirmarChamada() {
		if (!currentFilaId) return;
		// Fecha antes de chamar o servidor: com um <dialog> aberto via showModal()
		// o restante da página fica inerte e mensagens do Frappe não apareceriam.
		closeDialog("modalConfirmarChamada");
		frappe.call({
			method: "gris.www.recepcao.fila_espera.chamar_associado",
			args: { fila_id: currentFilaId },
			freeze: true,
			freeze_message: "Chamando associado...",
			callback: function (r) {
				if (r.exc) return;
				frappe.show_alert({
					message: "Associado chamado com sucesso",
					indicator: "green",
				});
				setTimeout(() => window.location.reload(), 800);
			},
			error: function () {
				frappe.show_alert({
					message: "Não foi possível chamar o associado",
					indicator: "red",
				});
			},
		});
	}

	// ---------- Modal de confirmação de desistência --------------------------

	function abrirConfirmarDesistencia() {
		if (!currentFilaId) return;
		closeDialog("modalFilaEspera");
		openDialog("modalConfirmarDesistencia");
	}

	function cancelarDesistencia() {
		closeDialog("modalConfirmarDesistencia");
		// Reabre o modal anterior caso ainda haja contexto.
		if (currentFilaId) openDialog("modalFilaEspera");
	}

	function confirmarDesistencia() {
		if (!currentFilaId) return;
		// Mesmo motivo de confirmarChamada: fechar o dialog antes da chamada.
		closeDialog("modalConfirmarDesistencia");
		frappe.call({
			method: "gris.www.recepcao.fila_espera.registrar_desistencia",
			args: { fila_id: currentFilaId },
			freeze: true,
			freeze_message: "Registrando desistência...",
			callback: function (r) {
				if (r.exc) return;
				frappe.show_alert({ message: "Desistência registrada", indicator: "green" });
				setTimeout(() => window.location.reload(), 800);
			},
			error: function () {
				frappe.show_alert({
					message: "Não foi possível registrar a desistência",
					indicator: "red",
				});
			},
		});
	}

	// ---------- Modal de detalhes de vagas -----------------------------------

	function openVagasModal(button) {
		const ramo = button.dataset.ramo || "";
		document.getElementById("modalVagasRamo").textContent = ramo;
		document.getElementById("vagasLimite").textContent = button.dataset.limite ?? "—";
		document.getElementById("vagasAtivos").textContent = button.dataset.ativos ?? "—";
		document.getElementById("vagasNovos").textContent = button.dataset.novos ?? "—";
		document.getElementById("vagasSaindo").textContent = button.dataset.saindo ?? "—";
		document.getElementById("vagasDisponiveis").textContent =
			button.dataset.disponiveis ?? "—";

		let labels = [];
		let values = [];
		try {
			labels = JSON.parse(button.dataset.chartLabels || "[]");
			values = JSON.parse(button.dataset.chartValues || "[]");
		} catch (err) {
			console.warn("Falha ao ler dados do gráfico de vagas:", err);
		}

		openDialog("modalVagas");
		renderVagasChart(labels, values);
	}

	// ---------- Bootstrap -----------------------------------------------------

	frappe.ready(function () {
		// Cards do Kanban → modal de detalhes
		document.querySelectorAll(".kanban-card").forEach((card) => {
			card.addEventListener("click", () => openFilaModal(card));
		});

		// Botão de vagas no header de cada coluna
		document.querySelectorAll(".kanban-column__vagas").forEach((btn) => {
			btn.addEventListener("click", () => openVagasModal(btn));
		});

		// Ações do modal de fila de espera
		document
			.getElementById("btnChamarAssociado")
			?.addEventListener("click", abrirConfirmarChamada);
		document.getElementById("btnAbrirFicha")?.addEventListener("click", abrirFicha);
		document
			.getElementById("btnRegistrarDesistencia")
			?.addEventListener("click", abrirConfirmarDesistencia);

		// Ações dos modais de confirmação
		document.getElementById("btnCancelarChamada")?.addEventListener("click", cancelarChamada);
		document.getElementById("btnConfirmarChamada")?.addEventListener("click", confirmarChamada);
		document
			.getElementById("btnCancelarDesistencia")
			?.addEventListener("click", cancelarDesistencia);
		document
			.getElementById("btnConfirmarDesistencia")
			?.addEventListener("click", confirmarDesistencia);

		// Botão "Fechar" dos dialogs (atributo data-dialog-close)
		document.addEventListener("click", (event) => {
			const closer = event.target.closest("[data-dialog-close]");
			if (closer) {
				const dlg = closer.closest("dialog");
				if (dlg && dlg.open) dlg.close();
			}
		});
	});
})();
