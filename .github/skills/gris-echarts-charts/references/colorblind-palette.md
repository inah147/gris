# Paleta Colorblind-Safe para Graficos GRIS

## Base
A paleta adotada nesta skill parte do conjunto Okabe-Ito, reconhecido por boa distincao entre cores para diferentes tipos de daltonismo.

Cores principais:
- `#0072B2` (azul)
- `#E69F00` (laranja)
- `#56B4E9` (azul claro)
- `#009E73` (verde)
- `#F0E442` (amarelo)
- `#D55E00` (vermelho queimado)
- `#CC79A7` (magenta)
- `#000000` (preto)

## Ordem recomendada para series
Use esta ordem por padrao em fundos claros:
1. `#0072B2`
2. `#E69F00`
3. `#009E73`
4. `#D55E00`
5. `#56B4E9`
6. `#CC79A7`
7. `#F0E442`
8. `#000000`

## Boas praticas de uso
- Ate 4 series: usar as 4 primeiras cores da ordem recomendada.
- De 5 a 8 series: usar a lista completa.
- Acima de 8 series: agrupar categorias menores em "Outros" antes de adicionar novas cores.
- Evitar usar amarelo em linha fina sobre fundo branco; preferir barras, areas ou pontos maiores.
- Para destacar metas, media ou linha de referencia, preferir `#000000` com traco pontilhado.

## Exemplo de array para ECharts
```js
const CHART_COLORS = [
  '#0072B2',
  '#E69F00',
  '#009E73',
  '#D55E00',
  '#56B4E9',
  '#CC79A7',
  '#F0E442',
  '#000000'
]
```

## Exemplo de reforco nao cromatico
Quando houver comparacao de multiplas linhas, combine cor com variacao de traco:

```js
series: [
  { name: 'Realizado', type: 'line', lineStyle: { type: 'solid' }, symbol: 'circle' },
  { name: 'Meta', type: 'line', lineStyle: { type: 'dashed' }, symbol: 'triangle' },
  { name: 'Ano anterior', type: 'line', lineStyle: { type: 'dotted' }, symbol: 'rect' }
]
```
