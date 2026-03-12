// Dashboard Financeiro - visualizacoes com Apache ECharts
(async function () {
  const CHART_COLORS = ['#0072B2', '#E69F00', '#009E73', '#D55E00', '#56B4E9', '#CC79A7', '#F0E442', '#000000'];
  const chartIds = [
    'chart-entradas-saidas-mensal',
    'chart-resultado-mensal',
    'chart-entradas-credito-mensal',
    'chart-entradas-credito-categoria-mensal',
    'chart-entradas-credito-centro-mensal',
    'chart-entradas-credito-tipo-mensal',
    'chart-saidas-debito-mensal',
    'chart-saidas-debito-categoria-mensal',
    'chart-saidas-debito-centro-mensal',
    'chart-saidas-debito-tipo-mensal',
    'chart-contribuicoes-status-mensal',
    'chart-contribuicoes-inadimplencia-mensal',
  ];

  let currentFilters = {};

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
        if (window.echarts) resolve();
        else reject(new Error('ECharts não disponível'));
      };
      script.onerror = () => reject(new Error('Falha ao carregar ECharts'));
      document.head.appendChild(script);
    });

  function isMobile() {
    return window.innerWidth < 640;
  }

  function getFormFilters(form) {
    const fd = new FormData(form);
    const out = {};
    ['categoria', 'instituicao', 'carteira', 'centro_de_custo', 'ordinaria_extraordinaria'].forEach((k) => {
      const v = (fd.get(k) || '').trim();
      if (v) out[k] = v;
    });
    return out;
  }

  function parseNumber(value) {
    const n = typeof value === 'number' ? value : parseFloat(value || 0);
    return Number.isFinite(n) ? n : 0;
  }

  function formatCurrency(value) {
    return parseNumber(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  function formatNumber(value) {
    return parseNumber(value).toLocaleString('pt-BR');
  }

  function formatPercent(value, digits = 2) {
    return `${parseNumber(value).toFixed(digits).replace('.', ',')}%`;
  }

  function axisLabelConfig() {
    return {
      interval: 0,
      rotate: isMobile() ? 35 : 0,
      hideOverlap: true,
      fontSize: isMobile() ? 10 : 12,
    };
  }

  function baseOption({ yAxisName = '', gridTop = 58, legendTop = 4, axisPointer = 'shadow' } = {}) {
    return {
      aria: { enabled: true },
      color: CHART_COLORS,
      animationDuration: 400,
      animationDurationUpdate: 250,
      tooltip: {
        trigger: 'axis',
        confine: true,
        className: 'echarts-tooltip-modern',
        axisPointer: { type: axisPointer },
      },
      legend: {
        type: 'scroll',
        top: legendTop,
      },
      grid: {
        top: gridTop,
        left: 14,
        right: 14,
        bottom: isMobile() ? 66 : 38,
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
    const existing = window.echarts.getInstanceByDom(target);
    if (existing) existing.dispose();
  }

  function setChartMessage(id, text) {
    disposeChart(id);
    const target = document.getElementById(id);
    if (target) target.innerHTML = `<div class="text-muted small px-2 pt-3">${text}</div>`;
  }

  function setAllLoading() {
    chartIds.forEach((id) => setChartMessage(id, 'Carregando...'));
  }

  function computeBand(values) {
    const coerced = (values || []).map(parseNumber);
    let sample = coerced.slice();

    if (sample.length > 2) {
      const minVal = Math.min(...sample);
      const maxVal = Math.max(...sample);
      let removedMin = false;
      let removedMax = false;
      sample = sample.filter((v) => {
        if (!removedMin && v === minVal) {
          removedMin = true;
          return false;
        }
        if (!removedMax && v === maxVal) {
          removedMax = true;
          return false;
        }
        return true;
      });
    }

    let mean = 0;
    let std = 0;
    if (sample.length) {
      mean = sample.reduce((acc, v) => acc + v, 0) / sample.length;
      const variance = sample.reduce((acc, v) => acc + Math.pow(v - mean, 2), 0) / sample.length;
      std = Math.sqrt(variance);
    }

    let lower = mean - std;
    let upper = mean + std;
    if (std === 0) {
      const delta = mean !== 0 ? Math.abs(mean) * 0.05 : 0.01;
      lower = mean - delta;
      upper = mean + delta;
    }

    return { values: coerced, mean, lower, upper };
  }

  async function atualizarCardInadimplencia() {
    const el = document.getElementById('card-inadimplencia');
    const desc = document.getElementById('card-inadimplencia-desc');
    if (!el) return;
    el.textContent = '--';

    try {
      const resp = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_inadimplencia_historica_12m' });
      const data = resp.message || resp || {};

      if (typeof data.percent === 'number') {
        el.textContent = formatPercent(data.percent, 2);
        if (desc && typeof data.atrasado === 'number' && typeof data.total === 'number') {
          desc.textContent = `Últimos 12 meses • ${data.atrasado}/${data.total} associados`;
        }
      } else {
        el.textContent = '0,00%';
      }
    } catch (e) {
      el.textContent = 'Erro';
    }
  }

  async function fetchData(extraArgs) {
    const args = Object.assign({}, currentFilters, extraArgs || {});
    const r = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_entradas_saidas_mensal', args });
    return r.message || {};
  }

  function renderMoneyStackedBar({ id, labels, datasets, yAxisName, emptyMessage, stackKey, colorMap }) {
    if (!labels || !labels.length || !datasets || !datasets.length) {
      setChartMessage(id, emptyMessage || 'Sem dados.');
      return;
    }

    const chart = getChart(id);
    if (!chart) return;

    chart.setOption(
      {
        ...baseOption({ yAxisName }),
        xAxis: { ...baseOption().xAxis, data: labels },
        tooltip: {
          ...baseOption().tooltip,
          formatter: (params) => {
            const rows = params
              .map((item) => `${item.marker}${item.seriesName}: <strong>${formatCurrency(item.value)}</strong>`)
              .join('<br/>');
            return `<strong>${params[0]?.axisValue || ''}</strong><br/>${rows}`;
          },
        },
        series: datasets.map((ds) => ({
          name: ds.name,
          type: 'bar',
          stack: stackKey || null,
          barMaxWidth: 34,
          itemStyle: colorMap?.[ds.name] ? { color: colorMap[ds.name] } : undefined,
          emphasis: { focus: 'series' },
          data: (ds.values || []).map(parseNumber),
        })),
      },
      true,
    );
  }

  function renderMoneyLineWithBand({ id, labels, seriesName, values, color, yAxisName, emptyMessage }) {
    if (!labels || !labels.length || !values || !values.length) {
      setChartMessage(id, emptyMessage || 'Sem dados.');
      return;
    }

    const chart = getChart(id);
    if (!chart) return;

    const { values: coerced, mean, lower, upper } = computeBand(values);

    chart.setOption(
      {
        ...baseOption({ yAxisName, axisPointer: 'line' }),
        xAxis: { ...baseOption().xAxis, data: labels },
        tooltip: {
          ...baseOption().tooltip,
          axisPointer: { type: 'line' },
          formatter: (params) => {
            const item = params[0];
            if (!item) return '';
            return `<strong>${item.axisValue}</strong><br/>${item.marker}${seriesName}: <strong>${formatCurrency(item.value)}</strong>`;
          },
        },
        series: [
          {
            name: seriesName,
            type: 'line',
            symbol: 'circle',
            symbolSize: 7,
            smooth: 0.25,
            lineStyle: { width: 3, type: 'solid' },
            itemStyle: { color },
            areaStyle: { opacity: 0.1 },
            markArea: {
              itemStyle: { color: 'rgba(0, 114, 178, 0.08)' },
              data: [[{ yAxis: lower }, { yAxis: upper }]],
            },
            markLine: {
              symbol: 'none',
              lineStyle: { type: 'dashed', color: '#000000' },
              data: [{ yAxis: mean, name: 'Média' }],
            },
            data: coerced,
          },
        ],
      },
      true,
    );
  }

  async function renderEntradasSaidas() {
    const data = await fetchData();
    if (!data.labels || !data.labels.length) {
      setChartMessage('chart-entradas-saidas-mensal', 'Sem dados.');
      return;
    }

    const onlyBars = {
      labels: data.labels.slice(),
      datasets: (data.datasets || []).filter((d) => !/Resultado/i.test(d.name || '')),
    };

    renderMoneyStackedBar({
      id: 'chart-entradas-saidas-mensal',
      labels: onlyBars.labels,
      datasets: onlyBars.datasets,
      yAxisName: 'Valor (R$)',
      emptyMessage: 'Sem dados.',
      stackKey: null,
    });
  }

  async function renderResultado() {
    const data = await fetchData();
    if (!data.labels || !data.labels.length) {
      setChartMessage('chart-resultado-mensal', 'Sem dados.');
      return;
    }

    const dsResultado = (data.datasets || []).find((d) => /Resultado/i.test(d.name || ''));
    if (!dsResultado) {
      setChartMessage('chart-resultado-mensal', 'Sem dados de resultado.');
      return;
    }

    const chart = getChart('chart-resultado-mensal');
    if (!chart) return;
    const coerced = (dsResultado.values || []).map(parseNumber);

    chart.setOption(
      {
        ...baseOption({ yAxisName: 'Resultado (R$)', axisPointer: 'line' }),
        xAxis: { ...baseOption().xAxis, data: data.labels.slice() },
        tooltip: {
          ...baseOption().tooltip,
          axisPointer: { type: 'line' },
          formatter: (params) => {
            const item = params[0];
            if (!item) return '';
            return `<strong>${item.axisValue}</strong><br/>${item.marker}${dsResultado.name || 'Resultado'}: <strong>${formatCurrency(item.value)}</strong>`;
          },
        },
        series: [
          {
            name: dsResultado.name || 'Resultado',
            type: 'line',
            symbol: 'triangle',
            symbolSize: 8,
            smooth: 0.2,
            lineStyle: { width: 3, type: 'solid' },
            itemStyle: { color: '#0072B2' },
            areaStyle: { opacity: 0.08 },
            markLine: {
              symbol: 'none',
              lineStyle: { type: 'dashed', color: '#000000' },
              data: [{ yAxis: 0, name: 'Zero' }],
            },
            data: coerced,
          },
        ],
      },
      true,
    );
  }

  async function renderEntradasCredito() {
    const data = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_entradas_credito_mensal', args: currentFilters });
    const payload = data.message || data || {};
    const ds = (payload.datasets || [])[0];

    renderMoneyLineWithBand({
      id: 'chart-entradas-credito-mensal',
      labels: payload.labels,
      values: ds?.values,
      seriesName: ds?.name || 'Entradas (Crédito)',
      color: '#009E73',
      yAxisName: 'Valor (R$)',
      emptyMessage: 'Sem dados.',
    });
  }

  async function renderEntradasCreditoCategoria() {
    const { categoria, ...filtersSemCategoria } = currentFilters;
    const resp = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_entradas_credito_mensal_por_categoria', args: filtersSemCategoria });
    const payload = resp.message || resp || {};

    renderMoneyStackedBar({
      id: 'chart-entradas-credito-categoria-mensal',
      labels: payload.labels,
      datasets: payload.datasets,
      yAxisName: 'Valor (R$)',
      emptyMessage: 'Sem dados.',
      stackKey: 'entradas_categoria',
    });
  }

  async function renderEntradasCreditoCentro() {
    const { centro_de_custo, ...filtersSemCentro } = currentFilters;
    const resp = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_entradas_credito_mensal_por_centro_custo', args: filtersSemCentro });
    const payload = resp.message || resp || {};

    renderMoneyStackedBar({
      id: 'chart-entradas-credito-centro-mensal',
      labels: payload.labels,
      datasets: payload.datasets,
      yAxisName: 'Valor (R$)',
      emptyMessage: 'Sem dados.',
      stackKey: 'entradas_centro',
    });
  }

  async function renderEntradasCreditoTipo() {
    const { ordinaria_extraordinaria, ...filtersSemTipo } = currentFilters;
    const resp = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_entradas_credito_mensal_por_tipo', args: filtersSemTipo });
    const payload = resp.message || resp || {};

    renderMoneyStackedBar({
      id: 'chart-entradas-credito-tipo-mensal',
      labels: payload.labels,
      datasets: payload.datasets,
      yAxisName: 'Valor (R$)',
      emptyMessage: 'Sem dados.',
      stackKey: 'entradas_tipo',
    });
  }

  async function renderSaidasDebito() {
    const data = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_saidas_debito_mensal', args: currentFilters });
    const payload = data.message || data || {};
    const ds = (payload.datasets || [])[0];

    renderMoneyLineWithBand({
      id: 'chart-saidas-debito-mensal',
      labels: payload.labels,
      values: ds?.values,
      seriesName: ds?.name || 'Saídas (Débito)',
      color: '#D55E00',
      yAxisName: 'Valor (R$)',
      emptyMessage: 'Sem dados.',
    });
  }

  async function renderSaidasDebitoCategoria() {
    const { categoria, ...filtersSemCategoria } = currentFilters;
    const resp = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_saidas_debito_mensal_por_categoria', args: filtersSemCategoria });
    const payload = resp.message || resp || {};

    renderMoneyStackedBar({
      id: 'chart-saidas-debito-categoria-mensal',
      labels: payload.labels,
      datasets: payload.datasets,
      yAxisName: 'Valor (R$)',
      emptyMessage: 'Sem dados.',
      stackKey: 'saidas_categoria',
    });
  }

  async function renderSaidasDebitoCentro() {
    const { centro_de_custo, ...filtersSemCentro } = currentFilters;
    const resp = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_saidas_debito_mensal_por_centro_custo', args: filtersSemCentro });
    const payload = resp.message || resp || {};

    renderMoneyStackedBar({
      id: 'chart-saidas-debito-centro-mensal',
      labels: payload.labels,
      datasets: payload.datasets,
      yAxisName: 'Valor (R$)',
      emptyMessage: 'Sem dados.',
      stackKey: 'saidas_centro',
    });
  }

  async function renderSaidasDebitoTipo() {
    const { ordinaria_extraordinaria, ...filtersSemTipo } = currentFilters;
    const resp = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_saidas_debito_mensal_por_tipo', args: filtersSemTipo });
    const payload = resp.message || resp || {};

    renderMoneyStackedBar({
      id: 'chart-saidas-debito-tipo-mensal',
      labels: payload.labels,
      datasets: payload.datasets,
      yAxisName: 'Valor (R$)',
      emptyMessage: 'Sem dados.',
      stackKey: 'saidas_tipo',
    });
  }

  async function renderContribuicoesMensaisStatus() {
    const resp = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_contribuicoes_mensais_por_status' });
    const payload = resp.message || resp || {};
    const colorMap = {
      'Em Aberto': '#E69F00',
      Pago: '#009E73',
      Atrasado: '#D55E00',
      Cancelado: '#000000',
      'Sem Status': '#56B4E9',
    };

    if (!payload.labels || !payload.labels.length || !payload.datasets || !payload.datasets.length) {
      setChartMessage('chart-contribuicoes-status-mensal', 'Sem dados.');
      return;
    }

    const chart = getChart('chart-contribuicoes-status-mensal');
    if (!chart) return;

    chart.setOption(
      {
        ...baseOption({ yAxisName: 'Quantidade' }),
        xAxis: { ...baseOption().xAxis, data: payload.labels.slice() },
        tooltip: {
          ...baseOption().tooltip,
          formatter: (params) => {
            const rows = params
              .map((item) => `${item.marker}${item.seriesName}: <strong>${formatNumber(item.value)}</strong> contrib.`)
              .join('<br/>');
            return `<strong>${params[0]?.axisValue || ''}</strong><br/>${rows}`;
          },
        },
        series: payload.datasets.map((ds) => ({
          name: ds.name,
          type: 'bar',
          stack: 'status',
          barMaxWidth: 34,
          itemStyle: { color: colorMap[ds.name] || '#0072B2' },
          emphasis: { focus: 'series' },
          data: (ds.values || []).map(parseNumber),
        })),
      },
      true,
    );
  }

  async function renderContribuicoesMensaisInadimplencia() {
    const resp = await frappe.call({ method: 'gris.api.financeiro.dashboard.get_contribuicoes_mensais_inadimplencia' });
    const payload = resp.message || resp || {};
    const ds = (payload.datasets || [])[0];

    if (!payload.labels || !payload.labels.length || !ds) {
      setChartMessage('chart-contribuicoes-inadimplencia-mensal', 'Sem dados.');
      return;
    }

    const chart = getChart('chart-contribuicoes-inadimplencia-mensal');
    if (!chart) return;

    chart.setOption(
      {
        ...baseOption({ yAxisName: 'Inadimplência (%)', axisPointer: 'line' }),
        xAxis: { ...baseOption().xAxis, data: payload.labels.slice() },
        yAxis: {
          type: 'value',
          name: 'Inadimplência (%)',
          min: 0,
          max: 100,
          axisLabel: { formatter: (v) => `${v}%` },
        },
        tooltip: {
          ...baseOption().tooltip,
          axisPointer: { type: 'line' },
          formatter: (params) => {
            const item = params[0];
            if (!item) return '';
            return `<strong>${item.axisValue}</strong><br/>${item.marker}${ds.name || 'Inadimplência'}: <strong>${formatPercent(item.value, 2)}</strong>`;
          },
        },
        series: [
          {
            name: ds.name || 'Inadimplência',
            type: 'line',
            symbol: 'triangle',
            symbolSize: 8,
            smooth: 0.25,
            lineStyle: { width: 3, type: 'dashed' },
            itemStyle: { color: '#CC79A7' },
            areaStyle: { opacity: 0.08 },
            data: (ds.values || []).map(parseNumber),
          },
        ],
      },
      true,
    );
  }

  async function refreshCharts() {
    try {
      await ensureEcharts();
      setAllLoading();
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
    } catch (e) {
      console.warn('Erro ao atualizar gráficos', e);
      chartIds.forEach((id) => setChartMessage(id, 'Erro ao carregar gráfico.'));
    }
  }

  function bindResize() {
    window.addEventListener('resize', () => {
      if (!window.echarts) return;
      chartIds.forEach((id) => {
        const target = document.getElementById(id);
        if (!target) return;
        const chart = window.echarts.getInstanceByDom(target);
        if (chart) chart.resize();
      });
    });
  }

  frappe.ready(async () => {
    const form = document.getElementById('fin-dashboard-filters');
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        currentFilters = getFormFilters(form);
        await refreshCharts();
      });

      form.addEventListener('reset', () => {
        setTimeout(async () => {
          currentFilters = {};
          await refreshCharts();
        }, 0);
      });
    }

    bindResize();
    await refreshCharts();
  });
})();
