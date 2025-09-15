// Portal page client script for /associados
// Requer que frappe-charts (frappe.Chart) esteja disponível. Se não, carrega UMD.

(async function() {
  const ensureCharts = () => new Promise((resolve, reject) => {
    if (window.frappe && frappe.Chart) return resolve();
    const s = document.createElement('script');
    s.src = '/assets/frappe/node_modules/frappe-charts/dist/frappe-charts.umd.js';
    s.onload = () => {
      try { const ns = window['frappe-charts']; if (ns && ns.Chart) frappe.Chart = ns.Chart; } catch(e) {}
      if (frappe.Chart) return resolve();
      reject(new Error('frappe.Chart não disponível após load.'));
    };
    s.onerror = () => reject(new Error('Falha ao carregar frappe-charts UMD'));
    document.head.appendChild(s);
  });

  let currentChartInstance = null;
  let currentVencChart = null;
  let currentAtivosMensalChart = null;
  let currentNovosMensalChart = null;
  let currentEvasaoMensalChart = null;
  frappe.ready(async () => {
    const form = document.getElementById('assoc-dashboard-filters');
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        await refreshDashboard(getFormFilters(form));
      });
      form.addEventListener('reset', async (e) => {
        // pequeno delay para reset efetivar
        setTimeout(() => refreshDashboard({}), 0);
      });
    }
    await refreshDashboard({});
  });

  function getFormFilters(form){
    const fd = new FormData(form);
    const filters = {};
    ['categoria','ramo','secao','funcao'].forEach(k=>{ const v = (fd.get(k)||'').trim(); if(v) filters[k]=v; });
    return filters;
  }

  async function refreshDashboard(filters){
    try {
      await ensureCharts();
      setLoadingState();
      const r = await frappe.call({ method: 'gris.www.associados.index.get_associados_dashboard', args: filters });
      const data = r.message || {};
      updateCards(data.cards);
  renderRamoCategoriaChart(data.chart);
  renderVencimentosRegistroChart(data.chart_vencimentos);
  renderAtivosMensalChart(data.chart_ativos_mensal);
  renderNovosMensalChart(data.chart_novos_mensal);
  renderEvasaoMensalChart(data.chart_evasao_mensal);
    } catch(e){
      console.warn('Erro ao atualizar dashboard', e);
    }
  }

  function updateCards(cards={}) {
    if (!cards.ativos) return;
    setText('card-ativos-total', cards.ativos.total);
    setText('card-ativos-benef', cards.ativos.beneficiarios);
    setText('card-ativos-adultos', cards.ativos.adultos);
    setText('card-ativos-outros', cards.ativos.outros);

    if (cards.registro_valido) {
      setText('card-reg-valido-total', cards.registro_valido.total);
      setText('card-reg-valido-pct', formatPct(cards.registro_valido.pct));
    }
    if (cards.registro_vencido) {
      setText('card-reg-vencido-total', cards.registro_vencido.total);
      setText('card-reg-vencido-pct', formatPct(cards.registro_vencido.pct));
    }
    if (cards.registro_isento) {
      setText('card-reg-isento-total', cards.registro_isento.total);
      setText('card-reg-isento-pct', formatPct(cards.registro_isento.pct));
    }
    if (cards.registro_provisorio) {
      setText('card-reg-provisorio-total', cards.registro_provisorio.total);
      setText('card-reg-provisorio-pct', formatPct(cards.registro_provisorio.pct));
    }
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }
  function formatPct(v){ return (v!=null? v:0) + '%'; }

  function renderRamoCategoriaChart(chartData) {
    if (!chartData) return;
    const target = document.getElementById('chart-ramos-categorias');
    if (!target) return;

    const isMobile = window.innerWidth < 640;
    if (isMobile) {
      // Compactar labels para caber
      chartData.labels = chartData.labels.map(l => {
        if (l === 'Não se aplica') return 'N/A';
        if (l === 'Escoteiro') return 'Esc.';
        if (l === 'Pioneiro') return 'Pion.';
        if (l === 'Sênior') return 'Sên.';
        return l;
      });
    }

    if (currentChartInstance && currentChartInstance.parent === target) {
      // limpar área
      target.innerHTML = '';
    }
    const chart = new frappe.Chart(target, {
      title: 'Associados Ativos por Ramo e Categoria',
      type: 'bar',
      data: chartData,
      height: isMobile ? 300 : 320,
      barOptions: {
        stacked: true,
        spaceRatio: 0.35
      },
      axisOptions: {
        xAxisMode: 'tick',
        xIsSeries: false,
        shortenYAxisNumbers: 1
      },
      tooltipOptions: {
        formatTooltipY: d => d + ' associados'
      }
    });
    currentChartInstance = chart;
  if (isMobile) rotateXAxisLabels(target, -35);
    // Reposiciona tooltip para não vazar viewport
    const root = target.querySelector('svg');
    if (root) {
      const observer = new MutationObserver(() => {
        adjustTooltip(target);
      });
      observer.observe(target, { subtree: true, childList: true, attributes: true });
    }
  }

  function setLoadingState(){
    setText('card-ativos-total','--');
    setText('card-ativos-benef','--');
    setText('card-ativos-adultos','--');
    setText('card-ativos-outros','--');
    setText('card-reg-valido-total','--'); setText('card-reg-valido-pct','--%');
    setText('card-reg-vencido-total','--'); setText('card-reg-vencido-pct','--%');
    setText('card-reg-isento-total','--'); setText('card-reg-isento-pct','--%');
  setText('card-reg-provisorio-total','--'); setText('card-reg-provisorio-pct','--%');
    const chartTarget = document.getElementById('chart-ramos-categorias');
    if (chartTarget) chartTarget.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
    const vencTarget = document.getElementById('chart-vencimentos-registro');
    if (vencTarget) vencTarget.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
  const mensalTarget = document.getElementById('chart-ativos-mensal');
  if (mensalTarget) mensalTarget.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
  const novosTarget = document.getElementById('chart-novos-mensal');
  if (novosTarget) novosTarget.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
  const evasaoTarget = document.getElementById('chart-evasao-mensal');
  if (evasaoTarget) evasaoTarget.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
  }

  function renderVencimentosRegistroChart(chartData){
    const target = document.getElementById('chart-vencimentos-registro');
    if(!target) return;
    if(!chartData || !chartData.labels || !chartData.labels.length){
      target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados para os próximos 6 meses.</div>';
      return;
    }
    if (currentVencChart && currentVencChart.parent === target) target.innerHTML='';
    const isMobile = window.innerWidth < 640;
    const chart = new frappe.Chart(target, {
      title: 'Vencimento de Registro (Próximos 6 meses)',
      type: 'bar',
      data: chartData,
      height: isMobile ? 300 : 320,
      barOptions: { stacked: true, spaceRatio: 0.4 },
      axisOptions: { xAxisMode:'tick', xIsSeries:false, shortenYAxisNumbers:1 },
      tooltipOptions: { formatTooltipY: d => d + ' associados' }
  });
    currentVencChart = chart;
    if (isMobile) rotateXAxisLabels(target, -35);
  }

  function renderAtivosMensalChart(chartData){
    const target = document.getElementById('chart-ativos-mensal');
    if(!target) return;
    if(!chartData || !chartData.labels || !chartData.labels.length){
      target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados para os últimos 12 meses.</div>';
      return;
    }
    if (currentAtivosMensalChart && currentAtivosMensalChart.parent === target) target.innerHTML='';
    const isMobile = window.innerWidth < 640;
    const chart = new frappe.Chart(target, {
      title: 'Ativos (Últimos 12 meses)',
      type: 'line',
      data: chartData,
      height: isMobile ? 300 : 320,
      lineOptions: { regionFill: 1, hideDots: 0 },
      axisOptions: { xAxisMode:'tick', xIsSeries:false, shortenYAxisNumbers:1 },
      tooltipOptions: { formatTooltipY: d => d + ' ativos' }
    });
    currentAtivosMensalChart = chart;
    if (isMobile) rotateXAxisLabels(target, -35);
  }

  function renderNovosMensalChart(chartData){
    const target = document.getElementById('chart-novos-mensal');
    if(!target) return;
    if(!chartData || !chartData.labels || !chartData.labels.length){
      target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados para os últimos 12 meses.</div>';
      return;
    }
    if (currentNovosMensalChart && currentNovosMensalChart.parent === target) target.innerHTML='';
    const isMobile = window.innerWidth < 640;
    const chart = new frappe.Chart(target, {
      title: 'Novos Associados (Últimos 12 meses)',
      type: 'bar',
      data: chartData,
      height: isMobile ? 300 : 320,
      barOptions: { stacked: false, spaceRatio: 0.4 },
      axisOptions: { xAxisMode:'tick', xIsSeries:false, shortenYAxisNumbers:1 },
      tooltipOptions: { formatTooltipY: d => d + ' novos' }
    });
    currentNovosMensalChart = chart;
    if (isMobile) rotateXAxisLabels(target, -35);
  }

  function renderEvasaoMensalChart(chartData){
    const target = document.getElementById('chart-evasao-mensal');
    if(!target) return;
    if(!chartData || !chartData.labels || !chartData.labels.length){
      target.innerHTML = '<div class="text-muted small px-2 pt-3">Sem dados para os últimos 12 meses.</div>';
      return;
    }
    if (currentEvasaoMensalChart && currentEvasaoMensalChart.parent === target) target.innerHTML='';
    const isMobile = window.innerWidth < 640;
    // Espera datasets: [ {name: Evasão, chartType: bar}, {name: Taxa Evasão (%), chartType: line} ]
    // Normalização: escala taxa (%) para faixa 0..max(evasão) para sobrepor a mesma Y.
    try {
      const dsEvasao = chartData.datasets.find(d => /Evasão$/i.test(d.name));
      const dsRate = chartData.datasets.find(d => /Taxa Evasão/i.test(d.name));
      if (dsEvasao && dsRate) {
        const evasaoValues = dsEvasao.values.slice();
        const rateOriginal = dsRate.values.slice(); // percentuais originais
        const maxBar = Math.max(...evasaoValues, 0);
        // Evita divisão por zero; se sem barras, mantém linha em zeros
        const scale = maxBar > 0 ? maxBar / 100 : 0;
        const normalizedRates = rateOriginal.map(v => scale ? +(v * scale).toFixed(2) : 0);
        // Substitui valores da linha pela versão normalizada
        dsRate.values = normalizedRates;
        // Guarda originais em propriedades auxiliares para tooltip
        dsRate._original_percentages = rateOriginal;
        dsRate._normalized = true;
      }
    } catch(e) { console.warn('Falha ao normalizar taxa evasão', e); }

    const chart = new frappe.Chart(target, {
      title: 'Evasão (Últimos 12 meses)',
      type: 'axis-mixed',
      data: chartData,
      height: isMobile ? 300 : 320,
      barOptions: { stacked: false, spaceRatio: 0.4 },
      lineOptions: { regionFill: 0, hideDots: 0 },
      axisOptions: { xAxisMode:'tick', xIsSeries:false, shortenYAxisNumbers:1 },
      tooltipOptions: { 
        formatTooltipY: (val, opts) => {
          // opts.datasetIndex, opts.index (frappe-charts passa contexto)
          if (opts && chartData && chartData.datasets) {
            const ds = chartData.datasets[opts.datasetIndex];
            if (ds && ds._normalized && Array.isArray(ds._original_percentages)) {
              const original = ds._original_percentages[opts.index];
              if (original != null) return original + '%';
            }
          }
          // Caso contrário é a barra (evasão absoluta)
          return val + '';
        }
      }
    });
    currentEvasaoMensalChart = chart;
    if (isMobile) rotateXAxisLabels(target, -35);
  }

  // Reposition logic removido: gráfico tem card próprio agora

  function rotateXAxisLabels(container, angle){
    // Aguarda próximo frame para garantir que o SVG e eixos existam
    requestAnimationFrame(()=>{
      const svg = container.querySelector('svg');
      if(!svg) return;
      // Seleciona textos dos ticks do eixo X (estrutura típica do frappe-charts)
      const tickTexts = svg.querySelectorAll('.x.axis text, .x-axis text, .chart-axis.x text');
      tickTexts.forEach(txt => {
        // Evita aplicar múltiplas vezes
        if (txt.__rotated) return;
        txt.__rotated = true;
        // Define origem e âncora para manter legibilidade
        txt.setAttribute('text-anchor','end');
        const x = txt.getAttribute('x') || 0;
        const y = txt.getAttribute('y') || 0;
        txt.setAttribute('transform', `translate(0,0) rotate(${angle} ${x} ${y})`);
        // Ajusta leve subida para não cortar
        const dy = parseFloat(txt.getAttribute('dy') || 0);
        txt.setAttribute('dy', (dy + 2));
        txt.style.fontSize = '10px';
      });
    });
  }
})();

function adjustTooltip(target) {
  const tip = target.querySelector('.graph-svg-tip');
  if (!tip) return;
  // Reset para medir corretamente
  tip.style.left = tip.style.left || '';
  tip.style.right = '';
  const rect = tip.getBoundingClientRect();
  const vw = window.innerWidth; const vh = window.innerHeight;
  // Limitar largura se excede viewport
  if (rect.width > vw - 24) {
    tip.style.width = (vw - 24) + 'px';
  }
  let dx = 0; let dy = 0;
  if (rect.right > vw - 4) dx = vw - 4 - rect.right; // move para esquerda
  if (rect.left < 4) dx = 4 - rect.left; // move para direita
  if (rect.bottom > vh - 4) dy = vh - 4 - rect.bottom; // sobe
  if (rect.top < 4) dy = 4 - rect.top; // desce
  if (dx || dy) {
    const currentLeft = parseFloat(tip.style.left || '0');
    const currentTop = parseFloat(tip.style.top || '0');
    // Quando lib define left/top em px relativos ao container
    tip.style.left = (currentLeft + dx) + 'px';
    tip.style.top = (currentTop + dy) + 'px';
  }
}

// (Código de labels custom removido por decisão: manter implementação padrão da biblioteca)
