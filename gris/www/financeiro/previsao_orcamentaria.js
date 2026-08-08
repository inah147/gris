// Página /financeiro/previsao_orcamentaria — comparativo previsto × realizado (ECharts) e CRUD do orçamento.
(function () {
	'use strict';

	const API = 'gris.api.financeiro.previsao_orcamentaria';
	// Paleta Okabe-Ito (colorblind-safe) — ver skill gris-echarts-charts.
	const COR_PREVISTO = '#0072B2';
	const COR_REALIZADO = '#E69F00';
	const COR_RECEITA = '#009E73';
	const COR_DESPESA = '#D55E00';
	const CHART_IDS = [
		'chart-previsao-receitas',
		'chart-previsao-despesas',
		'chart-previsao-acumulado',
		'chart-previsao-categorias',
	];

	const wrapper = document.querySelector('.previsao-wrapper');
	if (!wrapper) return;

	const previsaoAtual = wrapper.dataset.previsao || '';
	const podeEditar = wrapper.dataset.canEdit === '1';

	function qs(id) { return document.getElementById(id); }

	function openDialog(id) {
		const dlg = qs(id);
		if (dlg && typeof dlg.showModal === 'function' && !dlg.open) dlg.showModal();
	}

	function closeDialog(id) {
		const dlg = qs(id);
		if (dlg && dlg.open) dlg.close();
	}

	// ----- helpers de componentes do design system -----

	// O select do basecoat guarda o valor num <input type="hidden"> interno; <select> nativo responde direto.
	function selectValue(id) {
		const root = qs(id);
		if (!root) return '';
		if (root.tagName === 'SELECT' || root.tagName === 'INPUT') return root.value || '';
		const input = root.querySelector('input[type="hidden"][name]');
		return input ? (input.value || '') : '';
	}

	function dpGetValue(rootId) {
		const root = qs(rootId);
		if (!root) return '';
		const input = root.querySelector('[data-datepicker-value]');
		return input ? (input.value || '') : '';
	}

	// Preenche o datepicker programaticamente (hidden input + rótulo visível).
	function dpSetValue(rootId, isoDate) {
		const root = qs(rootId);
		if (!root) return;
		const input = root.querySelector('[data-datepicker-value]');
		const labelEl = root.querySelector('[data-datepicker-label]');
		const placeholder = root.dataset.placeholder || 'Selecione uma data';
		if (input) input.value = isoDate || '';
		if (!labelEl) return;
		const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate || '');
		if (m) {
			labelEl.textContent = `${m[3]}/${m[2]}/${m[1]}`;
			labelEl.classList.remove('datepicker-trigger__label--placeholder');
		} else if (isoDate) {
			labelEl.textContent = isoDate;
			labelEl.classList.remove('datepicker-trigger__label--placeholder');
		} else {
			labelEl.textContent = placeholder;
			labelEl.classList.add('datepicker-trigger__label--placeholder');
		}
	}

	// ----- formatação -----

	function parseNumber(value) {
		const n = typeof value === 'number' ? value : parseFloat(value || 0);
		return Number.isFinite(n) ? n : 0;
	}

	function formatCurrency(value) {
		return parseNumber(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
	}

	function formatPercent(value) {
		if (value === null || value === undefined) return '—';
		return `${parseNumber(value).toFixed(1).replace('.', ',')}%`;
	}

	function isMobile() {
		return window.innerWidth < 640;
	}

	// ----- ECharts -----

	const ensureEcharts = () =>
		new Promise((resolve, reject) => {
			if (window.echarts) {
				resolve();
				return;
			}
			const existing = document.querySelector('script[data-gris-echarts="1"]');
			if (existing) {
				existing.addEventListener(
					'load',
					() => (window.echarts ? resolve() : reject(new Error('ECharts não disponível'))),
					{ once: true },
				);
				existing.addEventListener('error', () => reject(new Error('Falha ao carregar ECharts')), { once: true });
				return;
			}
			const script = document.createElement('script');
			script.dataset.grisEcharts = '1';
			script.src = '/assets/gris/vendor/echarts/echarts.min.js';
			script.onload = () => (window.echarts ? resolve() : reject(new Error('ECharts não disponível')));
			script.onerror = () => reject(new Error('Falha ao carregar ECharts'));
			document.head.appendChild(script);
		});

	function getChart(id) {
		const target = qs(id);
		if (!target || !window.echarts) return null;
		const existing = window.echarts.getInstanceByDom(target);
		if (existing) return existing;
		target.innerHTML = '';
		return window.echarts.init(target);
	}

	function disposeChart(id) {
		const target = qs(id);
		if (!target || !window.echarts) return;
		const existing = window.echarts.getInstanceByDom(target);
		if (existing) existing.dispose();
	}

	function setChartMessage(id, text) {
		disposeChart(id);
		const target = qs(id);
		if (target) target.innerHTML = `<div class="text-muted-foreground text-sm px-2 pt-3">${text}</div>`;
	}

	function baseOption({ yAxisName = '', axisPointer = 'shadow' } = {}) {
		return {
			aria: { enabled: true },
			color: [COR_PREVISTO, COR_REALIZADO],
			animationDuration: 400,
			animationDurationUpdate: 250,
			tooltip: {
				trigger: 'axis',
				confine: true,
				className: 'echarts-tooltip-modern',
				axisPointer: { type: axisPointer },
			},
			legend: { type: 'scroll', top: 4 },
			grid: {
				top: 58,
				left: 14,
				right: 14,
				bottom: isMobile() ? 66 : 38,
				containLabel: true,
			},
			xAxis: {
				type: 'category',
				axisTick: { alignWithLabel: true },
				axisLabel: { interval: 0, rotate: isMobile() ? 35 : 0, hideOverlap: true, fontSize: isMobile() ? 10 : 12 },
			},
			yAxis: { type: 'value', name: yAxisName },
		};
	}

	function tooltipMoeda(params) {
		const linhas = params
			.map((item) => `${item.marker}${item.seriesName}: <strong>${formatCurrency(item.value)}</strong>`)
			.join('<br/>');
		return `<strong>${params[0] ? params[0].axisValue : ''}</strong><br/>${linhas}`;
	}

	// Barras previsto × realizado por mês. A distinção não depende só da cor:
	// "Previsto" é contornado e "Realizado" é sólido.
	function renderPrevistoRealizado({ id, labels, previsto, realizado, corRealizado, emptyMessage }) {
		const temDado = (previsto || []).some((v) => parseNumber(v) !== 0) || (realizado || []).some((v) => parseNumber(v) !== 0);
		if (!labels || !labels.length || !temDado) {
			setChartMessage(id, emptyMessage || 'Sem dados no período.');
			return;
		}
		const chart = getChart(id);
		if (!chart) return;
		const base = baseOption({ yAxisName: 'R$' });
		chart.setOption(
			{
				...base,
				xAxis: { ...base.xAxis, data: labels },
				tooltip: { ...base.tooltip, formatter: tooltipMoeda },
				series: [
					{
						name: 'Previsto',
						type: 'bar',
						barMaxWidth: 26,
						itemStyle: {
							color: 'transparent',
							borderColor: COR_PREVISTO,
							borderWidth: 2,
							borderType: 'dashed',
						},
						emphasis: { focus: 'series' },
						data: (previsto || []).map(parseNumber),
					},
					{
						name: 'Realizado',
						type: 'bar',
						barMaxWidth: 26,
						itemStyle: { color: corRealizado || COR_REALIZADO },
						emphasis: { focus: 'series' },
						data: (realizado || []).map(parseNumber),
					},
				],
			},
			true,
		);
	}

	function acumular(valores) {
		let soma = 0;
		return (valores || []).map((v) => {
			soma += parseNumber(v);
			return Math.round(soma * 100) / 100;
		});
	}

	function renderAcumulado({ id, labels, resultadoPrevisto, resultadoRealizado, mesesDecorridos }) {
		if (!labels || !labels.length) {
			setChartMessage(id, 'Sem dados no período.');
			return;
		}
		const chart = getChart(id);
		if (!chart) return;
		const previstoAcum = acumular(resultadoPrevisto);
		// O realizado só faz sentido até o mês corrente; meses futuros ficam sem ponto.
		const realizadoAcum = acumular(resultadoRealizado).map((v, i) => (i < mesesDecorridos ? v : null));
		const base = baseOption({ yAxisName: 'R$', axisPointer: 'line' });
		chart.setOption(
			{
				...base,
				xAxis: { ...base.xAxis, data: labels },
				tooltip: { ...base.tooltip, axisPointer: { type: 'line' }, formatter: tooltipMoeda },
				series: [
					{
						name: 'Resultado previsto (acum.)',
						type: 'line',
						symbol: 'circle',
						symbolSize: 7,
						smooth: 0.2,
						lineStyle: { width: 3, type: 'dashed', color: COR_PREVISTO },
						itemStyle: { color: COR_PREVISTO },
						data: previstoAcum,
					},
					{
						name: 'Resultado realizado (acum.)',
						type: 'line',
						symbol: 'triangle',
						symbolSize: 9,
						smooth: 0.2,
						connectNulls: false,
						lineStyle: { width: 3, type: 'solid', color: COR_REALIZADO },
						itemStyle: { color: COR_REALIZADO },
						data: realizadoAcum,
					},
					{
						name: 'Equilíbrio',
						type: 'line',
						symbol: 'none',
						silent: true,
						lineStyle: { width: 1, type: 'dotted', color: '#000000' },
						data: labels.map(() => 0),
					},
				],
			},
			true,
		);
	}

	function renderCategorias({ id, linhas }) {
		const dados = (linhas || []).slice(0, 10);
		if (!dados.length) {
			setChartMessage(id, 'Nenhuma despesa prevista ou realizada por categoria.');
			return;
		}
		const chart = getChart(id);
		if (!chart) return;
		// Barras horizontais: eixo Y invertido para a maior categoria ficar no topo.
		const rotulos = dados.map((l) => l.rotulo).reverse();
		const previsto = dados.map((l) => parseNumber(l.previsto)).reverse();
		const realizado = dados.map((l) => parseNumber(l.realizado)).reverse();
		chart.setOption(
			{
				aria: { enabled: true },
				color: [COR_PREVISTO, COR_REALIZADO],
				tooltip: {
					trigger: 'axis',
					confine: true,
					className: 'echarts-tooltip-modern',
					axisPointer: { type: 'shadow' },
					formatter: tooltipMoeda,
				},
				legend: { type: 'scroll', top: 4 },
				grid: { top: 44, left: 14, right: 24, bottom: 24, containLabel: true },
				xAxis: { type: 'value', name: 'R$' },
				yAxis: { type: 'category', data: rotulos, axisLabel: { hideOverlap: true, width: 120, overflow: 'truncate' } },
				series: [
					{
						name: 'Previsto',
						type: 'bar',
						barMaxWidth: 16,
						itemStyle: { color: 'transparent', borderColor: COR_PREVISTO, borderWidth: 2, borderType: 'dashed' },
						data: previsto,
					},
					{
						name: 'Realizado',
						type: 'bar',
						barMaxWidth: 16,
						itemStyle: { color: COR_REALIZADO },
						data: realizado,
					},
				],
			},
			true,
		);
	}

	// ----- KPIs -----

	function setTexto(id, texto) {
		const el = qs(id);
		if (el) el.textContent = texto;
	}

	function renderKpis(totais) {
		setTexto('kpi-receitas-realizadas', formatCurrency(totais.receitas_realizadas));
		setTexto('kpi-receitas-previstas', `Previsto: ${formatCurrency(totais.receitas_previstas)}`);
		setTexto('kpi-receitas-execucao', `Execução até hoje: ${formatPercent(totais.execucao_receitas)}`);

		setTexto('kpi-despesas-realizadas', formatCurrency(totais.despesas_realizadas));
		setTexto('kpi-despesas-previstas', `Previsto: ${formatCurrency(totais.despesas_previstas)}`);
		setTexto('kpi-despesas-execucao', `Execução até hoje: ${formatPercent(totais.execucao_despesas)}`);

		setTexto('kpi-resultado-realizado', formatCurrency(totais.resultado_realizado));
		setTexto('kpi-resultado-previsto', `Previsto: ${formatCurrency(totais.resultado_previsto)}`);

		const desvio = parseNumber(totais.desvio_despesas);
		setTexto('kpi-desvio-despesas', formatCurrency(desvio));
		// Texto explícito além da cor, para não depender só do canal cromático.
		setTexto(
			'kpi-desvio-despesas-desc',
			desvio > 0 ? 'Acima do previsto' : desvio < 0 ? 'Abaixo do previsto' : 'Em linha com o previsto',
		);
		const el = qs('kpi-desvio-despesas');
		if (el) {
			el.classList.remove('previsao-kpi__value--alerta', 'previsao-kpi__value--positivo');
			if (desvio > 0) el.classList.add('previsao-kpi__value--alerta');
			else if (desvio < 0) el.classList.add('previsao-kpi__value--positivo');
		}
	}

	// ----- carregamento -----

	async function carregarComparativo() {
		if (!previsaoAtual) return;
		try {
			await ensureEcharts();
		} catch (e) {
			CHART_IDS.forEach((id) => setChartMessage(id, 'Não foi possível carregar os gráficos.'));
			return;
		}

		let dados;
		try {
			const r = await frappe.call({ method: `${API}.obter_comparativo`, args: { previsao: previsaoAtual } });
			dados = r.message;
		} catch (e) {
			CHART_IDS.forEach((id) => setChartMessage(id, 'Erro ao carregar os dados do comparativo.'));
			return;
		}
		if (!dados || !dados.success) {
			CHART_IDS.forEach((id) => setChartMessage(id, 'Sem dados para esta previsão.'));
			return;
		}

		renderKpis(dados.totais || {});

		const labels = dados.labels || [];
		const series = dados.series || {};

		renderPrevistoRealizado({
			id: 'chart-previsao-receitas',
			labels,
			previsto: series.receitas_previstas,
			realizado: series.receitas_realizadas,
			corRealizado: COR_RECEITA,
			emptyMessage: 'Nenhuma receita prevista ou realizada no período.',
		});
		renderPrevistoRealizado({
			id: 'chart-previsao-despesas',
			labels,
			previsto: series.despesas_previstas,
			realizado: series.despesas_realizadas,
			corRealizado: COR_DESPESA,
			emptyMessage: 'Nenhuma despesa prevista ou realizada no período.',
		});
		renderAcumulado({
			id: 'chart-previsao-acumulado',
			labels,
			resultadoPrevisto: series.resultado_previsto,
			resultadoRealizado: series.resultado_realizado,
			mesesDecorridos: dados.meses_decorridos || 0,
		});
		renderCategorias({
			id: 'chart-previsao-categorias',
			linhas: (dados.por_categoria || {}).despesas,
		});
	}

	let resizeTimer = null;
	window.addEventListener('resize', () => {
		if (resizeTimer) clearTimeout(resizeTimer);
		resizeTimer = setTimeout(() => {
			if (!window.echarts) return;
			CHART_IDS.forEach((id) => {
				const target = qs(id);
				if (!target) return;
				const chart = window.echarts.getInstanceByDom(target);
				if (chart) chart.resize();
			});
		}, 180);
	});

	// ----- navegação entre previsões -----

	const seletor = qs('previsao-seletor');
	if (seletor) {
		seletor.addEventListener('change', () => {
			const valor = selectValue('previsao-seletor');
			if (!valor || valor === previsaoAtual) return;
			window.location.href = `/financeiro/previsao_orcamentaria?previsao=${encodeURIComponent(valor)}`;
		});
	}

	// ----- CRUD -----

	// O frappe.call já exibe as mensagens de erro vindas do servidor; aqui só
	// complementamos com um alerta curto, útil para falhas sem mensagem (ex.: rede).
	function alertaErro(mensagem) {
		frappe.show_alert({ message: mensagem, indicator: 'red' }, 6);
	}

	function chamar(metodo, args) {
		return frappe.call({ method: `${API}.${metodo}`, args, type: 'POST' });
	}

	function formValores(formId) {
		const form = qs(formId);
		if (!form) return {};
		const fd = new FormData(form);
		const out = {};
		fd.forEach((valor, chave) => {
			out[chave] = typeof valor === 'string' ? valor.trim() : valor;
		});
		return out;
	}

	function abrirModalPrevisao(previsao) {
		const form = qs('formPrevisao');
		if (!form) return;
		form.reset();
		form.elements.name.value = previsao ? previsao.name : '';
		form.elements.titulo.value = previsao ? previsao.titulo : '';
		form.elements.exercicio.value = previsao ? previsao.exercicio : new Date().getFullYear();
		form.elements.status.value = previsao ? previsao.status : 'Rascunho';
		form.elements.centro_de_custo.value = previsao ? previsao.centro_de_custo || '' : '';
		form.elements.observacoes.value = previsao ? previsao.observacoes || '' : '';
		dpSetValue('previsao_data_inicio', previsao ? previsao.data_inicio : '');
		dpSetValue('previsao_data_fim', previsao ? previsao.data_fim : '');
		const titulo = document.querySelector('#modalPrevisao h2');
		if (titulo) titulo.textContent = previsao ? 'Editar Previsão' : 'Nova Previsão';
		openDialog('modalPrevisao');
	}

	async function salvarPrevisao(botao) {
		const valores = formValores('formPrevisao');
		const dataInicio = dpGetValue('previsao_data_inicio');
		const dataFim = dpGetValue('previsao_data_fim');
		if (!valores.titulo || !valores.exercicio || !dataInicio || !dataFim) {
			frappe.msgprint('Preencha título, exercício e o período da previsão.');
			return;
		}
		const args = {
			titulo: valores.titulo,
			exercicio: valores.exercicio,
			data_inicio: dataInicio,
			data_fim: dataFim,
			status: valores.status || 'Rascunho',
			centro_de_custo: valores.centro_de_custo || '',
			observacoes: valores.observacoes || '',
		};
		botao.disabled = true;
		try {
			const editando = valores.name;
			if (editando) args.name = editando;
			const r = await chamar(editando ? 'atualizar_previsao' : 'criar_previsao', args);
			const nome = r.message && r.message.name;
			closeDialog('modalPrevisao');
			window.location.href = `/financeiro/previsao_orcamentaria?previsao=${encodeURIComponent(nome || previsaoAtual)}`;
		} catch (e) {
			alertaErro('Não foi possível salvar a previsão.');
		} finally {
			botao.disabled = false;
		}
	}

	function alternarMesReferencia() {
		const wrapperMes = qs('itemMesWrapper');
		const distribuicao = qs('itemDistribuicao');
		if (!wrapperMes || !distribuicao) return;
		wrapperMes.classList.toggle('hidden', distribuicao.value !== 'Mês específico');
	}

	function abrirModalItem(botao) {
		const form = qs('formItem');
		if (!form) return;
		form.reset();
		const dados = botao ? botao.dataset : null;
		form.elements.item_name.value = dados ? dados.name : '';
		form.elements.tipo.value = dados ? dados.tipo : 'Despesa';
		form.elements.descricao.value = dados ? dados.descricao : '';
		form.elements.categoria.value = dados ? dados.categoria || '' : '';
		form.elements.centro_de_custo.value = dados ? dados.centro || '' : '';
		form.elements.valor_previsto.value = dados ? dados.valor : '';
		qs('itemDistribuicao').value = dados ? dados.distribuicao : 'Uniforme no período';
		form.elements.observacoes.value = dados ? dados.observacoes || '' : '';
		dpSetValue('item_mes_referencia', dados ? dados.mes || '' : '');
		alternarMesReferencia();
		const titulo = document.querySelector('#modalItem h2');
		if (titulo) titulo.textContent = dados ? 'Editar Item' : 'Novo Item';
		openDialog('modalItem');
	}

	async function salvarItem(botao) {
		const valores = formValores('formItem');
		const distribuicao = qs('itemDistribuicao').value;
		const mesReferencia = dpGetValue('item_mes_referencia');
		if (!valores.descricao || !valores.valor_previsto) {
			frappe.msgprint('Informe a descrição e o valor previsto do item.');
			return;
		}
		if (distribuicao === 'Mês específico' && !mesReferencia) {
			frappe.msgprint('Informe o mês de referência do item.');
			return;
		}
		botao.disabled = true;
		try {
			await chamar('salvar_item', {
				previsao: previsaoAtual,
				item_name: valores.item_name || '',
				tipo: valores.tipo,
				descricao: valores.descricao,
				categoria: valores.categoria || '',
				centro_de_custo: valores.centro_de_custo || '',
				distribuicao: distribuicao,
				mes_referencia: distribuicao === 'Mês específico' ? mesReferencia : '',
				valor_previsto: valores.valor_previsto,
				observacoes: valores.observacoes || '',
			});
			closeDialog('modalItem');
			window.location.reload();
		} catch (e) {
			alertaErro('Não foi possível salvar o item.');
		} finally {
			botao.disabled = false;
		}
	}

	function abrirModalDuplicar() {
		const form = qs('formDuplicar');
		if (!form) return;
		form.reset();
		dpSetValue('duplicar_data_inicio', '');
		dpSetValue('duplicar_data_fim', '');
		openDialog('modalDuplicar');
	}

	async function confirmarDuplicar(botao) {
		const valores = formValores('formDuplicar');
		const dataInicio = dpGetValue('duplicar_data_inicio');
		const dataFim = dpGetValue('duplicar_data_fim');
		if (!valores.titulo || !valores.exercicio || !dataInicio || !dataFim) {
			frappe.msgprint('Preencha título, exercício e o período da nova previsão.');
			return;
		}
		botao.disabled = true;
		try {
			const r = await chamar('duplicar_previsao', {
				name: previsaoAtual,
				titulo: valores.titulo,
				exercicio: valores.exercicio,
				data_inicio: dataInicio,
				data_fim: dataFim,
			});
			const nome = r.message && r.message.name;
			closeDialog('modalDuplicar');
			window.location.href = `/financeiro/previsao_orcamentaria?previsao=${encodeURIComponent(nome || '')}`;
		} catch (e) {
			alertaErro('Não foi possível duplicar a previsão.');
		} finally {
			botao.disabled = false;
		}
	}

	if (podeEditar) {
		const distribuicao = qs('itemDistribuicao');
		if (distribuicao) distribuicao.addEventListener('change', alternarMesReferencia);

		document.addEventListener('click', function (e) {
			if (e.target.closest('#btnNovaPrevisao')) {
				abrirModalPrevisao(null);
				return;
			}

			if (e.target.closest('#btnEditarPrevisao')) {
				frappe
					.call({ method: `${API}.obter_previsao`, args: { name: previsaoAtual } })
					.then((r) => abrirModalPrevisao(r.message))
					.catch(() => alertaErro('Não foi possível carregar a previsão.'));
				return;
			}

			const btnExcluirPrevisao = e.target.closest('#btnExcluirPrevisao');
			if (btnExcluirPrevisao) {
				frappe.confirm('Excluir esta previsão e todos os seus itens?', async () => {
					try {
						await chamar('excluir_previsao', { name: previsaoAtual });
						window.location.href = '/financeiro/previsao_orcamentaria';
					} catch (err) {
						alertaErro('Não foi possível excluir a previsão.');
					}
				});
				return;
			}

			if (e.target.closest('#btnDuplicarPrevisao')) {
				abrirModalDuplicar();
				return;
			}

			if (e.target.closest('#btnNovoItem')) {
				abrirModalItem(null);
				return;
			}

			const btnEditarItem = e.target.closest('.previsao-item-editar');
			if (btnEditarItem) {
				abrirModalItem(btnEditarItem);
				return;
			}

			const btnExcluirItem = e.target.closest('.previsao-item-excluir');
			if (btnExcluirItem) {
				const descricao = btnExcluirItem.dataset.descricao || 'este item';
				frappe.confirm(`Excluir "${descricao}" do orçamento?`, async () => {
					try {
						await chamar('excluir_item', { previsao: previsaoAtual, item_name: btnExcluirItem.dataset.name });
						window.location.reload();
					} catch (err) {
						alertaErro('Não foi possível excluir o item.');
					}
				});
				return;
			}

			const salvarPrevisaoBtn = e.target.closest('[data-action="salvar-previsao"]');
			if (salvarPrevisaoBtn) {
				salvarPrevisao(salvarPrevisaoBtn);
				return;
			}

			const salvarItemBtn = e.target.closest('[data-action="salvar-item"]');
			if (salvarItemBtn) {
				salvarItem(salvarItemBtn);
				return;
			}

			const duplicarBtn = e.target.closest('[data-action="confirmar-duplicar"]');
			if (duplicarBtn) {
				confirmarDuplicar(duplicarBtn);
			}
		});
	}

	carregarComparativo();
})();
