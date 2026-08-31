// Contribuições mensais — gráficos ECharts, filtros da tabela e detalhe por contribuinte.
(function () {
	"use strict";

	const CHART_COLORS = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#56B4E9", "#CC79A7"];
	const LINHAS_POR_PAGINA = 15;

	let assocAtual = null;
	let paginaAtual = 1;

	// ─────────────────────────── utilitários ───────────────────────────

	function parseNumber(valor) {
		const numero = typeof valor === "number" ? valor : parseFloat(valor || 0);
		return Number.isFinite(numero) ? numero : 0;
	}

	function formatarMoeda(valor) {
		return parseNumber(valor).toLocaleString("pt-BR", {
			minimumFractionDigits: 2,
			maximumFractionDigits: 2,
		});
	}

	function formatarMoedaCompleta(valor) {
		return parseNumber(valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
	}

	function formatarPercentual(valor) {
		return `${parseNumber(valor).toFixed(1).replace(".", ",")}%`;
	}

	function formatarData(iso) {
		if (!iso) return "—";
		const partes = String(iso).split("-");
		if (partes.length !== 3) return iso;
		return `${partes[2]}/${partes[1]}/${partes[0]}`;
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

	function showToast(mensagem, indicador) {
		const categorias = { green: "success", red: "error", orange: "warning", blue: "info" };
		document.dispatchEvent(
			new CustomEvent("basecoat:toast", {
				detail: {
					config: {
						category: categorias[indicador] || "info",
						title: mensagem,
						duration: 3000,
					},
				},
			})
		);
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

	// ─────────────────────────── detalhe ───────────────────────────

	function getDialog() {
		return document.getElementById("detalheModal");
	}

	function setTexto(id, valor) {
		const elemento = document.getElementById(id);
		if (elemento) elemento.textContent = valor;
	}

	function renderMeses(assoc) {
		const tbody = document.getElementById("detalheMeses");
		if (!tbody) return;
		tbody.innerHTML = "";

		(assoc.linhas || []).forEach((linha) => {
			const tr = document.createElement("tr");
			let marca = "";
			if (linha.usou_credito) {
				marca = ' <span class="text-xs text-muted-foreground">(crédito)</span>';
			} else if (linha.quitacao_retroativa) {
				marca = ' <span class="text-xs text-muted-foreground">(pago depois)</span>';
			}
			// Motivo aparece nos meses de carência de registro; "atraso" avisa que o
			// mês passou a valer o valor cheio do vencido.
			const motivo = linha.motivo
				? ` <span class="text-xs text-muted-foreground">(${escapeHtml(
						linha.motivo
				  )})</span>`
				: "";
			const marcaAtraso = linha.em_atraso
				? ' <span class="text-xs text-muted-foreground">(atraso)</span>'
				: "";
			tr.innerHTML = [
				`<td class="whitespace-nowrap">${escapeHtml(linha.rotulo)}</td>`,
				`<td><span class="badge contrib-badge contrib-badge--${escapeHtml(
					linha.status_slug
				)}">${escapeHtml(linha.status)}</span>${marca}${motivo}</td>`,
				`<td class="text-right whitespace-nowrap contrib-num">R$ ${formatarMoeda(
					linha.esperado
				)}${marcaAtraso}</td>`,
				`<td class="text-right whitespace-nowrap contrib-num">R$ ${formatarMoeda(
					linha.recebido
				)}</td>`,
			].join("");
			tbody.appendChild(tr);
		});
	}

	function renderTransacoes(transacoes) {
		const tbody = document.getElementById("detalheTransacoes");
		if (!tbody) return;
		tbody.innerHTML = "";

		if (!transacoes || !transacoes.length) {
			tbody.innerHTML =
				'<tr><td colspan="4" class="text-sm text-muted-foreground">Nenhuma transação de contribuição no período.</td></tr>';
			return;
		}

		transacoes.forEach((transacao) => {
			const tr = document.createElement("tr");
			const url = `/financeiro/detalhe_extrato?name=${encodeURIComponent(transacao.name)}`;
			tr.innerHTML = [
				`<td class="whitespace-nowrap">${escapeHtml(formatarData(transacao.data))}</td>`,
				`<td>${escapeHtml(transacao.descricao || "—")}</td>`,
				`<td class="text-right whitespace-nowrap contrib-num">R$ ${formatarMoeda(
					transacao.valor
				)}</td>`,
				`<td class="text-right"><a class="btn-sm-outline" href="${url}">Abrir</a></td>`,
			].join("");
			tbody.appendChild(tr);
		});
	}

	function carregarTransacoes(assoc) {
		const tbody = document.getElementById("detalheTransacoes");
		if (tbody) {
			tbody.innerHTML =
				'<tr><td colspan="4" class="text-sm text-muted-foreground">Carregando…</td></tr>';
		}

		frappe
			.call({
				method: "gris.api.financeiro.contribuicoes.get_extrato_do_associado",
				args: { associado: assoc.id, meses: window.contribMeses },
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				renderTransacoes(dados.transacoes);
			})
			.catch(() => {
				if (tbody) {
					tbody.innerHTML =
						'<tr><td colspan="4" class="text-sm text-muted-foreground">Não foi possível carregar as transações.</td></tr>';
				}
			});
	}

	function atualizarAcoesCadastro(assoc) {
		const btnRealizado = document.getElementById("btnCadastroRealizado");
		const btnCancelado = document.getElementById("btnCadastroCancelado");
		if (btnRealizado)
			btnRealizado.classList.toggle("hidden", assoc.acao_cadastro !== "Cadastrar");
		if (btnCancelado) {
			btnCancelado.classList.toggle("hidden", assoc.status_cobranca !== "Ativo");
		}
	}

	function mostrarDetalhes(linha) {
		const assoc = JSON.parse(linha.getAttribute("data-assoc"));
		assocAtual = assoc;

		const dialog = getDialog();
		const titulo = dialog ? dialog.querySelector("h2#detalheModal-title") : null;
		if (titulo) titulo.textContent = assoc.nome || "Detalhes do contribuinte";

		// Desfaz edições em aberto de um contribuinte anterior antes de preencher os campos:
		// os spans só existem depois que os formulários inline saem da tela.
		cancelarEdicaoValor();
		restaurarCobranca();

		setTexto("detalheValor", formatarMoeda(assoc.esperado_mensal));
		setTexto("detalheRecebido", formatarMoeda(assoc.total_recebido));
		setTexto("detalheCredito", formatarMoeda(assoc.credito));

		renderMeses(assoc);
		atualizarAcoesCadastro(assoc);
		carregarTransacoes(assoc);
		carregarCobranca(assoc);

		if (dialog && typeof dialog.showModal === "function" && !dialog.open) {
			dialog.showModal();
		}
	}

	// ─────────────────────────── ações de gestão ───────────────────────────

	function semPermissao() {
		if (window.canManageContrib) return false;
		showToast("Sem permissão para esta ação.", "red");
		return true;
	}

	function chamarApi(metodo, args, mensagemSucesso) {
		frappe
			.call({ method: metodo, args: args, freeze: true })
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				if (!dados.ok) {
					showToast("Não foi possível concluir a ação.", "red");
					return;
				}
				showToast(mensagemSucesso, "green");
				// A apuração é calculada no servidor: recarregar mantém tela e números coerentes.
				window.setTimeout(() => window.location.reload(), 600);
			})
			.catch(() => showToast("Erro ao executar a ação.", "red"));
	}

	function alterarValor() {
		if (semPermissao() || !assocAtual) return;
		const container = document.getElementById("valorContainer");
		const acoes = document.getElementById("acoesValor");
		if (!container || !acoes || container.querySelector("input")) return;

		container.classList.remove("hidden");
		container.innerHTML = `
			<div class="field">
				<label class="label" for="inputNovoValor">Novo valor esperado por mês (R$)</label>
				<input type="number" min="0" step="0.01" id="inputNovoValor" class="input contrib-input-valor"
					value="${parseNumber(assocAtual.esperado_mensal)}" />
			</div>
		`;
		acoes.innerHTML = `
			<button type="button" class="btn-sm-primary" data-acao="salvar-valor">Salvar</button>
			<button type="button" class="btn-sm-outline" data-acao="cancelar-valor">Cancelar</button>
		`;
	}

	function cancelarEdicaoValor() {
		const container = document.getElementById("valorContainer");
		const acoes = document.getElementById("acoesValor");
		if (container) {
			container.innerHTML = "";
			container.classList.add("hidden");
		}
		if (acoes && window.canManageContrib) {
			acoes.innerHTML =
				'<button type="button" id="btnAlterarValor" class="btn-sm-outline" data-acao="alterar-valor">Alterar valor</button>';
		}
	}

	function salvarNovoValor() {
		if (semPermissao() || !assocAtual) return;
		const input = document.getElementById("inputNovoValor");
		if (!input) return;
		const novoValor = parseFloat(input.value);
		if (!Number.isFinite(novoValor) || novoValor < 0) {
			showToast("Informe um valor válido.", "orange");
			return;
		}
		frappe
			.call({
				method: "gris.api.financeiro.monthly_payments.update_contribution_value",
				args: { associate_id: assocAtual.id, new_value: novoValor },
				freeze: true,
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				if (!dados.ok) {
					showToast("Não foi possível salvar o valor.", "red");
					return;
				}
				showToast("Valor atualizado", "green");
				window.setTimeout(() => window.location.reload(), 600);
			})
			.catch(() => showToast("Erro ao salvar valor.", "red"));
	}

	function cadastroRealizado() {
		if (semPermissao() || !assocAtual) return;
		chamarApi(
			"gris.api.financeiro.monthly_payments.activate_billing_status",
			{ associate_id: assocAtual.id },
			"Cobrança ativada"
		);
	}

	function cadastroCancelado() {
		if (semPermissao() || !assocAtual) return;
		chamarApi(
			"gris.api.financeiro.monthly_payments.deactivate_billing_status",
			{ associate_id: assocAtual.id },
			"Cobrança inativada"
		);
	}

	function editarCobranca() {
		if (semPermissao() || !assocAtual) return;
		const container = document.getElementById("cobrancaContainer");
		const acoes = document.getElementById("acoesCobranca");
		if (!container || !acoes || container.querySelector("input")) return;

		const email = assocAtual.email_cobranca || "";
		const telefone = assocAtual.telefone_cobranca || "";
		const alvo = container.querySelector(".flex-1");
		if (alvo) {
			alvo.innerHTML = `
				<div class="field">
					<label class="label" for="inputEmailCobranca">E-mail de cobrança</label>
					<input type="email" id="inputEmailCobranca" class="input" value="${escapeHtml(
						email
					)}" placeholder="email@exemplo.com" />
				</div>
				<div class="field">
					<label class="label" for="inputFoneCobranca">Telefone de cobrança</label>
					<input type="text" id="inputFoneCobranca" class="input" value="${escapeHtml(
						telefone
					)}" placeholder="(xx) xxxxx-xxxx" />
				</div>
			`;
		}
		acoes.innerHTML = `
			<button type="button" class="btn-sm-primary" data-acao="salvar-cobranca">Salvar</button>
			<button type="button" class="btn-sm-outline" data-acao="cancelar-cobranca">Cancelar</button>
		`;
	}

	function restaurarCobranca() {
		const container = document.getElementById("cobrancaContainer");
		const acoes = document.getElementById("acoesCobranca");
		if (container && assocAtual) {
			const alvo = container.querySelector(".flex-1");
			if (alvo) {
				alvo.innerHTML = `
					<div class="text-sm"><strong>E-mail de cobrança:</strong> <span id="emailCobranca">${escapeHtml(
						assocAtual.email_cobranca || "—"
					)}</span></div>
					<div class="text-sm"><strong>Telefone de cobrança:</strong> <span id="foneCobranca">${escapeHtml(
						assocAtual.telefone_cobranca || "—"
					)}</span></div>
				`;
			}
		}
		if (acoes) {
			acoes.innerHTML =
				'<button type="button" id="btnEditarCobranca" class="btn-sm-outline" data-acao="editar-cobranca">Editar cobrança</button>';
		}
	}

	function salvarDadosCobranca() {
		if (semPermissao() || !assocAtual) return;
		const email = document.getElementById("inputEmailCobranca")?.value.trim() || "";
		const telefone = document.getElementById("inputFoneCobranca")?.value.trim() || "";

		frappe
			.call({
				method: "gris.api.financeiro.monthly_payments.update_billing_contacts",
				args: { associate_id: assocAtual.id, email: email, phone: telefone },
				freeze: true,
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				if (!dados.ok) {
					showToast("Não foi possível salvar os dados de cobrança.", "red");
					return;
				}
				assocAtual.email_cobranca = dados.email;
				assocAtual.telefone_cobranca = dados.phone;
				restaurarCobranca();
				showToast("Dados de cobrança atualizados", "green");
			})
			.catch(() => showToast("Erro ao salvar dados de cobrança.", "red"));
	}

	// ─────────────────────────── cobrança InfinitePay ───────────────────────────

	function elementosCobranca() {
		return {
			secao: document.getElementById("cobrancaInfinitepay"),
			pendentes: document.getElementById("cobrancaPendentes"),
			acoes: document.getElementById("cobrancaAcoes"),
			total: document.getElementById("cobrancaTotal"),
			emitidas: document.getElementById("cobrancaEmitidas"),
		};
	}

	function competenciasMarcadas() {
		const marcadas = document.querySelectorAll(".contrib-cobranca__competencia:checked");
		return Array.prototype.map.call(marcadas, (item) => item.value);
	}

	function atualizarTotalCobranca() {
		const { total } = elementosCobranca();
		if (!total) return;
		const marcadas = document.querySelectorAll(".contrib-cobranca__competencia:checked");
		const soma = Array.prototype.reduce.call(
			marcadas,
			(acumulado, item) => acumulado + parseNumber(item.getAttribute("data-valor")),
			0
		);
		total.textContent = marcadas.length ? `Total: R$ ${formatarMoeda(soma)}` : "";
	}

	function renderPendentes(pendentes) {
		const { pendentes: caixa, acoes } = elementosCobranca();
		if (!caixa) return;

		if (!pendentes || !pendentes.length) {
			caixa.innerHTML =
				'<p class="m-0 text-sm text-muted-foreground">Nenhuma competência em aberto no período apurado.</p>';
			if (acoes) acoes.classList.add("hidden");
			return;
		}

		caixa.innerHTML = pendentes
			.map(
				(pendente) => `
				<label class="contrib-cobranca__item">
					<input type="checkbox" class="contrib-cobranca__competencia" checked
						value="${escapeHtml(pendente.ym)}" data-valor="${escapeHtml(pendente.valor)}" />
					<span>${escapeHtml(pendente.rotulo)}</span>
					<span class="badge contrib-badge contrib-badge--${escapeHtml(pendente.status_slug)}">${escapeHtml(
					pendente.status
				)}</span>
					<span class="contrib-num text-muted-foreground">R$ ${formatarMoeda(pendente.valor)}</span>
				</label>`
			)
			.join("");

		if (acoes) acoes.classList.remove("hidden");
		atualizarTotalCobranca();
	}

	function renderCobrancasEmitidas(cobrancas) {
		const { emitidas } = elementosCobranca();
		if (!emitidas) return;

		const pendentesComLink = (cobrancas || []).filter(
			(cobranca) => cobranca.status === "Pendente" && cobranca.link_pagamento
		);
		if (!pendentesComLink.length) {
			emitidas.innerHTML = "";
			return;
		}

		emitidas.innerHTML = `
			<h4 class="text-xs font-semibold text-muted-foreground mb-2">Cobranças em aberto</h4>
			${pendentesComLink
				.map(
					(cobranca) => `
				<div class="contrib-cobranca__emitida">
					<a href="${escapeHtml(cobranca.link_pagamento)}" target="_blank" rel="noopener noreferrer">
						${escapeHtml(cobranca.name)}
					</a>
					<span class="text-xs text-muted-foreground">${escapeHtml(cobranca.competencias || "")}</span>
					<button type="button" class="btn-sm-outline" data-acao="reenviar-cobranca"
						data-cobranca="${escapeHtml(cobranca.name)}">Reenviar no WhatsApp</button>
				</div>`
				)
				.join("")}`;
	}

	function carregarCobranca(assoc) {
		const { secao, pendentes, acoes, emitidas } = elementosCobranca();
		if (!secao) return;

		if (pendentes) {
			pendentes.innerHTML = '<p class="m-0 text-sm text-muted-foreground">Carregando…</p>';
		}
		if (acoes) acoes.classList.add("hidden");
		if (emitidas) emitidas.innerHTML = "";

		frappe
			.call({
				method: "gris.api.financeiro.cobranca_contribuicao.get_cobranca_do_associado",
				args: { associado: assoc.id, meses: window.contribMeses },
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				renderPendentes(dados.pendentes);
				renderCobrancasEmitidas(dados.cobrancas);
			})
			.catch(() => {
				if (pendentes) {
					pendentes.innerHTML =
						'<p class="m-0 text-sm text-muted-foreground">Não foi possível carregar as competências em aberto.</p>';
				}
			});
	}

	function relatarEnvio(whatsapp) {
		if (!whatsapp) return;
		if (whatsapp.enviado) {
			showToast(`Link enviado no WhatsApp para ${whatsapp.telefone}.`, "green");
			return;
		}
		// A cobrança foi criada mesmo assim: o gestor ainda pode copiar o link da lista.
		showToast(`Cobrança criada, mas o WhatsApp falhou: ${whatsapp.motivo}`, "orange");
	}

	function gerarCobranca(enviarWhatsapp) {
		if (semPermissao() || !assocAtual) return;
		const competencias = competenciasMarcadas();
		if (!competencias.length) {
			showToast("Selecione ao menos uma competência para cobrar.", "orange");
			return;
		}

		frappe
			.call({
				method: "gris.api.financeiro.cobranca_contribuicao.gerar_cobranca",
				args: {
					associado: assocAtual.id,
					competencias: competencias.join(","),
					enviar_whatsapp: enviarWhatsapp ? 1 : 0,
					meses: window.contribMeses,
				},
				freeze: true,
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				if (!dados.success) {
					showToast("Não foi possível gerar a cobrança.", "red");
					return;
				}
				if (!enviarWhatsapp) showToast("Link de pagamento gerado.", "green");
				relatarEnvio(dados.whatsapp);
				carregarCobranca(assocAtual);
			})
			.catch(() => showToast("Erro ao gerar a cobrança.", "red"));
	}

	function reenviarCobranca(elemento) {
		if (semPermissao()) return;
		const name = elemento.getAttribute("data-cobranca");
		if (!name) return;

		frappe
			.call({
				method: "gris.api.financeiro.cobranca_contribuicao.enviar_cobranca_whatsapp",
				args: { name: name },
				freeze: true,
			})
			.then((resposta) => {
				const dados = (resposta && resposta.message) || {};
				relatarEnvio(dados.whatsapp);
			})
			.catch(() => showToast("Erro ao reenviar a cobrança.", "red"));
	}

	// ─────────────────────────── ligações ───────────────────────────

	const ACOES = {
		detalhes: (elemento) => mostrarDetalhes(elemento.closest("tr")),
		"alterar-valor": alterarValor,
		"salvar-valor": salvarNovoValor,
		"cancelar-valor": cancelarEdicaoValor,
		"editar-cobranca": editarCobranca,
		"salvar-cobranca": salvarDadosCobranca,
		"cancelar-cobranca": restaurarCobranca,
		"cadastro-realizado": cadastroRealizado,
		"cadastro-cancelado": cadastroCancelado,
		"cobrar-whatsapp": () => gerarCobranca(true),
		"cobrar-link": () => gerarCobranca(false),
		"reenviar-cobranca": reenviarCobranca,
	};

	function init() {
		initGraficos();

		const filtroNome = document.getElementById("filtroAssociado");
		if (filtroNome) filtroNome.addEventListener("input", aplicarFiltros);

		// O macro `select` dispara `change` no próprio componente (não no input hidden,
		// que é filho dele) e só então atualiza o valor do hidden.
		const filtroSituacao = document.getElementById("filtroSituacao");
		if (filtroSituacao) filtroSituacao.addEventListener("change", aplicarFiltros);

		document.addEventListener("change", (evento) => {
			if (evento.target.classList.contains("contrib-cobranca__competencia")) {
				atualizarTotalCobranca();
			}
		});

		document.addEventListener("click", (evento) => {
			const alvo = evento.target.closest("[data-acao]");
			if (!alvo) return;
			const acao = ACOES[alvo.getAttribute("data-acao")];
			if (!acao) return;
			evento.preventDefault();
			acao(alvo);
		});

		atualizarPaginacao();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
