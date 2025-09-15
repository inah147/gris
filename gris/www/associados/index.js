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
    const chartTarget = document.getElementById('chart-ramos-categorias');
    if (chartTarget) chartTarget.innerHTML = '<div class="text-muted small px-2 pt-3">Carregando...</div>';
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
