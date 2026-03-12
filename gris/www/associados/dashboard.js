// Portal page client script for /associados
// Usa Apache ECharts como biblioteca única de gráficos.

(async function () {
  const CHART_COLORS = [
    '#0072B2',
    '#E69F00',
    '#009E73',
    '#D55E00',
    '#56B4E9',
    '#CC79A7',
    '#F0E442',
    '#000000',
  ];

  const chartIds = [
    'chart-ramos-categorias',
    'chart-vencimentos-registro',
    'chart-ativos-mensal',
    'chart-novos-mensal',
    'chart-evasao-mensal',
  ];

  const ensureEcharts = () =>
    new Promise((resolve, reject) => {
      if (window.echarts) {
        resolve();
        return;
      }

      const existing = document.querySelector('script[data-gris-echarts="1"]');
      if (existing) {
        existing.addEventListener('load', () => (window.echarts ? resolve() : reject(new Error('ECharts não disponível'))), {
          once: true,
        });
        existing.addEventListener('error', () => reject(new Error('Falha ao carregar ECharts')), { once: true });
        return;
      }

      const script = document.createElement('script');
      script.dataset.grisEcharts = '1';
      script.src = '/assets/gris/vendor/echarts/echarts.min.js';
      script.onload = () => {
        if (window.echarts) {
          resolve();
        } else {
          reject(new Error('ECharts não disponível'));
        }
      };
      script.onerror = () => reject(new Error('Falha ao carregar ECharts'));
      document.head.appendChild(script);
    });

  function getFormFilters(form) {
    const fd = new FormData(form);
    const filters = {};
    ['categoria', 'ramo', 'secao', 'funcao'].forEach((k) => {
      const v = (fd.get(k) || '').trim();
      if (v) filters[k] = v;
    });
    return filters;
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function formatPct(v) {
    return `${v != null ? v : 0}%`;
  }

  function formatNumber(v) {
    return Number(v || 0).toLocaleString('pt-BR');
  }

  function isMobile() {
    return window.innerWidth < 640;
  }

  function axisLabelConfig() {
    return {
      interval: 0,
      rotate: isMobile() ? 35 : 0,
      hideOverlap: true,
      fontSize: isMobile() ? 10 : 12,
      formatter: (label) => {
        if (!isMobile()) return label;
        const map = {
          'Não se aplica': 'N/A',
          Escoteiro: 'Esc.',
          Pioneiro: 'Pion.',
          Sênior: 'Sên.',
        };
        return map[label] || label;
      },
    };
  }

  function baseOption({ legendTop = 0, gridTop = 56, yAxisName = '' } = {}) {
    return {
      aria: { enabled: true },
      color: CHART_COLORS,
      animationDuration: 450,
      animationDurationUpdate: 300,
      tooltip: {
        trigger: 'axis',
        confine: true,
        className: 'echarts-tooltip-modern',
        axisPointer: { type: 'shadow' },
      },
      legend: {
        type: 'scroll',
        top: legendTop,
      },
      grid: {
        left: 12,
        right: 12,
        top: gridTop,
        bottom: isMobile() ? 64 : 36,
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        axisTick: { alignWithLabel: true },
        axisLabel: axisLabelConfig(),
      },
      yAxis: {
        type: 'value',
        name: yAxisName,
        minInterval: 1,
      },
    };
  }

  function getChart(id) {
    const target = document.getElementById(id);
    if (!target || !window.echarts) return null;
    const existing = window.echarts.getInstanceByDom(target);
    if (existing) return existing;
    target.innerHTML = '';
    return window.echarts.init(target);
  }

  function disposeChart(id) {
    const target = document.getElementById(id);
    if (!target || !window.echarts) return;
    const instance = window.echarts.getInstanceByDom(target);
    if (instance) instance.dispose();
  }

  function setChartMessage(id, text) {
    disposeChart(id);
    const target = document.getElementById(id);
    if (target) target.innerHTML = `<div class="text-muted small px-2 pt-3">${text}</div>`;
  }

  function updateCards(cards = {}) {
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

  function setLoadingState() {
    setText('card-ativos-total', '--');
    setText('card-ativos-benef', '--');
    setText('card-ativos-adultos', '--');
    setText('card-ativos-outros', '--');
    setText('card-reg-valido-total', '--');
    setText('card-reg-valido-pct', '--%');
    setText('card-reg-vencido-total', '--');
    setText('card-reg-vencido-pct', '--%');
    setText('card-reg-isento-total', '--');
    setText('card-reg-isento-pct', '--%');
    setText('card-reg-provisorio-total', '--');
    setText('card-reg-provisorio-pct', '--%');

    chartIds.forEach((id) => setChartMessage(id, 'Carregando...'));
  }

  function renderRamoCategoriaChart(chartData) {
    if (!chartData || !Array.isArray(chartData.labels) || !chartData.labels.length) {
      setChartMessage('chart-ramos-categorias', 'Sem dados para os filtros selecionados.');
      return;
    }

    const chart = getChart('chart-ramos-categorias');
    if (!chart) return;
    const datasets = Array.isArray(chartData.datasets) ? chartData.datasets : [];

    chart.setOption(
      {
        ...baseOption({ yAxisName: 'Associados' }),
        xAxis: {
          ...baseOption().xAxis,
          data: chartData.labels,
        },
        tooltip: {
          ...baseOption().tooltip,
          formatter: (params) => {
            const rows = params
              .map((item) => `${item.marker}${item.seriesName}: <strong>${formatNumber(item.value)}</strong> associados`)
              .join('<br/>');
            return `<strong>${params[0]?.axisValue || ''}</strong><br/>${rows}`;
          },
        },
        series: datasets.map((ds) => ({
          name: ds.name,
          type: 'bar',
          stack: 'ativos',
          barMaxWidth: 34,
          emphasis: { focus: 'series' },
          data: Array.isArray(ds.values) ? ds.values : [],
        })),
      },
      true,
    );
  }

  function renderVencimentosRegistroChart(chartData) {
    if (!chartData || !Array.isArray(chartData.labels) || !chartData.labels.length) {
      setChartMessage('chart-vencimentos-registro', 'Sem dados para os próximos 6 meses.');
      return;
    }

    const chart = getChart('chart-vencimentos-registro');
    if (!chart) return;
    const datasets = Array.isArray(chartData.datasets) ? chartData.datasets : [];

    chart.setOption(
      {
        ...baseOption({ yAxisName: 'Associados' }),
        xAxis: {
          ...baseOption().xAxis,
          data: chartData.labels,
        },
        tooltip: {
          ...baseOption().tooltip,
          formatter: (params) => {
            const rows = params
              .map((item) => `${item.marker}${item.seriesName}: <strong>${formatNumber(item.value)}</strong> associados`)
              .join('<br/>');
            return `<strong>${params[0]?.axisValue || ''}</strong><br/>${rows}`;
          },
        },
        series: datasets.map((ds) => ({
          name: ds.name,
          type: 'bar',
          stack: 'vencimentos',
          barMaxWidth: 34,
          emphasis: { focus: 'series' },
          data: Array.isArray(ds.values) ? ds.values : [],
        })),
      },
      true,
    );
  }

  function renderAtivosMensalChart(chartData) {
    if (!chartData || !Array.isArray(chartData.labels) || !chartData.labels.length) {
      setChartMessage('chart-ativos-mensal', 'Sem dados para os últimos 12 meses.');
      return;
    }

    const chart = getChart('chart-ativos-mensal');
    if (!chart) return;
    const firstDs = (chartData.datasets || [])[0] || {};

    chart.setOption(
      {
        ...baseOption({ yAxisName: 'Ativos' }),
        xAxis: {
          ...baseOption().xAxis,
          data: chartData.labels,
        },
        tooltip: {
          ...baseOption().tooltip,
          axisPointer: { type: 'line' },
          formatter: (params) => {
            const item = params[0];
            if (!item) return '';
            return `<strong>${item.axisValue}</strong><br/>${item.marker}${firstDs.name || 'Ativos'}: <strong>${formatNumber(item.value)}</strong>`;
          },
        },
        series: [
          {
            name: firstDs.name || 'Ativos',
            type: 'line',
            symbol: 'circle',
            symbolSize: 7,
            smooth: 0.25,
            lineStyle: { width: 3, type: 'solid' },
            areaStyle: { opacity: 0.12 },
            data: Array.isArray(firstDs.values) ? firstDs.values : [],
          },
        ],
      },
      true,
    );
  }

  function renderNovosMensalChart(chartData) {
    if (!chartData || !Array.isArray(chartData.labels) || !chartData.labels.length) {
      setChartMessage('chart-novos-mensal', 'Sem dados para os últimos 12 meses.');
      return;
    }

    const chart = getChart('chart-novos-mensal');
    if (!chart) return;
    const firstDs = (chartData.datasets || [])[0] || {};

    chart.setOption(
      {
        ...baseOption({ yAxisName: 'Novos' }),
        xAxis: {
          ...baseOption().xAxis,
          data: chartData.labels,
        },
        tooltip: {
          ...baseOption().tooltip,
          formatter: (params) => {
            const item = params[0];
            if (!item) return '';
            return `<strong>${item.axisValue}</strong><br/>${item.marker}${firstDs.name || 'Novos'}: <strong>${formatNumber(item.value)}</strong>`;
          },
        },
        series: [
          {
            name: firstDs.name || 'Novos',
            type: 'bar',
            barMaxWidth: 34,
            emphasis: { focus: 'series' },
            data: Array.isArray(firstDs.values) ? firstDs.values : [],
          },
        ],
      },
      true,
    );
  }

  function renderEvasaoMensalChart(chartData) {
    if (!chartData || !Array.isArray(chartData.labels) || !chartData.labels.length) {
      setChartMessage('chart-evasao-mensal', 'Sem dados para os últimos 12 meses.');
      return;
    }

    const chart = getChart('chart-evasao-mensal');
    if (!chart) return;
    const datasets = Array.isArray(chartData.datasets) ? chartData.datasets : [];
    const dsEvasao = datasets.find((d) => /Evasão$/i.test(d.name || '')) || datasets[0] || {};
    const dsTaxa = datasets.find((d) => /Taxa Evasão/i.test(d.name || '')) || datasets[1] || {};

    chart.setOption(
      {
        ...baseOption({ yAxisName: 'Evasões' }),
        xAxis: {
          ...baseOption().xAxis,
          data: chartData.labels,
        },
        yAxis: [
          {
            type: 'value',
            name: 'Evasões',
            minInterval: 1,
          },
          {
            type: 'value',
            name: 'Taxa (%)',
            min: 0,
            max: 100,
            axisLabel: {
              formatter: (v) => `${v}%`,
            },
          },
        ],
        tooltip: {
          ...baseOption().tooltip,
          formatter: (params) => {
            const rows = params
              .map((item) => {
                const suffix = item.seriesName === (dsTaxa.name || 'Taxa Evasão (%)') ? '%' : '';
                return `${item.marker}${item.seriesName}: <strong>${formatNumber(item.value)}${suffix}</strong>`;
              })
              .join('<br/>');
            return `<strong>${params[0]?.axisValue || ''}</strong><br/>${rows}`;
          },
        },
        series: [
          {
            name: dsEvasao.name || 'Evasão',
            type: 'bar',
            yAxisIndex: 0,
            barMaxWidth: 34,
            emphasis: { focus: 'series' },
            data: Array.isArray(dsEvasao.values) ? dsEvasao.values : [],
          },
          {
            name: dsTaxa.name || 'Taxa Evasão (%)',
            type: 'line',
            yAxisIndex: 1,
            symbol: 'triangle',
            symbolSize: 8,
            smooth: 0.25,
            lineStyle: {
              width: 3,
              type: 'dashed',
            },
            data: Array.isArray(dsTaxa.values) ? dsTaxa.values : [],
          },
        ],
      },
      true,
    );
  }

  async function refreshDashboard(filters) {
    try {
      await ensureEcharts();
      setLoadingState();
      const r = await frappe.call({ method: 'gris.www.associados.dashboard.get_associados_dashboard', args: filters });
      const data = r.message || {};

      updateCards(data.cards);
      renderRamoCategoriaChart(data.chart);
      renderVencimentosRegistroChart(data.chart_vencimentos);
      renderAtivosMensalChart(data.chart_ativos_mensal);
      renderNovosMensalChart(data.chart_novos_mensal);
      renderEvasaoMensalChart(data.chart_evasao_mensal);
    } catch (e) {
      console.warn('Erro ao atualizar dashboard', e);
      chartIds.forEach((id) => setChartMessage(id, 'Erro ao carregar gráfico.'));
    }
  }

  function bindGlobalResize() {
    window.addEventListener('resize', () => {
      if (!window.echarts) return;
      chartIds.forEach((id) => {
        const target = document.getElementById(id);
        if (!target) return;
        const instance = window.echarts.getInstanceByDom(target);
        if (instance) instance.resize();
      });
    });
  }

  frappe.ready(async () => {
    const form = document.getElementById('assoc-dashboard-filters');
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        await refreshDashboard(getFormFilters(form));
      });
      form.addEventListener('reset', () => {
        setTimeout(() => refreshDashboard({}), 0);
      });
    }

    bindGlobalResize();
    await refreshDashboard({});
  });
})();