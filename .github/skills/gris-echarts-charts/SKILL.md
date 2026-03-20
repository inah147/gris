---
name: gris-echarts-charts
description: Padroniza a criacao de graficos no GRIS usando exclusivamente Apache ECharts, com configuracoes de acessibilidade, temas e paleta de cores inclusiva para daltonismo.
---

# GRIS ECharts Charts

## Quando usar
Use esta skill quando a solicitacao envolver um ou mais pontos:
- criacao de novos graficos no portal, desk ou relatorios;
- refatoracao de graficos existentes;
- padronizacao visual e tecnica de visualizacoes de dados;
- definicao de paleta de cores acessivel para daltonismo;
- ajustes de tooltip, legenda, eixos ou estados de interacao em charts.
- padronizacao de cards KPI em dashboards (numero principal, percentual e breakdown).

## Objetivo
Garantir que todos os graficos do projeto GRIS sejam implementados com Apache ECharts, com foco em:
- consistencia visual e tecnica;
- legibilidade em desktop e mobile;
- acessibilidade para pessoas com daltonismo;
- configuracoes de interacao previsiveis;
- manutencao simples e reaproveitamento de opcoes.

## Regras mandatorias
- Todos os graficos devem usar Apache ECharts.
- Nao usar Chart.js, ApexCharts, D3 direto, Plotly ou bibliotecas alternativas para visualizacao principal.
- Definir as cores via tokens da paleta recomendada desta skill (sem hardcode disperso).
- Sempre configurar `tooltip`, `legend` e `grid` de forma explicita.
- Preferir `dataset` + `encode` quando fizer sentido, para separar dados da apresentacao.
- Em series com comparacao entre categorias, nao depender apenas de cor: combinar com `lineStyle.type`, `symbol` ou padrao visual equivalente.

## Cards KPI (numero grande)
Use estas diretrizes quando a tela tiver cards de metricas junto com graficos.

Para implementacao pratica (estrutura, snippets e checklist), consultar:
- `references/kpi-cards.md`

### Quando usar ECharts em KPI
- Use ECharts no KPI apenas quando houver necessidade de:
	- animacao de valor,
	- composicao grafica customizada (ex.: numero + subtitulo em `graphic`),
	- mini-serie (sparkline) no mesmo card.

### Quando NAO usar ECharts em KPI
- Se o card for somente numero + percentual + texto auxiliar, priorize HTML/CSS + atualizacao via JS.
- Evite usar ECharts apenas para desenhar texto estatico; aumenta custo de manutencao sem ganho de UX.

### Padrao visual recomendado para KPI
- Card com hierarquia clara:
	- `label` (titulo curto),
	- `value` (numero principal),
	- `delta` (percentual/variacao),
	- `breakdown` opcional (linhas auxiliares).
- Alinhar conteudo horizontalmente de forma consistente no grid (esquerda ou centro, sem misturar no mesmo bloco).
- Usar `font-variant-numeric: tabular-nums` para estabilidade visual de numeros.
- Para `delta`, usar badge/pill com contraste adequado e texto explicito (ex.: `12,3%`).
- Em breakdown, preferir linhas curtas com label + valor e espacamento regular.

### Estado e atualizacao de KPI
- Definir estados explicitos: `loading`, `success`, `empty`, `error`.
- Em loading, usar placeholders consistentes (`--`, `--%`) para evitar salto de layout.
- Manter IDs/selectors estaveis para nao quebrar o script de atualizacao.
- Ao usar filtro global, atualizar KPI e graficos no mesmo ciclo de refresh.

### Acessibilidade em KPI
- Nao depender so de cor para indicar positivo/negativo.
- Garantir contraste minimo entre numero e fundo.
- Em cards com variacao, preservar legibilidade em mobile (sem truncar percentual).
- Quando houver iconografia de status, manter texto junto do valor.

## Paleta inclusiva para daltonismo
Use como base a paleta Okabe-Ito (amplamente reconhecida como colorblind-safe):
- `--chart-blue`: `#0072B2`
- `--chart-orange`: `#E69F00`
- `--chart-sky`: `#56B4E9`
- `--chart-green`: `#009E73`
- `--chart-yellow`: `#F0E442`
- `--chart-red`: `#D55E00`
- `--chart-purple`: `#CC79A7`
- `--chart-black`: `#000000`

Para fundos claros do GRIS, priorize a ordem de uso:
1. `#0072B2`
2. `#E69F00`
3. `#009E73`
4. `#D55E00`
5. `#56B4E9`
6. `#CC79A7`
7. `#F0E442` (usar com cautela para linhas finas; melhor para destaque/area)
8. `#000000` (series de referencia/meta)

## Padrao minimo de configuracao ECharts
Toda implementacao deve cobrir ao menos:
- `aria: { enabled: true }` quando suportado pelo contexto da versao;
- `color: [...]` com a paleta da skill;
- `tooltip` com formato legivel;
- `legend` com nomes claros de series;
- `grid` com espacamento suficiente para rotulos;
- `xAxis` e `yAxis` com nomes e/ou formatacao quando relevante;
- `series` com identificacao explicita de tipo (`line`, `bar`, `pie`, etc.).

## Regras de UX para acessibilidade
- Nao transmitir informacao apenas por cor.
- Garantir contraste adequado entre serie e fundo.
- Evitar combinacoes simultaneas de vermelho x verde como unico canal sem reforco visual.
- Em graficos de linha, combinar cor + tipo de traco + simbolo de ponto.
- Em graficos de barra, considerar `itemStyle.borderColor` para separar tons proximos.
- Em pie/donut com muitas categorias, limitar quantidade exibida e agrupar cauda em "Outros".

## Estrutura recomendada no codigo
- Centralizar opcoes base em helper reutilizavel quando houver mais de um grafico na pagina.
- Manter dados e transformacoes em modulo separado da configuracao visual.
- Evitar objetos gigantes inline quando o grafico tiver multiplas series.
- Nomear series e eixos com termos de negocio em PT-BR.

## Anti-padroes
- Criar grafico novo com biblioteca diferente de Apache ECharts.
- Aplicar paleta aleatoria sem validacao para daltonismo.
- Duplicar configuracoes iguais em varios arquivos sem helper compartilhado.
- Tooltip sem unidade de medida em dados numericos.
- Rotulos truncados sem estrategia de responsividade.
- Usar ECharts para KPI textual simples sem necessidade funcional.
- Misturar alinhamentos diferentes entre cards KPI no mesmo bloco (parte centralizada, parte alinhada a esquerda sem criterio).
- Atualizar apenas o numero principal e esquecer percentual/breakdown no refresh.

## Checklist final
- [ ] O grafico usa Apache ECharts.
- [ ] A paleta aplicada e colorblind-safe e vem desta skill.
- [ ] Informacoes criticas nao dependem apenas de cor.
- [ ] Tooltip, legenda, eixos e grid foram configurados explicitamente.
- [ ] O grafico esta legivel em desktop e mobile.
- [ ] O codigo evita duplicacao e facilita manutencao.
- [ ] Cards KPI seguem hierarquia visual clara (label, value, delta, breakdown).
- [ ] Foi escolhido corretamente entre ECharts ou HTML/CSS para KPI.
- [ ] Estados de loading/erro/empty dos KPIs foram tratados.

## Referencia complementar
- Tokens e combinacoes recomendadas: `references/colorblind-palette.md`
- Cards KPI (quando usar ECharts vs HTML/CSS): `references/kpi-cards.md`
