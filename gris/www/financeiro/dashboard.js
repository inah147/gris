// Dashboard Financeiro - gráficos Entradas x Saídas (barras) e Resultado (linha) separados
(async function(){
	const ensureCharts = () => new Promise((resolve, reject) => {
		if (window.frappe && frappe.Chart) return resolve();
		const s = document.createElement('script');
		s.src = '/assets/frappe/node_modules/frappe-charts/dist/frappe-charts.umd.js';
		s.onload = () => {
			try { const ns = window['frappe-charts']; if (ns && ns.Chart) frappe.Chart = ns.Chart; } catch(e) {}
			if (frappe.Chart) return resolve();
			reject(new Error('frappe.Chart não disponível.'));
		};
		s.onerror = () => reject(new Error('Falha ao carregar frappe-charts.'));
		document.head.appendChild(s);
	});

	let entradasSaidasChart = null;
	let resultadoChart = null;
	// Removidos gráficos separados Ordinárias / Extraordinárias (uso agora filtro global)
	let entradasCreditoChart = null;
	let currentFilters = {}; // {categoria, instituicao, carteira, centro_de_custo}

	frappe.ready(async () => {
		const form = document.getElementById('fin-dashboard-filters');
		if (form){
			form.addEventListener('submit', async (e) => {
				e.preventDefault();
				currentFilters = getFormFilters(form);
				await refreshCharts();
			});
			form.addEventListener('reset', async () => {
				setTimeout(async () => { currentFilters = {}; await refreshCharts(); }, 0);
			});
		}
		await refreshCharts();
	});

	function getFormFilters(form){
		const fd = new FormData(form);
		const out = {};
		['categoria','instituicao','carteira','centro_de_custo','ordinaria_extraordinaria'].forEach(k=>{
			const v = (fd.get(k)||'').trim();
			if (v) out[k]=v;
		});
		return out;
	}

	async function refreshCharts(){
		try {
			await ensureCharts();
			await atualizarCardInadimplencia();
			await renderEntradasSaidas();
			await renderResultado();
			await renderEntradasCredito();
			await renderEntradasCreditoCategoria();
			await renderEntradasCreditoCentro();
			await renderEntradasCreditoTipo();
			await renderSaidasDebito();
			await renderSaidasDebitoCategoria();
			await renderSaidasDebitoCentro();
			await renderSaidasDebitoTipo();
			await renderContribuicoesMensaisStatus();
			await renderContribuicoesMensaisInadimplencia();
		} catch(e){
			console.warn('Erro ao atualizar gráficos', e);
		}
	}

	// Atualiza card Inadimplência Histórica (últimos 6 meses)
	async function atualizarCardInadimplencia(){
		const el = document.getElementById('card-inadimplencia');
		const desc = document.getElementById('card-inadimplencia-desc');
		if (!el) return;
		el.textContent = '--';
		try {
			const resp = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_inadimplencia_historica_6m' });
			const data = resp.message || resp || {};
			if (typeof data.percent === 'number') {
				el.textContent = data.percent.toFixed(2).replace('.', ',') + '%';
				if (desc && typeof data.atrasado === 'number' && typeof data.total === 'number') {
					desc.textContent = `Últimos 12 meses • ${data.atrasado}/${data.total} associados`; // distintos
				}
			} else {
				el.textContent = '0,00%';
			}
		} catch(e){
			el.textContent = 'Erro';
		}
	}

	async function fetchData(extraArgs){
		const args = Object.assign({}, currentFilters, extraArgs||{});
		const r = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_entradas_saidas_mensal', args });
		return r.message || {};
	}

	async function renderEntradasSaidas(){
		const target = document.getElementById('chart-entradas-saidas-mensal');
		if (!target) return;
		if (!entradasSaidasChart) {
			// primeira carga
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		}
		const data = await fetchData();
		if (!data.labels || !data.labels.length){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>';
			return;
		}
		// Remover dataset Resultado desta coleção para este gráfico
		const onlyBars = {
			labels: data.labels.slice(),
			datasets: data.datasets.filter(d => !/Resultado/i.test(d.name))
		};
		const isMobile = window.innerWidth < 640;
		if (!entradasSaidasChart) {
			// cria
			target.innerHTML = '';
			entradasSaidasChart = new frappe.Chart(target, {
				title: 'Entradas x Saídas (Últimos 12 meses)',
				type: 'bar',
				data: onlyBars,
				height: isMobile ? 300 : 320,
				barOptions: { stacked: false, spaceRatio: 0.4 },
				axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
				tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
			});
			if (isMobile) rotateXAxisLabels(target, -35);
		} else {
			// atualiza datasets e relança draw
			try {
				entradasSaidasChart.data = onlyBars; // atribui novo objeto
				if (typeof entradasSaidasChart.draw === 'function') entradasSaidasChart.draw();
			} catch(e){
				console.warn('Falha ao atualizar gráfico, recriando...', e);
				try { target.innerHTML=''; } catch(_){}
				entradasSaidasChart = new frappe.Chart(target, {
					title: 'Entradas x Saídas (Últimos 12 meses)',
					type: 'bar',
					data: onlyBars,
					height: isMobile ? 300 : 320,
					barOptions: { stacked: false, spaceRatio: 0.4 },
					axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
					tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
				});
				if (isMobile) rotateXAxisLabels(target, -35);
			}
		}
	}

	let entradasCreditoTipoChart = null;
	async function renderEntradasCreditoTipo(){
		const target = document.getElementById('chart-entradas-credito-tipo-mensal');
		if (!target) return;
		if (!entradasCreditoTipoChart) target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		// Remover ordinaria_extraordinaria do filtro (cada tipo vira dataset)
		const { ordinaria_extraordinaria, ...filtersSemTipo } = currentFilters;
		const resp = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_entradas_credito_mensal_por_tipo', args: filtersSemTipo });
		const msg = resp.message || resp;
		const payload = msg || {};
		if (!payload.labels || !payload.labels.length){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>';
			return;
		}
		if (!payload.datasets || !payload.datasets.length){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>';
			return;
		}
		const palette = ['#0d9488','#dc2626','#6366f1','#f59e0b'];
		payload.datasets.forEach((ds,i)=>{ ds.color = palette[i % palette.length]; });
		const stackedData = { labels: payload.labels.slice(), datasets: payload.datasets };
		const isMobile = window.innerWidth < 640;
		try {
			if (!entradasCreditoTipoChart){
				target.innerHTML = '';
				entradasCreditoTipoChart = new frappe.Chart(target, {
					title: 'Entradas por Tipo (Crédito) - Empilhado',
					type: 'bar',
					data: stackedData,
					height: isMobile ? 340 : 360,
					barOptions: { stacked: true, spaceRatio: 0.4 },
					axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
					tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
				});
				if (isMobile) rotateXAxisLabels(target, -35);
			} else {
				entradasCreditoTipoChart.data = stackedData;
				if (typeof entradasCreditoTipoChart.draw === 'function') entradasCreditoTipoChart.draw();
			}
		} catch(e){ console.warn('Falha gráfico Entradas Tipo', e); }
	}

	let entradasCreditoCentroChart = null;
	async function renderEntradasCreditoCentro(){
		const target = document.getElementById('chart-entradas-credito-centro-mensal');
		if (!target) return;
		if (!entradasCreditoCentroChart) target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		// Remover centro_de_custo do filtro (cada centro vira dataset)
		const { centro_de_custo, ...filtersSemCentro } = currentFilters;
		const resp = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_entradas_credito_mensal_por_centro_custo', args: filtersSemCentro });
		const msg = resp.message || resp;
		const payload = msg || {};
		if (!payload.labels || !payload.labels.length){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>';
			return;
		}
		if (!payload.datasets || !payload.datasets.length){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>';
			return;
		}
		const palette = ['#2563eb','#059669','#db2777','#d97706','#10b981','#7c3aed','#0ea5e9','#dc2626','#f59e0b','#0891b2'];
		payload.datasets.forEach((ds,i)=>{ ds.color = palette[i % palette.length]; });
		const stackedData = { labels: payload.labels.slice(), datasets: payload.datasets };
		const isMobile = window.innerWidth < 640;
		try {
			if (!entradasCreditoCentroChart){
				target.innerHTML = '';
				entradasCreditoCentroChart = new frappe.Chart(target, {
					title: 'Entradas por Centro de Custo (Crédito) - Empilhado',
					type: 'bar',
					data: stackedData,
					height: isMobile ? 340 : 360,
					barOptions: { stacked: true, spaceRatio: 0.4 },
					axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
					tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
				});
				if (isMobile) rotateXAxisLabels(target, -35);
			} else {
				entradasCreditoCentroChart.data = stackedData;
				if (typeof entradasCreditoCentroChart.draw === 'function') entradasCreditoCentroChart.draw();
			}
		} catch(e){ console.warn('Falha gráfico Entradas Centro Custo', e); }
	}

	async function renderResultado(){
		const target = document.getElementById('chart-resultado-mensal');
		if (!target) return;
		// Sempre recriar para evitar estados internos inconsistentes após filtros
		target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		const data = await fetchData();
		if (!data.labels || !data.labels.length){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>';
			return;
		}
		const dsResultado = data.datasets.find(d => /Resultado/i.test(d.name));
		if (!dsResultado){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados de resultado.</div>';
			return;
		}
		// Coerção explícita para números (evita string -> path invisível)
		const coercedVals = (dsResultado.values || []).map(v => typeof v === 'number' ? v : parseFloat(v)||0);
		const allZero = coercedVals.every(v => v === 0);
		const cleanResultado = { name: dsResultado.name || 'Resultado', values: coercedVals, color: '#2563eb' };
		const lineData = { labels: data.labels.slice(), datasets: [ cleanResultado ], yMarkers: [ { label: 'Zero', value: 0, options: { labelPos: 'left' } } ] };
		const isMobile = window.innerWidth < 640;
		// Recriação sempre
		target.innerHTML = '';
		resultadoChart = new frappe.Chart(target, {
			title: 'Resultado Mensal (Entradas - Saídas)',
			type: 'line',
			data: lineData,
			height: isMobile ? 300 : 320,
			lineOptions: { regionFill: 1, hideDots: false, dotSize: 5 },
			axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
			tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
		});
		if (isMobile) rotateXAxisLabels(target, -35);
		// Se todos os valores forem zero, adiciona aviso sutil e evita impressão de linha invisível branca
		if (allZero) {
			const note = document.createElement('div');
			note.className = 'small text-muted mt-1';
			note.textContent = 'Sem variação (todos os meses = 0)';
			target.appendChild(note);
		}
		// Fallback: se por algum motivo o path não renderizar, desenha pontos manualmente
		requestAnimationFrame(()=>{
			const svg = target.querySelector('svg');
			if (!svg) return;
			const existingPath = svg.querySelector('path.line-graph-path, .chart-lines path');
			if (existingPath) return; // linha presente
			try {
				// calcular escala aproximada a partir de y e largura do gráfico
				const yAxisTicks = svg.querySelectorAll('.y.axis text, .chart-axis.y text');
				let minY = 0, maxY = 0;
				const vals = coercedVals;
				if (vals.length){
					minY = Math.min(...vals);
					maxY = Math.max(...vals);
					if (minY === maxY) { maxY = minY + 1; }
				}
				const plotArea = svg.querySelector('g.chart-group') || svg;
				const bbox = plotArea.getBBox();
				const h = bbox.height || 1;
				const w = bbox.width || 1;
				coercedVals.forEach((v,i)=>{
					const cx = bbox.x + (w * (i/(coercedVals.length-1 || 1)));
					const ratio = (v - minY)/(maxY - minY);
					const cy = bbox.y + (h - h*ratio);
					const circle = document.createElementNS('http://www.w3.org/2000/svg','circle');
					circle.setAttribute('cx', cx);
					circle.setAttribute('cy', cy);
					circle.setAttribute('r', 3.5);
					circle.setAttribute('fill', '#2563eb');
					circle.setAttribute('stroke', 'white');
					circle.setAttribute('stroke-width', '1');
					plotArea.appendChild(circle);
				});
			} catch(err){ console.warn('Fallback dots erro', err); }
		});
	}


	async function renderEntradasCredito(){
		const target = document.getElementById('chart-entradas-credito-mensal');
		if (!target) return;
		if (!entradasCreditoChart) target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		const data = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_entradas_credito_mensal', args: currentFilters });
		const msg = data.message || data; // compat
		const payload = msg || {};
		if (!payload.labels || !payload.labels.length){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>';
			return;
		}
		// Espera dataset único linha
		const ds = payload.datasets && payload.datasets[0];
		if (!ds){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>';
			return;
		}
		const coercedVals = (ds.values||[]).map(v => typeof v==='number'? v: parseFloat(v)||0);
		// Cálculo média e desvio padrão (populacional)
		let mean = 0, std = 0;
		if (coercedVals.length){
			let sample = coercedVals.slice();
			if (sample.length > 2){
				// remove um menor e um maior (apenas uma ocorrência cada)
				const minVal = Math.min(...sample);
				const maxVal = Math.max(...sample);
				let removedMin = false, removedMax = false;
				sample = sample.filter(v=>{
					if (!removedMin && v === minVal){ removedMin = true; return false; }
					if (!removedMax && v === maxVal){ removedMax = true; return false; }
					return true;
				});
			}
			if (sample.length){
				mean = sample.reduce((a,b)=>a+b,0)/sample.length;
				const varPop = sample.reduce((a,b)=>a+Math.pow(b-mean,2),0)/sample.length;
				std = Math.sqrt(varPop);
			}
		}
		let lower = mean - std;
		let upper = mean + std;
		if (std === 0){ // todos iguais: criar banda mínima para visualização opcional
			lower = mean - (mean!==0 ? Math.abs(mean)*0.05 : 0.01);
			upper = mean + (mean!==0 ? Math.abs(mean)*0.05 : 0.01);
		}
		const lineData = { 
			labels: payload.labels.slice(), 
			datasets: [ { name: ds.name || 'Entradas (Crédito)', values: coercedVals, color: '#0d9488' } ], 
			yRegions: [ { label: 'Variação', start: lower, end: upper, options: { labelPos: 'right' } } ]
		};
		const isMobile = window.innerWidth < 640;
		try {
			if (entradasCreditoChart){ entradasCreditoChart = null; }
			target.innerHTML = '';
			entradasCreditoChart = new frappe.Chart(target, {
				title: 'Entradas (Crédito) - Últimos 12 meses',
				type: 'line',
				data: lineData,
				height: isMobile ? 300 : 320,
				lineOptions: { regionFill: 1, hideDots: false, dotSize: 4 },
				axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
				tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
			});
			if (isMobile) rotateXAxisLabels(target, -35);
		} catch(e){ console.warn('Falha gráfico Entradas Crédito', e); }
	}

	let entradasCreditoCategoriaChart = null;
	async function renderEntradasCreditoCategoria(){
		const target = document.getElementById('chart-entradas-credito-categoria-mensal');
		if (!target) return;
		if (!entradasCreditoCategoriaChart) target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		// Remover categoria do filtro (cada categoria vira dataset)
		const { categoria, ...filtersSemCategoria } = currentFilters;
		const resp = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_entradas_credito_mensal_por_categoria', args: filtersSemCategoria });
		const msg = resp.message || resp;
		const payload = msg || {};
		if (!payload.labels || !payload.labels.length){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>';
			return;
		}
		if (!payload.datasets || !payload.datasets.length){
			target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>';
			return;
		}
		const palette = ['#1d4ed8','#0d9488','#9333ea','#dc2626','#f59e0b','#16a34a','#6d28d9','#0891b2','#7c3aed','#ea580c'];
		payload.datasets.forEach((ds,i)=>{ ds.color = palette[i % palette.length]; });
		const stackedData = { labels: payload.labels.slice(), datasets: payload.datasets };
		const isMobile = window.innerWidth < 640;
		try {
			if (!entradasCreditoCategoriaChart){
				target.innerHTML = '';
				entradasCreditoCategoriaChart = new frappe.Chart(target, {
					title: 'Entradas por Categoria (Crédito) - Empilhado',
					type: 'bar',
					data: stackedData,
					height: isMobile ? 300 : 320,
					barOptions: { stacked: true, spaceRatio: 0.4 },
					axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
					tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
				});
				if (isMobile) rotateXAxisLabels(target, -35);
			} else {
				entradasCreditoCategoriaChart.data = stackedData;
				if (typeof entradasCreditoCategoriaChart.draw === 'function') entradasCreditoCategoriaChart.draw();
			}
		} catch(e){ console.warn('Falha gráfico Entradas Categoria', e); }
	}

	function formatNumberBR(v){
		try { return parseFloat(v).toFixed(2).replace('.',',').replace(/\B(?=(\d{3})+(?!\d))/g, '.'); } catch(e){ return v; }
	}

// formatTooltip removido (cada gráfico tem seu próprio tooltip simples)

	function rotateXAxisLabels(container, angle){
		requestAnimationFrame(()=>{
			const svg = container.querySelector('svg');
			if(!svg) return;
			const ticks = svg.querySelectorAll('.x.axis text, .x-axis text, .chart-axis.x text');
			ticks.forEach(txt => {
				if (txt.__rotated) return;
				txt.__rotated = true;
				txt.setAttribute('text-anchor','end');
				const x = txt.getAttribute('x') || 0;
				const y = txt.getAttribute('y') || 0;
				txt.setAttribute('transform', `translate(0,0) rotate(${angle} ${x} ${y})`);
				const dy = parseFloat(txt.getAttribute('dy') || 0);
				txt.setAttribute('dy', (dy + 2));
				txt.style.fontSize = '10px';
			});
		});
	}

	// ================= Saídas (Débito) =================
	let saidasDebitoChart = null;
	async function renderSaidasDebito(){
		const target = document.getElementById('chart-saidas-debito-mensal');
		if (!target) return;
		if (!saidasDebitoChart) target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		const data = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_saidas_debito_mensal', args: currentFilters });
		const payload = data.message || data || {};
		if (!payload.labels || !payload.labels.length){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		const ds = payload.datasets && payload.datasets[0];
		if (!ds){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		const coercedVals = (ds.values||[]).map(v=> typeof v==='number'? v: parseFloat(v)||0);
		// média e desvio para banda
		let mean=0,std=0; if (coercedVals.length){ let sample = coercedVals.slice(); if (sample.length>2){ const minVal=Math.min(...sample); const maxVal=Math.max(...sample); let removedMin=false,removedMax=false; sample = sample.filter(v=>{ if(!removedMin && v===minVal){removedMin=true; return false;} if(!removedMax && v===maxVal){removedMax=true; return false;} return true; }); } if (sample.length){ mean = sample.reduce((a,b)=>a+b,0)/sample.length; const varPop = sample.reduce((a,b)=>a+Math.pow(b-mean,2),0)/sample.length; std = Math.sqrt(varPop);} }
		let lower = mean - std, upper = mean + std; if (std===0){ lower = mean - (mean!==0? Math.abs(mean)*0.05:0.01); upper = mean + (mean!==0? Math.abs(mean)*0.05:0.01); }
		const lineData = { labels: payload.labels.slice(), datasets: [ { name: 'Saídas (Débito)', values: coercedVals, color: '#dc2626' } ], yRegions: [ { label: 'Variação', start: lower, end: upper, options: { labelPos: 'right' } } ] };
		const isMobile = window.innerWidth < 640;
		try {
			if (saidasDebitoChart){ saidasDebitoChart = null; }
			target.innerHTML = '';
			saidasDebitoChart = new frappe.Chart(target, {
				title: 'Saídas (Débito) - Últimos 12 meses',
				type: 'line',
				data: lineData,
				height: isMobile ? 300 : 320,
				lineOptions: { regionFill: 1, hideDots: false, dotSize: 4 },
				axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
				tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
			});
			if (isMobile) rotateXAxisLabels(target, -35);
		} catch(e){ console.warn('Falha gráfico Saídas Débito', e); }
	}

	let saidasDebitoCategoriaChart = null;
	async function renderSaidasDebitoCategoria(){
		const target = document.getElementById('chart-saidas-debito-categoria-mensal');
		if (!target) return;
		if (!saidasDebitoCategoriaChart) target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		const { categoria, ...filtersSemCategoria } = currentFilters;
		const resp = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_saidas_debito_mensal_por_categoria', args: filtersSemCategoria });
		const payload = resp.message || resp || {};
		if (!payload.labels || !payload.labels.length){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		if (!payload.datasets || !payload.datasets.length){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		const palette = ['#dc2626','#b91c1c','#ef4444','#f87171','#991b1b','#fb923c','#f59e0b','#ea580c','#d97706','#7f1d1d'];
		payload.datasets.forEach((ds,i)=>{ ds.color = palette[i % palette.length]; });
		const stackedData = { labels: payload.labels.slice(), datasets: payload.datasets };
		const isMobile = window.innerWidth < 640;
		try {
			if (!saidasDebitoCategoriaChart){
				target.innerHTML='';
				saidasDebitoCategoriaChart = new frappe.Chart(target, {
					title: 'Saídas por Categoria (Débito) - Empilhado',
					type: 'bar',
					data: stackedData,
					height: isMobile ? 300 : 320,
					barOptions: { stacked: true, spaceRatio: 0.4 },
					axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
					tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
				});
				if (isMobile) rotateXAxisLabels(target, -35);
			} else {
				saidasDebitoCategoriaChart.data = stackedData;
				if (typeof saidasDebitoCategoriaChart.draw === 'function') saidasDebitoCategoriaChart.draw();
			}
		} catch(e){ console.warn('Falha gráfico Saídas Categoria', e); }
	}

	let saidasDebitoCentroChart = null;
	async function renderSaidasDebitoCentro(){
		const target = document.getElementById('chart-saidas-debito-centro-mensal');
		if (!target) return;
		if (!saidasDebitoCentroChart) target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		const { centro_de_custo, ...filtersSemCentro } = currentFilters;
		const resp = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_saidas_debito_mensal_por_centro_custo', args: filtersSemCentro });
		const payload = resp.message || resp || {};
		if (!payload.labels || !payload.labels.length){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		if (!payload.datasets || !payload.datasets.length){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		const palette = ['#dc2626','#991b1b','#ef4444','#fb923c','#f59e0b','#b91c1c','#ea580c','#d97706','#f87171','#7f1d1d'];
		payload.datasets.forEach((ds,i)=>{ ds.color = palette[i % palette.length]; });
		const stackedData = { labels: payload.labels.slice(), datasets: payload.datasets };
		const isMobile = window.innerWidth < 640;
		try {
			if (!saidasDebitoCentroChart){
				target.innerHTML='';
				saidasDebitoCentroChart = new frappe.Chart(target, {
					title: 'Saídas por Centro de Custo (Débito) - Empilhado',
					type: 'bar',
					data: stackedData,
					height: isMobile ? 340 : 360,
					barOptions: { stacked: true, spaceRatio: 0.4 },
					axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
					tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
				});
				if (isMobile) rotateXAxisLabels(target, -35);
			} else {
				saidasDebitoCentroChart.data = stackedData;
				if (typeof saidasDebitoCentroChart.draw === 'function') saidasDebitoCentroChart.draw();
			}
		} catch(e){ console.warn('Falha gráfico Saídas Centro', e); }
	}

	let saidasDebitoTipoChart = null;
	async function renderSaidasDebitoTipo(){
		const target = document.getElementById('chart-saidas-debito-tipo-mensal');
		if (!target) return;
		if (!saidasDebitoTipoChart) target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		const { ordinaria_extraordinaria, ...filtersSemTipo } = currentFilters;
		const resp = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_saidas_debito_mensal_por_tipo', args: filtersSemTipo });
		const payload = resp.message || resp || {};
		if (!payload.labels || !payload.labels.length){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		if (!payload.datasets || !payload.datasets.length){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		const palette = ['#dc2626','#7f1d1d','#f87171'];
		payload.datasets.forEach((ds,i)=>{ ds.color = palette[i % palette.length]; });
		const stackedData = { labels: payload.labels.slice(), datasets: payload.datasets };
		const isMobile = window.innerWidth < 640;
		try {
			if (!saidasDebitoTipoChart){
				target.innerHTML='';
				saidasDebitoTipoChart = new frappe.Chart(target, {
					title: 'Saídas por Tipo (Débito) - Empilhado',
					type: 'bar',
					data: stackedData,
					height: isMobile ? 340 : 360,
					barOptions: { stacked: true, spaceRatio: 0.4 },
					axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
					tooltipOptions: { formatTooltipY: d => 'R$ ' + formatNumberBR(d) }
				});
				if (isMobile) rotateXAxisLabels(target, -35);
			} else {
				saidasDebitoTipoChart.data = stackedData;
				if (typeof saidasDebitoTipoChart.draw === 'function') saidasDebitoTipoChart.draw();
			}
		} catch(e){ console.warn('Falha gráfico Saídas Tipo', e); }
	}

	// ================= Contribuições Mensais =================
	let contribStatusChart = null;
	async function renderContribuicoesMensaisStatus(){
		const target = document.getElementById('chart-contribuicoes-status-mensal');
		if (!target) return;
		if (!contribStatusChart) target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		const resp = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_contribuicoes_mensais_por_status' });
		const payload = resp.message || resp || {};
		if (!payload.labels || !payload.labels.length){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		if (!payload.datasets || !payload.datasets.length){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		// Paleta consistente por status comuns
		const colorMap = { 'Em Aberto':'#6366f1','Pago':'#16a34a','Atrasado':'#dc2626','Cancelado':'#6b7280','Sem Status':'#9ca3af' };
		payload.datasets.forEach(ds=>{ ds.color = colorMap[ds.name] || '#0ea5e9'; });
		const stackedData = { labels: payload.labels.slice(), datasets: payload.datasets };
		const isMobile = window.innerWidth < 640;
		try {
			if (!contribStatusChart){
				target.innerHTML = '';
				contribStatusChart = new frappe.Chart(target, {
					title: 'Contribuições Mensais por Status - Empilhado',
					type: 'bar',
					data: stackedData,
					height: isMobile ? 340 : 360,
					barOptions: { stacked: true, spaceRatio: 0.4 },
					axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1 },
					tooltipOptions: { formatTooltipY: d => d + ' contrib.' }
				});
				if (isMobile) rotateXAxisLabels(target, -35);
			} else {
				contribStatusChart.data = stackedData;
				if (typeof contribStatusChart.draw === 'function') contribStatusChart.draw();
			}
		} catch(e){ console.warn('Falha gráfico Contribuições Status', e); }
	}


	// === Inadimplência (%) ===
	let contribInadimplenciaChart = null;
	async function renderContribuicoesMensaisInadimplencia(){
		const target = document.getElementById('chart-contribuicoes-inadimplencia-mensal');
		if (!target) return;
		if (!contribInadimplenciaChart) target.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
		const resp = await frappe.call({ method: 'gris.www.financeiro.dashboard.get_contribuicoes_mensais_inadimplencia' });
		const payload = resp.message || resp || {};
		if (!payload.labels || !payload.labels.length){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		const ds = payload.datasets && payload.datasets[0];
		if (!ds){ target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados.</div>'; return; }
		ds.color = '#6366f1';
		const data = { labels: payload.labels.slice(), datasets: [ ds ] };
		try {
			// recria sempre (pequeno e simples)
			target.innerHTML='';
			const isMobile = window.innerWidth < 640;
			contribInadimplenciaChart = new frappe.Chart(target, {
				title: 'Inadimplência (%)',
				type: 'line',
				data,
				height: isMobile ? 340 : 360,
				lineOptions: { regionFill: 1, hideDots: false, dotSize: 4 },
				axisOptions: { xAxisMode: 'tick', xIsSeries: false, shortenYAxisNumbers: 1, yAxisMode: 'span' },
				tooltipOptions: { formatTooltipY: d => parseFloat(d).toFixed(2).replace('.',',') + '%' }
			});
			if (isMobile) rotateXAxisLabels(target, -35);
		} catch(e){ console.warn('Falha gráfico Inadimplência', e); }
	}
})();
