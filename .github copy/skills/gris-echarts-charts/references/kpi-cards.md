# Referencia de Cards KPI (Dashboard)

## Objetivo
Padronizar cards de KPI no GRIS com foco em legibilidade, consistencia visual e manutencao simples.

## Estrutura recomendada
Todo KPI deve seguir a hierarquia:
- `label`: nome da metrica
- `value`: numero principal
- `delta`: percentual/variacao
- `breakdown` (opcional): linhas auxiliares por categoria

## Quando usar HTML/CSS
Use HTML/CSS + JS para KPI quando:
- o card e textual (numero, percentual e subtitulo);
- nao ha sparkline no card;
- nao ha necessidade de animacao especial.

Vantagens:
- menor complexidade;
- menor custo de manutencao;
- melhor previsibilidade para ajustes de layout.

## Quando usar ECharts no KPI
Use ECharts no KPI apenas quando houver necessidade real de:
- sparkline no proprio card;
- composicao grafica customizada com `graphic`;
- animacao de transicao de valor que agrega UX.

## Snippet base (HTML)
```html
<div class="card-metric">
  <span class="card-metric__label">Registro Valido</span>
  <div class="metric-main-row">
    <div class="card-metric__value" id="card-reg-valido-total">--</div>
    <span class="metric-pct metric-pct--positive" id="card-reg-valido-pct">--%</span>
  </div>
</div>
```

## Snippet base (CSS)
```css
.card-metric {
  border: 1px solid var(--border-subtle, #e5e7eb);
  border-radius: 0.85rem;
  padding: 0.9rem 0.95rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.card-metric__value {
  font-size: clamp(1.55rem, 2.2vw, 1.95rem);
  line-height: 1.05;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.metric-main-row {
  display: flex;
  align-items: baseline;
  gap: 0.55rem;
}

.metric-pct {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 1.3rem;
  padding: 0.12rem 0.45rem;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
```

## Snippet base (ECharts - apenas quando necessario)
```js
chart.setOption({
  aria: { enabled: true },
  xAxis: { show: false, min: 0, max: 1 },
  yAxis: { show: false, min: 0, max: 1 },
  series: [],
  graphic: [
    {
      type: 'text',
      left: 'center',
      top: '20%',
      style: {
        text: '1.245',
        fill: '#111827',
        fontSize: 30,
        fontWeight: 700,
      },
    },
    {
      type: 'text',
      left: 'center',
      top: '66%',
      style: {
        text: '12,4%',
        fill: '#166534',
        fontSize: 12,
        fontWeight: 600,
      },
    },
  ],
});
```

## Checklist rapido para KPI
- [ ] Numeros com `tabular-nums`.
- [ ] Estados tratados: `--`, `--%`, `empty`, `error`.
- [ ] Contraste suficiente entre numero e fundo.
- [ ] Variacao nao depende apenas de cor.
- [ ] Layout validado em desktop e mobile.
